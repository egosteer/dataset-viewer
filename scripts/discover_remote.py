"""Run via ssh s2 'python3 -' < this_file; read-only, emits JSONL to stdout.

Requires the remote's existing pyarrow. Never writes remote files.
"""
import csv
import hashlib
import json
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

PRIVATE = Path('/share_data/yifan/EgoSteer-RealWorld.private')
RAW = Path('/share_data/yifan/vla-teleop-data')
ASSETS = Path('/share_data/zhangtingrui/egosteer-data-website/assets')
env = json.loads((PRIVATE / 'environment.json').read_text())
cfg = env['config']
root = Path(cfg['output_root'])
info = json.loads((root / 'meta/info.json').read_text())
kept = set(Path(cfg['kept_list']).read_text().splitlines())
plan = {e['episode_index']: e for e in json.loads((PRIVATE / 'plan.json').read_text())['episodes']}
mapping = {r['current_task_name']: r['official_task_name'] for r in csv.DictReader(open(cfg['task_mapping_csv'], encoding='utf-8-sig'))}
merged = json.loads(Path(cfg['merged_instructions_json']).read_text())
annotations = {}
for line_no, line in enumerate(open(cfg['annotation_jsonl']), 1):
    row = json.loads(line)
    annotations[row['episode']['file_path']] = (line_no, row['annotation'])
hashes = {}
for key, expected in env['inputs_sha1'].items():
    actual = hashlib.sha1(Path(cfg[key]).read_bytes()).hexdigest()
    hashes[key] = dict(expected=expected, actual=actual, matches=actual == expected)
columns = ['episode_index', 'tasks', 'length', 'split', 'instructions']
for cam in ('head', 'chest'):
    columns += [f'videos/observation.images.{cam}/{s}' for s in ('chunk_index', 'file_index', 'from_timestamp', 'to_timestamp')]
metadata = {}
for file in sorted((root / 'meta/episodes').rglob('*.parquet')):
    for row_index, row in enumerate(pq.read_table(file, columns=columns).to_pylist()):
        assert row['episode_index'] not in metadata
        metadata[row['episode_index']] = (str(file), row_index, row)
provenance = pq.read_table(PRIVATE / 'provenance.parquet').to_pylist()
counts = Counter()
tasks = Counter()
paths = set()
stat_cache = {}
def file_info(path):
    path = str(path)
    if path not in stat_cache:
        p = Path(path)
        try:
            st = p.stat()
            exists = stat.S_ISREG(st.st_mode)
            size = st.st_size if exists else None
        except FileNotFoundError:
            exists, size = False, None
        stat_cache[path] = {'path': path, 'exists': exists, 'bytes': size}
    return stat_cache[path]
for prov in provenance:
    eid = prov['episode_index']
    source = prov['source_path']
    assert source not in paths
    paths.add(source)
    meta_file, row_index, meta = metadata[eid]
    p = plan[eid]
    rel = str(Path(source).relative_to(RAW if Path(source).is_relative_to(RAW) else RAW.parent))
    line_no, ann = annotations.get(rel, (None, {}))
    issues = []
    if source not in kept: issues.append('not_in_kept_list')
    if p['path'] != source: issues.append('plan_source_mismatch')
    if meta['tasks'] != [mapping.get(prov['source_task_name'])]: issues.append('task_mapping_mismatch')
    if meta['instructions'] != p['instructions']: issues.append('plan_instructions_mismatch')
    instruction_input = merged[source]['instructions'] if source in merged else (ann.get('text') or {}).get('labels', [])
    if meta['instructions'] != instruction_input: issues.append('instruction_input_mismatch')
    if ann.get('id') != prov['annotation_id']: issues.append('annotation_id_mismatch')
    if not meta['instructions']: issues.append('missing_instructions')
    rrd = file_info(source)
    if not rrd['exists']: issues.append('missing_rrd')
    videos = {}
    for cam, suffix in [('head', 'head'), ('chest', 'breast')]:
        original = file_info(Path(source).with_name(Path(source).stem + '_' + suffix + '.mp4'))
        key = 'observation.images.' + cam
        prefix = 'videos/' + key + '/'
        exported = file_info(root / info['video_path'].format(video_key=key, chunk_index=meta[prefix+'chunk_index'], file_index=meta[prefix+'file_index']))
        if not original['exists'] or not original['bytes']: issues.append('missing_original_' + cam)
        if not exported['exists'] or not exported['bytes']: issues.append('missing_exported_' + cam)
        counts['original_' + cam + '_bytes'] += original['bytes'] or 0
        asset_rel = f'episodes/{eid:06d}/{cam}.mp4'
        videos[cam] = {'original': original, 'exported': {**exported, 'from_seconds': meta[prefix+'from_timestamp'], 'to_seconds': meta[prefix+'to_timestamp']}, 'asset_relative_path': asset_rel, 'asset_target_path': str(ASSETS / asset_rel), 'asset_status': 'planned'}
    record = {'type': 'episode', 'episode_index': eid, 'source_task_name': prov['source_task_name'], 'task_names': meta['tasks'], 'rrd': rrd, 'split': meta['split'], 'num_frames': meta['length'], 'duration_seconds': meta['length']/info['fps'], 'instructions': meta['instructions'], 'instruction_source': {'metadata_path': meta_file, 'metadata_row_zero_based': row_index, 'field': 'instructions', 'annotation_path': cfg['annotation_jsonl'], 'annotation_line_one_based': line_no, 'annotation_id': prov['annotation_id'], 'annotation_field': 'annotation.text.labels', 'merged_path': cfg['merged_instructions_json'] if source in merged else None, 'merged_key': source if source in merged else None}, 'duplicates': prov['duplicates'], 'videos': videos, 'issues': issues}
    counts['episodes'] += 1
    counts['merged_instruction_episodes'] += source in merged
    counts['episodes_with_issues'] += bool(issues)
    counts.update(issues)
    tasks.update(meta['tasks'])
    print(json.dumps(record, ensure_ascii=False))
assert set(metadata) == {p['episode_index'] for p in provenance}
print(json.dumps({'type': 'audit', 'checked_at': datetime.now(timezone.utc).isoformat(), 'host': 's2', 'counts': dict(counts), 'task_count': len(tasks), 'tasks': dict(tasks), 'kept_count': len(kept), 'kept_not_exported': sorted(kept-paths), 'exported_not_kept': sorted(paths-kept), 'plan_count': len(plan), 'metadata_count': len(metadata), 'info_episode_count': info['total_episodes'], 'input_hashes': hashes, 'config': cfg, 'environment_path': str(PRIVATE/'environment.json'), 'provenance_path': str(PRIVATE/'provenance.parquet')}, ensure_ascii=False))
