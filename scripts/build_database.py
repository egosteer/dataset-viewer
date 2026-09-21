"""Build a private local SQLite catalog from a completed discovery stream."""
import json
import sqlite3
from pathlib import Path

data = Path(__file__).resolve().parents[1] / 'data'
target = data / 'catalog.sqlite'
temporary = data / 'catalog.sqlite.partial'
if temporary.exists():
    temporary.unlink()
db = sqlite3.connect(temporary)
db.executescript('''
PRAGMA foreign_keys=ON;
CREATE TABLE episodes (
 episode_index INTEGER PRIMARY KEY, task_name TEXT NOT NULL,
 source_task_name TEXT NOT NULL, rrd_path TEXT UNIQUE NOT NULL,
 split TEXT NOT NULL, num_frames INTEGER NOT NULL, duration_seconds REAL NOT NULL,
 instruction_source_json TEXT NOT NULL, duplicates_json TEXT NOT NULL,
 issues_json TEXT NOT NULL
);
CREATE INDEX episodes_task ON episodes(task_name);
CREATE TABLE instructions (
 episode_index INTEGER REFERENCES episodes, ordinal INTEGER, text TEXT NOT NULL,
 PRIMARY KEY(episode_index, ordinal)
);
CREATE TABLE videos (
 episode_index INTEGER REFERENCES episodes, camera TEXT CHECK(camera IN ('head','chest')),
 original_path TEXT, original_exists INTEGER, original_bytes INTEGER,
 exported_path TEXT, exported_exists INTEGER, from_seconds REAL, to_seconds REAL,
 asset_relative_path TEXT UNIQUE, asset_target_path TEXT, asset_status TEXT,
 PRIMARY KEY(episode_index,camera)
);
CREATE TABLE audit (json TEXT NOT NULL);
''')
audit = None
count = 0
source = data/'discovery.jsonl.partial'
if not source.exists():
    source = data/'discovery.jsonl'
with source.open() as stream:
    for line in stream:
        r = json.loads(line)
        if r['type'] == 'audit':
            assert audit is None
            audit = r
            continue
        assert audit is None, 'Audit must be the last record'
        assert len(r['task_names']) == 1
        eid = r['episode_index']
        db.execute('INSERT INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?)', (eid,r['task_names'][0],r['source_task_name'],r['rrd']['path'],r['split'],r['num_frames'],r['duration_seconds'],json.dumps(r['instruction_source'],ensure_ascii=False),json.dumps(r['duplicates']),json.dumps(r['issues'])))
        db.executemany('INSERT INTO instructions VALUES (?,?,?)', [(eid,i,t) for i,t in enumerate(r['instructions'])])
        for cam,v in r['videos'].items():
            o,e = v['original'],v['exported']
            db.execute('INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(eid,cam,o['path'],o['exists'],o['bytes'],e['path'],e['exists'],e['from_seconds'],e['to_seconds'],v['asset_relative_path'],v['asset_target_path'],v['asset_status']))
        count += 1
assert audit and count == audit['counts']['episodes'] == audit['info_episode_count']
db.execute('INSERT INTO audit VALUES (?)', (json.dumps(audit,ensure_ascii=False),))
db.commit()
assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
assert not db.execute('PRAGMA foreign_key_check').fetchall()
assert db.execute('SELECT COUNT(*) FROM videos').fetchone()[0] == count*2
assert db.execute('SELECT COUNT(*) FROM episodes e WHERE NOT EXISTS (SELECT 1 FROM instructions i WHERE i.episode_index=e.episode_index)').fetchone()[0] == 0
db.close()
temporary.replace(target)
if source.name.endswith('.partial'):
    source.replace(data/'discovery.jsonl')
(data/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'episodes': count, 'database': str(target), 'audit_counts': audit['counts']},indent=2))
