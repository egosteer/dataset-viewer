#!/usr/bin/env python3
"""Upload validated previews and an allowlisted public index with Tencent COS SDK.

No directory recursion: only ready MP4s and their generated JPEGs are eligible.
Credentials: COS_SECRET_ID, COS_SECRET_KEY, optional COS_SESSION_TOKEN.
"""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote

DEFAULT_ROOT = '/share_data/zhangtingrui/egosteer-dataset-website'
BUCKET = 'ego-steer-1351596430'
REGION = 'ap-shanghai'
PUBLIC_FIELDS = ('schema_version', 'episode_index', 'task_name_original',
                 'task_name', 'split', 'num_frames', 'fps', 'duration_seconds')

class UploadError(RuntimeError): pass

def public_record(record):
    """Explicit schema, never propagate new private fields from a source record."""
    out = {k: record[k] for k in PUBLIC_FIELDS}
    eid = out['episode_index']
    if type(eid) is not int or eid < 0:
        raise ValueError('Invalid episode_index')
    if out['schema_version'] != 1 or out['split'] not in ('train', 'val'):
        raise ValueError('Unsupported record schema')
    if not isinstance(out['task_name'], str) or not isinstance(out['task_name_original'], str):
        raise ValueError('Invalid task name')
    if out['fps'] != 30 or type(out['num_frames']) is not int or out['num_frames'] <= 0:
        raise ValueError('Invalid timing')
    if abs(out['duration_seconds']-out['num_frames']/30) > .001:
        raise ValueError('Inconsistent duration')
    out['videos'] = {}
    out['thumbnails'] = {}
    for camera in ('head', 'chest'):
        expected = f'assets/episodes/{eid:06d}/{camera}.mp4'
        if record['videos'][camera] != expected:
            raise ValueError('Video path does not match episode/camera')
        out['videos'][camera] = expected
        out['thumbnails'][camera] = str(Path(expected).with_suffix('.jpg'))
    out['annotations'] = {}
    for lang in ('en', 'zh'):
        values = record['annotations'][lang]
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError('Invalid annotation array')
        out['annotations'][lang] = values
    if not out['annotations']['en']:
        raise ValueError('Missing English annotations')
    payload = json.dumps(out, ensure_ascii=False)
    # Defense in depth after allowlisting: never silently publish private paths/keys.
    if re.search(r'/share_data(?:_exp)?/|/Users/|AKID[A-Za-z0-9]{16,}|SecretKey|COS_SECRET', payload):
        raise ValueError('Private-looking content in public fields; manual review required')
    for key in ('COS_SECRET_ID', 'COS_SECRET_KEY', 'COS_SESSION_TOKEN'):
        if os.environ.get(key) and os.environ[key] in payload:
            raise ValueError('Credential detected in public fields')
    return out

def media_path(root, relative):
    path = root / relative
    resolved = path.resolve(strict=True)
    assets = (root/'assets').resolve(strict=True)
    if not resolved.is_relative_to(assets) or not resolved.is_relative_to(root.resolve()):
        raise ValueError('Media path escapes the website assets directory')
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError('Missing or empty preview')
    return resolved

def snapshot(root):
    records = {}
    # Freeze the read boundary; transcode may be appending to this file concurrently.
    with (root/'index.ready.jsonl').open('rb') as stream:
        remaining = os.fstat(stream.fileno()).st_size
        while remaining:
            line = stream.readline(remaining)
            remaining -= len(line)
            if not line.endswith(b'\n'):
                break
            record = public_record(json.loads(line))
            eid = record['episode_index']
            if eid in records and records[eid] != record:
                raise ValueError('Conflicting duplicate episode')
            records[eid] = record
    if not records:
        raise ValueError('No completed episodes to publish')
    return [records[eid] for eid in sorted(records)]

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def jpeg_valid(path):
    """Check the generated JPEG's boundaries without loading the image into RAM."""
    if not path.is_file() or path.stat().st_size < 4:
        return False
    with path.open('rb') as stream:
        start = stream.read(2)
        stream.seek(-2, 2)
        return start == b'\xff\xd8' and stream.read(2) == b'\xff\xd9'

