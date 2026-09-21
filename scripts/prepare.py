"""Create the website catalog on s1, reading source data without modifying it."""
import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import pyarrow.parquet as pq

ROOT = Path('/share_data/zhangtingrui/egosteer-dataset-website')
PRIVATE = Path('/share_data/yifan/EgoSteer-RealWorld.private')
ENV = json.loads((PRIVATE/'environment.json').read_text())
C = ENV['config']
DATA = Path(C['output_root'])
ANNOTATIONS = C['annotation_jsonl']

def dump(path, obj):
    tmp = path.with_suffix(path.suffix+'.partial')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)

def texts(values):
    return list(dict.fromkeys(s.strip() for s in values if isinstance(s, str) and s.strip()))

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT/'pipeline').mkdir(exist_ok=True)
    target = ROOT/'pipeline/jobs.sqlite'
    if target.exists():
        raise SystemExit('jobs.sqlite already exists; use transcode.py to resume, do not overwrite the catalog')
    for key, expected in ENV['inputs_sha1'].items():
        assert hashlib.sha1(Path(C[key]).read_bytes()).hexdigest() == expected, key
    annotations = {}
    for line_no, line in enumerate(open(ANNOTATIONS), 1):
        row = json.loads(line)
        rel = row['episode']['file_path']
        path = rel if rel.startswith('/') else str(Path('/share_data/yifan')/rel) if rel.startswith('vla-teleop-data-multitask/') else str(Path('/share_data/yifan/vla-teleop-data')/rel)
        assert path not in annotations, path
        annotations[path] = (line_no, row['annotation'])
    mapping = {r['current_task_name']: r['official_task_name'] for r in csv.DictReader(open(C['task_mapping_csv'], encoding='utf-8-sig'))}
    plan = {r['episode_index']: r for r in json.loads((PRIVATE/'plan.json').read_text())['episodes']}
    provenance = {r['episode_index']: r for r in pq.read_table(PRIVATE/'provenance.parquet').to_pylist()}
    kept = set(Path(C['kept_list']).read_text().splitlines())
    assert {r['source_path'] for r in provenance.values()} == kept
    info = json.loads((DATA/'meta/info.json').read_text())
    columns = ['episode_index', 'tasks', 'length', 'split', 'instructions']
    for cam in ('head','chest'):
        columns += [f'videos/observation.images.{cam}/{s}' for s in ('chunk_index','file_index','from_timestamp','to_timestamp')]
    dbtmp = target.with_suffix('.sqlite.partial')
    if dbtmp.exists(): dbtmp.unlink()
    db = sqlite3.connect(dbtmp)
    db.executescript('''
    CREATE TABLE jobs (episode_index INTEGER PRIMARY KEY, record_json TEXT NOT NULL,
    sources_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    error TEXT, output_bytes INTEGER, completed_at TEXT);
    CREATE INDEX jobs_status ON jobs(status);
    ''')
    tasks = Counter()
    missing_zh = []
    count = 0
    output = ROOT/'index.jsonl.partial'
    with output.open('w') as out:
        for metafile in sorted((DATA/'meta/episodes').rglob('*.parquet')):
            for m in pq.read_table(metafile, columns=columns).to_pylist():
                eid = m['episode_index']
                p = provenance[eid]
                assert m['tasks'] == [mapping[p['source_task_name']]]
                assert m['instructions'] == plan[eid]['instructions']
                assert m['instructions'] and p['source_path'] in kept
                ann_sources = []
                zh = []
                for i, source in enumerate([p['source_path']] + p['duplicates']):
                    line_no, ann = annotations[source]
                    assert ann is not None, source
                    if i == 0: assert ann['id'] == p['annotation_id']
                    text = ann.get('text') or {}
                    en_raw, zh_raw = text.get('labels') or [], text.get('texts') or []
                    assert isinstance(en_raw,list) and isinstance(zh_raw,list)
                    zh.extend(zh_raw)
                    ann_sources.append({'rrd_path': source, 'role': 'primary' if i==0 else 'duplicate', 'annotation_id': ann['id'], 'annotation_jsonl_path': ANNOTATIONS, 'annotation_line_one_based': line_no, 'en': en_raw, 'zh': zh_raw})
                zh = texts(zh)
                if not zh: missing_zh.append(eid)
                videos, sources = {}, {}
                for cam in ('head','chest'):
                    key = 'observation.images.'+cam
                    prefix = 'videos/'+key+'/'
                    source = DATA/info['video_path'].format(video_key=key, chunk_index=m[prefix+'chunk_index'], file_index=m[prefix+'file_index'])
                    videos[cam] = f'assets/episodes/{eid:06d}/{cam}.mp4'
                    sources[cam] = {'path': str(source), 'from_seconds': m[prefix+'from_timestamp'], 'to_seconds': m[prefix+'to_timestamp']}
                    assert abs((sources[cam]['to_seconds']-sources[cam]['from_seconds'])*30-m['length']) < .01
                r = {'schema_version': 1, 'episode_index': eid, 'rrd_path': p['source_path'], 'task_name_original': p['source_task_name'], 'task_name': m['tasks'][0], 'split': m['split'], 'num_frames': m['length'], 'fps': 30, 'duration_seconds': m['length']/30, 'videos': videos, 'annotations': {'en': m['instructions'], 'zh': zh}, 'annotation_sources': ann_sources, 'duplicate_rrd_paths': p['duplicates'], 'instruction_metadata_path': str(metafile)}
                line = json.dumps(r, ensure_ascii=False, separators=(',',':'))
                out.write(line+'\n')
                db.execute('INSERT INTO jobs(episode_index,record_json,sources_json) VALUES (?,?,?)',(eid,line,json.dumps(sources)))
                tasks[r['task_name']] += 1
                count += 1
    assert count == len(kept) == len(provenance) == len(plan) == info['total_episodes']
    db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    output.replace(ROOT/'index.jsonl')
    dbtmp.replace(target)
    (ROOT/'index.ready.jsonl').touch()
    dump(ROOT/'tasks.json', [{'task_name': k, 'episode_count': v} for k,v in sorted(tasks.items())])
    dump(ROOT/'index.metadata.json', {'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'total_episodes':count,'total_tasks':len(tasks),'missing_chinese_episode_indices':missing_zh,'environment_path':str(PRIVATE/'environment.json'),'input_sha1':ENV['inputs_sha1'],'video_encoding':{'codec':'h264','pixel_format':'yuv420p','width':640,'height':480,'fps':30,'crf':26,'preset':'medium','faststart':True,'audio':False},'annotation_semantics':'English is final exported instructions. Chinese is the ordered exact-deduplicated union of primary and duplicate original texts. Arrays are not aligned translations.'})
    dump(ROOT/'progress.json',{'status':'prepared','updated_at':datetime.now(timezone.utc).isoformat(),'total_episodes':count,'ready_episodes':0,'failed_episodes':0,'pending_episodes':count,'workers':32,'threads_per_codec':2,'ffmpeg_memory_limit_mib':2048})
    print(json.dumps({'episodes':count,'tasks':len(tasks),'missing_chinese':len(missing_zh)}), flush=True)

if __name__ == '__main__': main()
