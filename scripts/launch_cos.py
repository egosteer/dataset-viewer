"""Launch the authorized upload on s1; read credentials from stdin, never a file.

The input line is JSON with COS_SECRET_ID and COS_SECRET_KEY (and optional
COS_SESSION_TOKEN). Call through a non-echoing terminal or private pipe.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path('/share_data/zhangtingrui/egosteer-dataset-website/pipeline')
credentials = json.loads(sys.stdin.readline())
assert credentials.get('COS_SECRET_ID') and credentials.get('COS_SECRET_KEY')
env = {**os.environ, **{k: credentials[k] for k in
       ('COS_SECRET_ID', 'COS_SECRET_KEY', 'COS_SESSION_TOKEN') if k in credentials}}
with (root/'upload_cos.log').open('a') as log:
    process = subprocess.Popen([
        str(root/'.venv-cos/bin/python'), '-u', str(root/'upload_cos.py'),
        '--require-complete', '--workers', '32', '--thumbnail-workers', '8',
    ], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
       env=env, start_new_session=True)
(root/'upload_cos.pid').write_text(str(process.pid)+'\n')
print(json.dumps({'pid':process.pid,'log':str(root/'upload_cos.log')}))
