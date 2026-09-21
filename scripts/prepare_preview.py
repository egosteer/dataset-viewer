"""Read-only access to s1; create a small, real, contract-compatible local preview."""
import json, sqlite3, subprocess, shlex
from pathlib import Path
from collections import Counter
root = Path(__file__).resolve().parents[1]
out = root / 'data/preview'
out.mkdir(parents=True, exist_ok=True)
tasks = ['Arrange Magnets of the Same Color in a Row on the Whiteboard', 'Fold the Towel', 'Pour Water into the Cup', 'Stack the Paper Cups', 'Open the Box', 'Stand the Screw Upright']
selected = []
counts = Counter()
for line in (root/'data/discovery.jsonl').open():
    r = json.loads(line)
    if r['type'] != 'episode': continue
    task = r['task_names'][0]
    counts[task] += 1
    if task in tasks and sum(x['task_names'][0] == task for x in selected) < 2:
        selected.append(r)
paths = {p for r in selected for p in [r['rrd']['path'], *r['duplicates']]}
# Annotation file keys use paths relative to /share_data/yifan/.
remote = """import json
wanted = %r
for line in open(%r):
 r=json.loads(line)
 p=r['episode']['file_path']
 if any(x.endswith('/'+p) or x==p for x in wanted):
  print(json.dumps({'path':p, 'zh':(r['annotation'].get('text') or {}).get('texts',[])},ensure_ascii=False))
""" % (paths, selected[0]['instruction_source']['annotation_path'])
result = subprocess.run(['ssh','s1','python3 -'],input=remote,text=True,capture_output=True,check=True)
annotations = [json.loads(x) for x in result.stdout.splitlines()]
records=[]
for r in selected:
    eid = r['episode_index']
    zh=[]
    for p in [r['rrd']['path'], *r['duplicates']]:
        for a in annotations:
            if p.endswith('/'+a['path']) or p==a['path']:
                for t in a['zh']:
                    if isinstance(t,str) and t.strip() and t not in zh: zh.append(t)
    videos={}
    for camera,v in r['videos'].items():
        rel=f'assets/episodes/{eid:06d}/{camera}.mp4'
        dest=out/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            e=v['exported']
            args=['ffmpeg','-v','error','-threads','2','-ss',str(e['from_seconds']),'-i',e['path'],'-frames:v',str(r['num_frames']),'-an','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-crf','26','-preset','fast','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1']
            temp=dest.with_suffix('.partial.mp4')
            with temp.open('wb') as f: subprocess.run(['ssh','s1',shlex.join(args)],stdout=f,check=True)
            subprocess.run(['ffmpeg','-v','error','-i',str(temp),'-c','copy','-movflags','+faststart','-y',str(dest)],check=True)
            temp.unlink()
        videos[camera]=rel
    records.append(dict(schema_version=1,episode_index=eid,task_name=r['task_names'][0],task_name_original=r['source_task_name'],split=r['split'],num_frames=r['num_frames'],fps=30,duration_seconds=r['duration_seconds'],videos=videos,annotations={'en':r['instructions'],'zh':zh}))
    print(f'Ready {eid}: {r["task_names"][0]} ({len(zh)} Chinese annotations)',flush=True)
(out/'index.ready.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
(out/'tasks.json').write_text(json.dumps([{'task_name':t,'episode_count':n} for t,n in sorted(counts.items())]))
(out/'progress.json').write_text(json.dumps({'status':'local_preview','total_episodes':sum(counts.values()),'ready_episodes':len(records),'preview':True}))