def generate_thumbnail(video, relative, frames, cache, semaphore):
    """Extract near one second (midpoint for short clips); cache by source content.

    The cache is local-only. COS uses the video's path with .jpg instead of .mp4.
    """
    source_stat = video.stat()
    source_digest = sha256(video)
    frame = min(30, frames // 2)
    identity = hashlib.sha256(
        f'jpeg-v1:{source_digest}:{relative}:{frame}:640:q3'.encode()
    ).hexdigest()
    directory = cache / identity
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / Path(relative).with_suffix('.jpg').name
    if jpeg_valid(output):
        return output
    with semaphore:
        fd, filename = tempfile.mkstemp(prefix='frame-', suffix='.jpg', dir=directory)
        os.close(fd)
        temporary = Path(filename)
        try:
            command = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                '-xerror', '-threads', '1', '-ss', f'{frame / 30:.9f}', '-i', str(video),
                '-map', '0:v:0', '-an', '-sn', '-dn', '-frames:v', '1',
                '-filter_threads', '1', '-filter_complex_threads', '1',
                '-vf', 'scale=640:-2', '-c:v', 'mjpeg', '-threads', '1',
                '-q:v', '3', '-f', 'image2', str(temporary),
            ]
            result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, timeout=60,
                                    env={**os.environ, 'OMP_NUM_THREADS': '1',
                                         'OPENBLAS_NUM_THREADS': '1'})
            if result.returncode or not jpeg_valid(temporary):
                raise UploadError('Thumbnail extraction failed')
            after = video.stat()
            if (source_stat.st_size, source_stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise UploadError('Source video changed during thumbnail extraction')
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    return output

def status_code(exc):
    try: return int(exc.get_status_code())
    except (AttributeError, ValueError, TypeError): return None

def retry(call, attempts):
    for attempt in range(attempts):
        try: return call()
        except Exception as exc:
            status = status_code(exc)
            if status is not None and status not in (408, 429) and status < 500:
                raise
            if attempt == attempts-1: raise
            time.sleep(min(30, 2**attempt) + random.random())

def safe_error(exc):
    # SDK exception strings may contain request headers; never print them.
    return f'{type(exc).__name__}' + (f' HTTP {status_code(exc)}' if status_code(exc) else '')

class Uploader:
    def __init__(self, client, bucket, prefix, attempts=5, overwrite=False):
        self.client, self.bucket, self.prefix = client, bucket, prefix
        self.attempts, self.overwrite = attempts, overwrite

    def key(self, relative):
        return '/'.join(p for p in (self.prefix, relative) if p)

    def head(self, key):
        try:
            return retry(lambda: self.client.head_object(Bucket=self.bucket, Key=key), self.attempts)
        except Exception as exc:
            if status_code(exc) == 404: return None
            raise

    @staticmethod
    def matches(headers, size, digest):
        h = {k.lower(): str(v) for k,v in (headers or {}).items()}
        return h.get('content-length') == str(size) and h.get('x-cos-meta-sha256') == digest

    def file(self, path, relative, content_type, catalog=False):
        stat = path.stat()
        size, digest = stat.st_size, sha256(path)
        key = self.key(relative)
        existing = self.head(key)
        if self.matches(existing, size, digest): return 'skipped', size
        if existing is not None and not (catalog or self.overwrite):
            raise UploadError('Existing media differs; choose a new prefix or --overwrite-media')
        retry(lambda: self.client.upload_file(
            Bucket=self.bucket, Key=key, LocalFilePath=str(path), PartSize=8,
            MAXThread=1, EnableMD5=True, ContentType=content_type,
            CacheControl='no-cache' if catalog else 'public, max-age=86400',
            Metadata={'x-cos-meta-sha256': digest},
        ), self.attempts)
        # Size + SHA256 metadata verifies resume identity; MD5 checks transfer integrity.
        if not self.matches(self.head(key), size, digest):
            raise UploadError('Remote object verification failed')
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise UploadError('Local file changed during upload')
        return 'uploaded', size

def run(args, client_factory=None):
    root = args.root.resolve()
    state = root/'pipeline/cos-upload'
    state.mkdir(parents=True, exist_ok=True)
    # This directory is local state only and is never an upload source.
    lock = (state/'upload.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    records = snapshot(root)
    metadata = json.loads((root/'index.metadata.json').read_text())
    total = int(metadata['total_episodes'])
    if args.require_complete and len(records) != total:
        raise UploadError('Transcoding incomplete; retry after all episodes are ready')
    total_bytes = sum(media_path(root, rel).stat().st_size
                      for r in records for rel in r['videos'].values())
    prefix = args.prefix.strip('/')
    if any(p in ('.','..') for p in prefix.split('/')) or '\\' in prefix:
        raise ValueError('Invalid COS prefix')
    base = f'https://{args.bucket}.cos.{args.region}.myqcloud.com/'
    base += quote(prefix, safe='/')+'/' if prefix else ''
    report = {'episodes':len(records),'total_episodes':total,'video_count':len(records)*2,
              'thumbnail_count':len(records)*2,'video_bytes':total_bytes,
              'public_base_url':base,'dry_run':args.dry_run}
    print(json.dumps(report), flush=True)
    # Publish direct COS URLs, while local disk paths/object keys stay separate.
    for record in records:
        for field in ('videos', 'thumbnails'):
            record[field] = {camera: base + quote(relative, safe='/')
                             for camera, relative in record[field].items()}
    # Temporary public index contains only allowlisted fields, never raw metadata.
    with tempfile.TemporaryDirectory(prefix='public-', dir=state) as directory:
        public = Path(directory)
        index = public/'index.jsonl'
        with index.open('w') as out:
            for record in records:
                out.write(json.dumps(record, ensure_ascii=False, separators=(',',':'))+'\n')
        if args.dry_run:
            # Sanitized sample lets the caller inspect the exact public schema.
            (state/'public-index.sample.json').write_text(json.dumps(records[0],ensure_ascii=False,indent=2)+'\n')
            print('Dry run passed: local paths/schema validated; no thumbnails generated or COS requests made.', flush=True)
            return 0
        if shutil.which('ffmpeg') is None:
            raise UploadError('FFmpeg is required for thumbnail generation')
        if client_factory is None:
            from qcloud_cos import CosConfig, CosS3Client
            if not os.environ.get('COS_SECRET_ID') or not os.environ.get('COS_SECRET_KEY'):
                raise UploadError('Set COS_SECRET_ID and COS_SECRET_KEY in the process environment')
            # Suppress SDK request logging; it may include authentication information.
            logging.getLogger('qcloud_cos').setLevel(logging.CRITICAL)
            config = CosConfig(Region=args.region, SecretId=os.environ['COS_SECRET_ID'],
                               SecretKey=os.environ['COS_SECRET_KEY'],
                               Token=os.environ.get('COS_SESSION_TOKEN'), Scheme='https')
            client = CosS3Client(config)
        else:
            client = client_factory()
        uploader = Uploader(client,args.bucket,prefix,args.attempts,args.overwrite_videos)
        thumbnail_slots = threading.BoundedSemaphore(args.thumbnail_workers)
        def upload_episode(record):
            results = []
            for camera in ('head', 'chest'):
                relative = f"assets/episodes/{record['episode_index']:06d}/{camera}.mp4"
                video = media_path(root,relative)
                thumbnail = generate_thumbnail(video,relative,record['num_frames'],
                                               state/'thumbnails',thumbnail_slots)
                results.append(('video', *uploader.file(video,relative,'video/mp4')))
                results.append(('thumbnail', *uploader.file(
                    thumbnail,str(Path(relative).with_suffix('.jpg')),'image/jpeg')))
            return results
        iterator = iter(records)
        completed = uploaded = skipped = uploaded_thumbnails = skipped_thumbnails = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            active = {}
            def submit():
                record = next(iterator,None)
                if record is not None:
                    active[pool.submit(upload_episode,record)] = record['episode_index']
            for _ in range(args.workers): submit()
            while active:
                finished,_ = wait(active,return_when=FIRST_COMPLETED)
                for future in finished:
                    eid = active.pop(future)
                    try: results = future.result()
                    except Exception as exc:
                        for queued in active: queued.cancel()
                        raise UploadError(f'Episode {eid} upload failed ({safe_error(exc)}); public index unchanged') from None
                    completed += 1
                    uploaded += sum(kind=='video' and status=='uploaded' for kind,status,_ in results)
                    skipped += sum(kind=='video' and status=='skipped' for kind,status,_ in results)
                    uploaded_thumbnails += sum(kind=='thumbnail' and status=='uploaded' for kind,status,_ in results)
                    skipped_thumbnails += sum(kind=='thumbnail' and status=='skipped' for kind,status,_ in results)
                    if completed % 100 == 0 or completed == len(records):
                        print(json.dumps({'completed_episodes':completed,'snapshot_episodes':len(records),
                                          'uploaded_videos':uploaded,'skipped_videos':skipped,
                                          'uploaded_thumbnails':uploaded_thumbnails,
                                          'skipped_thumbnails':skipped_thumbnails}),flush=True)
                    submit()
        # Publish only after BOTH videos AND thumbnails of EVERY episode are verified.
        # Exactly one public index; no auxiliary manifests, state, logs or source data.
        uploader.file(index,'index.jsonl','application/x-ndjson; charset=utf-8',catalog=True)
        report.update({'uploaded_videos':uploaded,'skipped_videos':skipped,
                       'uploaded_thumbnails':uploaded_thumbnails,'skipped_thumbnails':skipped_thumbnails,
                       'index_url':base+'index.jsonl','snapshot_complete':len(records)==total})
        (state/'last-success.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    return 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(DEFAULT_ROOT))
    parser.add_argument('--bucket',default=BUCKET)
    parser.add_argument('--region',default=REGION)
    parser.add_argument('--prefix',default='previews')
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--thumbnail-workers',type=int,default=4)
    parser.add_argument('--attempts',type=int,default=5)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--require-complete',action='store_true')
    parser.add_argument('--overwrite-media','--overwrite-videos',dest='overwrite_videos',
                        action='store_true',help='Allow replacing differing MP4 and JPEG objects')
    args = parser.parse_args()
    if not 1 <= args.workers <= 64 or not 1 <= args.attempts <= 10 or not 1 <= args.thumbnail_workers <= 16:
        parser.error('workers must be 1..64, thumbnail-workers 1..16, and attempts 1..10')
    try: return run(args)
    except (UploadError,ValueError) as exc:
        # These are only locally constructed, non-SDK messages.
        print(f'Upload stopped: {exc}',file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'Upload stopped: {safe_error(exc)}',file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
