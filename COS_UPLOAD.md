# COS preview upload script

Script: `scripts/upload_cos.py`. Dependencies: `scripts/requirements-cos.txt` and FFmpeg available on PATH for JPEG extraction.

The user authorized execution on 2026-09-21 after conversion completed (54,454 ready episodes, no failures; 61,130,763,986 video bytes). The uploader was launched on s1 with 32 upload workers and 8 thumbnail workers. Follow `pipeline/upload_cos.log` and `pipeline/cos-upload/last-success.json` for actual progress/completion; launch alone does not imply all files were uploaded. Credentials are passed through a private stdin pipe into process memory and are not embedded in source, documentation, or configuration files.

## Verified launch status (2026-09-21)

The first 1,000 episodes (2,000 MP4s + 2,000 JPEGs) uploaded successfully and passed authenticated HEAD verification. The process continues in the background; the final index is not published until all media completes. Log: `/share_data/zhangtingrui/egosteer-dataset-website/pipeline/upload_cos.log`; PID at launch: 109092.

Anonymous reads of the newly uploaded episode 000000 MP4/JPEG returned HTTP 403, including a JPEG GET without an Origin header. This is a public-access issue in addition to the previously failing GitHub-origin CORS preflight. No bucket/object ACL or CORS settings were changed.

## Exact upload allowlist

Defaults: bucket `ego-steer-1351596430`, region `ap-shanghai`, key prefix `previews`.

```text
previews/
├── index.jsonl
└── assets/episodes/{episode_index:06d}/
    ├── head.mp4
    ├── head.jpg
    ├── chest.mp4
    └── chest.jpg
```

Only these object types are uploaded. No directory recursion. No tasks.json, latest.json, metadata manifests, private indexes, SQLite files, logs, scripts, environment snapshots, RRD files, or annotation-source files are uploaded. Bucket policy and ACLs are not changed; objects inherit the existing public-read policy.

The public index is derived from a fixed snapshot of `index.ready.jsonl`; only completed episodes with both videos are eligible. Each public record contains:

```text
schema_version, episode_index, task_name_original, task_name, split,
num_frames, fps, duration_seconds,
videos: {head, chest}, thumbnails: {head, chest}, annotations: {en: [...], zh: [...]}
```

Each JPEG has the same object path and basename as its MP4, with `.mp4` replaced by `.jpg`. Both fields in the public index are **absolute HTTPS COS URLs**, for example:

```json
{
  "videos": {"head": "https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/assets/episodes/000000/head.mp4"},
  "thumbnails": {"head": "https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/assets/episodes/000000/head.jpg"}
}
```

Both camera entries are present in real records. The MP4 remains available under `videos.head`; local source paths and COS object keys are kept separate from public URLs.

At upload time, FFmpeg extracts frame `min(30, num_frames // 2)` (near one second, or the midpoint for a short clip), at width 640 with preserved aspect ratio and JPEG quality `-q:v 3`. Both cameras use the same timestamp. JPEGs are atomically cached by source content under local `pipeline/cos-upload/thumbnails/` for reruns, then uploaded as `image/jpeg`. The private input index is not modified; only the derived public index gains `thumbnails`.

`rrd_path`, `annotation_sources`, `duplicate_rrd_paths`, and `instruction_metadata_path` are deliberately excluded from this public index. They remain in the private server-side index for traceability. English and Chinese arrays are not guaranteed to align sentence by sentence.

Media URLs are constructed from the configured bucket, region and prefix. The local private input index keeps relative paths. Expected public index URL after a future successful upload: `https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/index.jsonl`.

The frontend is a static GitHub Pages app. It reads this public index and uses its media URLs directly; the Express server is for local debugging only. COS must allow cross-origin index reads from the Pages origin (`https://egosteer.github.io`); see README for CORS details. The uploader does not change CORS or ACL settings.

## Execution instructions for later review

The SDK and uploader are installed under the target server's `pipeline/` directory. The commands below document manual setup/resume; do not launch a second uploader while one is running.

```bash
cd /share_data/zhangtingrui/egosteer-dataset-website
python3 -m venv pipeline/.venv-cos
pipeline/.venv-cos/bin/pip install -r pipeline/requirements-cos.txt

# Enter credentials interactively in Bash, without placing literal keys in shell history.
read -r -s -p 'COS SecretId: ' COS_SECRET_ID; echo
read -r -s -p 'COS SecretKey: ' COS_SECRET_KEY; echo
export COS_SECRET_ID COS_SECRET_KEY

# Optional later review: validates paths/schema; no JPEG generation or COS requests.
pipeline/.venv-cos/bin/python pipeline/upload_cos.py --dry-run --require-complete

# This command actually uploads. Run only after reviewing the public schema and prefix.
pipeline/.venv-cos/bin/python pipeline/upload_cos.py --workers 16 --thumbnail-workers 4 --require-complete

unset COS_SECRET_ID COS_SECRET_KEY
```

Use `COS_SESSION_TOKEN` as well if using temporary credentials. Omitting `--require-complete` uploads only the ready snapshot captured at startup; rerun later to include newly completed videos. The default source root is `/share_data/zhangtingrui/egosteer-dataset-website`; `--root`, `--bucket`, `--region`, and `--prefix` override defaults.

## Reliability and resource limits

- Default 16 concurrent episode uploads, one active video per worker, SDK multipart `MAXThread=1`, 8 MiB parts. SHA-256 reads in 1 MiB chunks; entire videos are never loaded into memory.
- Thumbnail extraction has a separate cap of 4 simultaneous FFmpeg processes (configurable with `--thumbnail-workers`), each with decoder, encoder and filter threading restricted to 1, and a 60-second timeout. No FFmpeg runs in dry-run mode.
- Uses the official `qcloud_cos.CosS3Client.upload_file`, `EnableMD5=True`, and post-upload HEAD verification of size and SHA-256 metadata.
- On rerun, HEAD + matching size/SHA-256 metadata skips an already uploaded MP4 or JPEG. Existing differing media stops the run unless `--overwrite-media` is explicitly supplied (`--overwrite-videos` remains an alias and applies to both formats). This is object-level resume; do not assume a partial individual MP4 resumes from its last byte.
- Retries transient failures with exponential backoff; authentication and other nonretryable 4xx errors stop. SDK raw request/exception details are not printed.
- Video or thumbnail generation/upload failures prevent publication of the new index. Some verified media objects may already have uploaded; rerunning safely discovers them.
- Only after every video and thumbnail referenced by the captured index is verified does the script replace `previews/index.jsonl`. An existing index may be replaced with a smaller snapshot if the input ready index is smaller; use `--require-complete` for final publication and a fresh `--prefix` for experimental snapshots.
- Internal upload locks, optional sanitized sample, and success summaries live under local `pipeline/cos-upload/` and never enter COS.
- An earlier instruction prohibited execution; the later explicit request to start uploading superseded it. Bucket CORS/ACL settings remain unchanged.

SDK references: [Tencent Python SDK setup](https://cloud.tencent.com/document/product/436/12269), [Python upload API](https://cloud.tencent.com/document/product/436/65820).
