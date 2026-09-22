"""Export the verified public catalog as deterministic gzip to stdout (no COS calls).

Run on s1: python export_static_index.py > index.jsonl.gz
Only approved public fields are exported; raw indexes must never be bundled.
"""
import gzip
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, '/share_data/zhangtingrui/egosteer-dataset-website/pipeline')
from upload_cos import public_record

root = Path('/share_data/zhangtingrui/egosteer-dataset-website')
success = json.loads((root/'pipeline/cos-upload/last-success.json').read_text())
assert success['snapshot_complete'] and success['episodes'] == success['total_episodes']
base = success['public_base_url']
assert base == 'https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/'
seen = set()
with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', filename='', mtime=0) as out:
    for line in (root/'index.ready.jsonl').open():
        record = public_record(json.loads(line))
        assert record['episode_index'] not in seen
        seen.add(record['episode_index'])
        for field in ('videos', 'thumbnails'):
            record[field] = {camera:base+quote(relative, safe='/') for camera,relative in record[field].items()}
        out.write((json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n').encode())
assert len(seen) == success['episodes']
print(f'Exported {len(seen)} sanitized records', file=sys.stderr)
