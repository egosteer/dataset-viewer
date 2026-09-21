"""Bounded parallel, resumable FFmpeg conversion. Writes only website root."""
import argparse
import concurrent.futures as futures
import fcntl
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/share_data/zhangtingrui/egosteer-dataset-website')
ENV = {**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
CAP = ['/bin/bash','-c','ulimit -v 2097152; exec "$@"','bounded-media']

def stamp(): return datetime.now(timezone.utc).isoformat()

def probe(path, frames):
    cmd = CAP + ['ffprobe','-v','error','-threads','1','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt,width,height,nb_frames,r_frame_rate:format=duration','-of','json',str(path)]
    p = subprocess.run(cmd,env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
    if p.returncode: raise RuntimeError(p.stderr[-2000:])
    d = json.loads(p.stdout)
    s = d['streams'][0]
    assert s['codec_name']=='h264' and s['pix_fmt']=='yuv420p',s
    assert (s['width'],s['height'])==(640,480),s
    assert s['r_frame_rate']=='30/1' and int(s['nb_frames'])==frames,s
    assert abs(float(d['format']['duration'])-frames/30)<.05,d
    assert path.stat().st_size>0

def convert(job):
    eid, record_json, sources_json = job
    r, sources = json.loads(record_json),json.loads(sources_json)
    start = time.monotonic()
    total_bytes = 0
    try:
        for cam in ('head','chest'):
            out = ROOT/r['videos'][cam]
            out.parent.mkdir(parents=True,exist_ok=True)
            if out.exists():
                probe(out,r['num_frames'])
                total_bytes += out.stat().st_size
                continue
            tmp = out.with_name(out.stem+'.partial.mp4')
            src = sources[cam]
            cmd = CAP + ['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-xerror',
                '-threads','2','-ss',f"{src['from_seconds']:.9f}",'-i',src['path'],
                '-map','0:v:0','-an','-sn','-dn','-frames:v',str(r['num_frames']),
                '-filter_threads','1','-filter_complex_threads','1','-vf','scale=640:480',
                '-r','30','-vsync','cfr','-c:v','libx264','-threads','2','-preset','medium',
                '-crf','26','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)]
            p = subprocess.run(cmd,env=ENV,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=600)
            if p.returncode: raise RuntimeError(f'{cam}: FFmpeg exit {p.returncode}: {p.stderr[-3000:]}')
            probe(tmp,r['num_frames'])
            tmp.replace(out)
            total_bytes += out.stat().st_size
        return eid,True,total_bytes,time.monotonic()-start,None
    except Exception as exc:
        return eid,False,0,time.monotonic()-start,str(exc)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workers',type=int,default=32)
    ap.add_argument('--limit',type=int)
    args=ap.parse_args()
    assert 1<=args.workers<=64
    lock=(ROOT/'pipeline/transcode.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.nice(10)
    db=sqlite3.connect(ROOT/'pipeline/jobs.sqlite')
    db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
    db.commit()
    tmp=ROOT/'index.ready.jsonl.partial'
    with tmp.open('w') as f:
        for (record,) in db.execute("SELECT record_json FROM jobs WHERE status='ready' ORDER BY episode_index"):
            f.write(record+'\n')
    tmp.replace(ROOT/'index.ready.jsonl')
    total=db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    query="SELECT episode_index,record_json,sources_json FROM jobs WHERE status != 'ready' ORDER BY episode_index"
    if args.limit is not None: query+=' LIMIT '+str(max(0,args.limit))
    # Read only IDs first; keep at most workers jobs and subprocess outputs resident.
    ids=[r[0] for r in db.execute(query.replace('episode_index,record_json,sources_json','episode_index'))]
    started=time.monotonic()
    run_done=0
    def progress(status):
        counts=dict(db.execute('SELECT status,COUNT(*) FROM jobs GROUP BY status'))
        obj={'status':status,'updated_at':stamp(),'total_episodes':total,'ready_episodes':counts.get('ready',0),'failed_episodes':counts.get('failed',0),'pending_episodes':counts.get('pending',0)+counts.get('running',0),'workers':args.workers,'threads_per_codec':2,'ffmpeg_memory_limit_mib':2048,'pid':os.getpid(),'run_completed_episodes':run_done,'run_elapsed_seconds':round(time.monotonic()-started,2)}
        tmp=ROOT/'progress.json.partial'
        tmp.write_text(json.dumps(obj,indent=2)+'\n')
        tmp.replace(ROOT/'progress.json')
    iterator=iter(ids)
    with (ROOT/'index.ready.jsonl').open('a',buffering=1) as ready, futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active={}
        def submit():
            eid=next(iterator,None)
            if eid is None:return
            row=db.execute('SELECT episode_index,record_json,sources_json FROM jobs WHERE episode_index=?',(eid,)).fetchone()
            db.execute("UPDATE jobs SET status='running',error=NULL WHERE episode_index=?",(eid,))
            db.commit()
            active[pool.submit(convert,row)]=row
        for _ in range(args.workers):submit()
        progress('running')
        while active:
            finished,_=futures.wait(active,timeout=10,return_when=futures.FIRST_COMPLETED)
            for future in finished:
                row=active.pop(future)
                eid,ok,size,seconds,error=future.result()
                db.execute('UPDATE jobs SET status=?,error=?,output_bytes=?,completed_at=? WHERE episode_index=?',('ready' if ok else 'failed',error,size,stamp(),eid))
                db.commit()
                if ok:ready.write(row[1]+'\n')
                run_done+=1
                print(json.dumps({'episode_index':eid,'ok':ok,'bytes':size,'seconds':round(seconds,2),'error':error}),flush=True)
                submit()
            progress('running')
    pending=db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('pending','running')").fetchone()[0]
    failed=db.execute("SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0]
    progress('prepared' if pending else 'completed_with_errors' if failed else 'completed')
    print(json.dumps({'run_finished':True,'processed':run_done,'pending':pending,'failed':failed,'seconds':round(time.monotonic()-started,2)}),flush=True)
    db.close()

if __name__=='__main__': main()
