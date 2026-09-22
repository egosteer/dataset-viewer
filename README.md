# EgoSteer Dataset Browser

A Vite + Vue 3 dataset browser with head-camera preview grids, animated transitions to a thumbnail list and dual-camera detail view, synchronized playback, and original English/Chinese annotations. Animations use Motion for Vue.

## GitHub Pages + COS

Production is a static site: publish `dist/` on GitHub Pages. The browser fetches the sanitized COS JSONL index, falling back to a bundled gzip snapshot if COS fails, times out after 15 seconds, or returns an invalid/empty catalog. It decompresses, parses and queries the catalog in a Web Worker, and uses the absolute video/thumbnail URLs in each record. No Node backend, local dataset, FFmpeg, API proxy, or credentials are required for the hosted frontend. The index is downloaded once per page session; parsing runs outside the UI thread.

Default index: `https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/index.jsonl`. Set `VITE_DATASET_INDEX_URL` at build time to override it. The frontend expects the public index produced by [upload_cos.py](scripts/upload_cos.py), including absolute HTTPS `videos` and `thumbnails` URLs. The bundled fallback is the same sanitized schema; it never uses the local debug API in production.

The COS upload completed: 108,908 MP4s and 108,908 JPEGs. On 2026-09-22, media URLs are publicly readable with GitHub-origin CORS, while the COS index still returns 403. The bundled fallback allows browsing without access to that remote index. Video playback and thumbnails still require COS media access.

### Bundled index snapshot

`src/catalog/snapshot/index.jsonl.gz` contains all 54,454 published episodes, including English/Chinese annotations and absolute COS media URLs, with internal paths and provenance removed. Its original JSONL size is 63,006,216 bytes (63.01 MB); the gzip download is 4,508,840 bytes (4.51 MB), 92.84% smaller. Vite emits a content-hashed static asset, so new snapshots receive a new cache URL. GitHub Pages serves it alongside the frontend; no COS credentials are required. Decompression uses the browser’s DecompressionStream API inside the worker.

To regenerate after a verified complete upload, run from the repository root:

```bash
ssh s1 'python3 -' < scripts/export_static_index.py > src/catalog/snapshot/index.jsonl.gz.partial
# Only on successful export, rename .partial to index.jsonl.gz, then test/build.
```

The exporter validates the successful full-upload record and public field allowlist. It never uploads or bundles the raw private index.

### Build / preview

Requires Node.js 20.19+ or 22.12+. CI uses Node 22.

```bash
npm ci
npm test
npm run build
npm run preview
```

`npm run dev` also uses COS by default. Relative built asset paths support both `/` and `/dataset-viewer/`, including the catalog worker. No history-based routing or special 404 rewrite is required.

### GitHub Pages deployment

The existing repository remote is `https://github.com/egosteer/dataset-viewer.git`. The workflow in `.github/workflows/pages.yml` builds and publishes **only dist/** on pushes to main or a manual workflow dispatch. It never invokes Python, accesses COS write credentials, or uploads dataset files. The repository owner made this repository public on 2026-09-22, and GitHub Pages is enabled with GitHub Actions as the build source. Pushes to main trigger the deployment workflow.

In repository **Settings → Pages**, select **GitHub Actions** as the source. The expected project URL is `https://egosteer.github.io/dataset-viewer/`. An optional Actions repository variable `VITE_DATASET_INDEX_URL` overrides the default public index URL. Do not place COS SecretId/SecretKey into frontend variables or this deployment workflow.

### COS cross-origin access

The index fetch requires COS CORS to allow origin `https://egosteer.github.io` (an origin has no repository path), with methods GET and HEAD. Allow `http://127.0.0.1:5173` and `http://localhost:5173` too if using those local development URLs; add the exact origin for other ports or a future custom domain. Range can be allowed as a request header, and Content-Length, Content-Range, Accept-Ranges and ETag exposed when needed. Cross-origin reads are unauthenticated. No bucket CORS/ACL changes have been made by this task.

References: [Vite GitHub Pages deployment](https://vite.dev/guide/static-deploy.html#github-pages), [Tencent COS CORS](https://cloud.tencent.com/document/product/436/13318).

## Local dataset debugging only

The original Express API, local file serving and on-demand FFmpeg thumbnails are retained only for an explicit local debug session:

```bash
DATASET_DIR=/absolute/path/to/dataset npm run debug -- --port 5174
```

`npm start` is an alias for this debug mode. The debug server binds to `127.0.0.1`; no public hosting/reverse proxy is needed. The dataset directory must contain `index.ready.jsonl`, `tasks.json`, `progress.json`, and `assets/` per [DATA_LAYOUT.md](DATA_LAYOUT.md). Without DATASET_DIR it uses `data/preview/`, which is not included in Git. FFmpeg is needed only for local debug thumbnails. `FFMPEG_PATH` and `THUMBNAIL_DIR` remain supported.

Local API middleware is enabled only in `npm run debug` (or an explicit `VITE_DATA_SOURCE=local` development session). Static preview has no API middleware, and builds reject local-data mode. `server/start.js` is a legacy loopback-only debug helper, not a production backend.

Python preparation/transcoding/upload scripts are separate maintainer tools and are never required by GitHub Pages. Generated data, upload state, media, dependencies, build output, and environment files are excluded from Git.

## Original dataset preparation notes

The following records describe the original data audit and infrastructure, not prerequisites for installing the browser.

本目录独立于相邻的 `egosteer/` 网站。最初只读排查结果和本地目录库保存在本目录；随后授权的中英文索引与 FFmpeg 压缩任务在 s1 的 `/share_data/zhangtingrui/egosteer-dataset-website/` 执行。网站开发请遵循 [DATA_LAYOUT.md](DATA_LAYOUT.md)，该文件也已同步到远端目标根目录。下文是初始排查记录；其中 `egosteer-data-website` 是旧规划名，实际输出目录以新契约的 `egosteer-dataset-website` 为准。

## 2026-09-21 核查结果

- 54,454 个最终样本，193 个正式任务，121,171 条最终英文指令。
- 主目录 53,733 个样本，multitask 目录 721 个样本；1,635 个样本使用重复样本合并指令。
- FINAL_kept、plan、provenance、最终 episode metadata 数量一致；FINAL_kept 与实际导出路径集合完全一致。
- 全部 RRD 存在；108,908 个原始 RGB MP4 和对应导出 RGB 文件均存在且非空。原始头部视频 75,831,320,185 字节，胸部视频 78,785,730,717 字节，合计 154,617,050,902 字节（154.62 GB / 144.00 GiB）。这是文件存在与大小检查，不等同于全量视频解码检查。
- 5 份输入文件 SHA-1 均匹配 environment 快照；正式任务名均匹配映射；最终指令均匹配导出计划。
- 44 条输入指令列表差异均已解释，见下文；未发现其他采集异常。
- SQLite 完整性、外键、唯一性、每样本双相机和非空指令检查通过。

## 来源与关联

所有远端路径均在 SSH 主机 `s2`。

| 内容 | 权威位置 / 关联方式 |
| --- | --- |
| 导出环境与输入指纹 | `/share_data/yifan/EgoSteer-RealWorld.private/environment.json` |
| 最终 QC 保留名单 | `/share_data/yifan/qc_lists/v3/FINAL_kept.txt`，绝对 RRD 路径 |
| 实际导出样本溯源 | `/share_data/yifan/EgoSteer-RealWorld.private/provenance.parquet`，`episode_index → source_path` |
| 导出计划 | `/share_data/yifan/EgoSteer-RealWorld.private/plan.json`，任务、instructions、重复来源 |
| 正式任务名 | `/share_data/yifan/EgoSteer-task-name-mapping-English.csv`，UTF-8 BOM，`current_task_name → official_task_name` |
| 原始标注 | `/share_data/zhangtingrui/xiaozi-webui-test/django_annotation_backend/annotations_20260618_dice_fixed_6.jsonl`，英文 `annotation.text.labels`，中文 `annotation.text.texts` |
| 重复样本合并指令 | `/share_data/yifan/qc_lists/v3/duplicate_merged_instructions.json`，以绝对 RRD 路径索引，取 `instructions` |
| 最终导出指令、视频片段 | `/share_data/yifan/EgoSteer-RealWorld/meta/episodes/chunk-*/file-*.parquet`，按 `episode_index` 关联 |
| 最终任务目录 | `/share_data/yifan/EgoSteer-RealWorld/meta/tasks.parquet` |

以实际导出 provenance + episode metadata 作为网站样本来源，核对 FINAL_kept 和 plan。不要自行使用 `quality` 或 `discard` 再次筛选，避免改变已定稿集合。数据库保存最终 metadata 的全部 instructions，不只取第一句；合并重复样本带来的额外指令也保留。每条指令来源可追溯到 metadata 文件及行、标注文件行号与 annotation ID、合并 JSON key。

注意除了 `/share_data/yifan/vla-teleop-data/`，实际导出还包含 `/share_data/yifan/vla-teleop-data-multitask/`。后者标注相对路径带 `vla-teleop-data-multitask/` 前缀，不能只按文件名或 task/episode 配对。

## 视频与隔离目录

原始 RRD 同目录下 `episode_XXXXXX_head.mp4` 对应头部相机，`episode_XXXXXX_breast.mp4` 对应胸部相机。网站与最终导出统一使用 `head` / `chest`，原始文件名保留 `breast`。

导出 RGB 路径为 `/share_data/yifan/EgoSteer-RealWorld/videos/observation.images.{head|chest}/chunk-XXX/file-XXX.mp4`。这是多 episode 拼接视频，必须使用 metadata 中各相机的 `from_timestamp` / `to_timestamp` 切片，不能把整个文件当成单个样本。数据库已保存各自时间范围。

压缩输出规划为 `/share_data/zhangtingrui/egosteer-data-website/assets/episodes/{episode_index:06d}/{head|chest}.mp4`。使用全局 episode_index，避免不同目录同名 episode 冲突；所有输出状态为 `planned`，路径不表示视频已生成。

抽查 episode 0：原始 head/chest 为 H.264、640×480、30fps，时长分别 21.767/21.800 秒，最终导出片段为 21.4 秒。因此后续若要求与最终开源数据严格一致，应优先从导出 RGB 片段转码；若使用原始 MP4，需要先核查裁剪与同步规则。尚未全面解码验证视频，也未确定压缩参数或估算压缩后体积。

## 本地产物与重建

`data/catalog.sqlite` 是私有后台目录库；`data/audit.json` 为完整覆盖统计、异常和 SHA-1 输入校验；`data/discovery.jsonl` 是原始采集流，采集中使用 `.partial` 后缀，只有以 audit 记录结尾且构建成功后才改名。数据已被本目录 `.gitignore` 忽略，未来发布网站时不要直接公开这些带内部绝对路径的文件。

```bash
cd /Users/andy/Develop/egosteer-website/dataset-viewer
ssh s2 'python3 -' < scripts/discover_remote.py > data/discovery.jsonl.partial
python3 scripts/build_database.py
```

远端脚本仅使用读取接口，依赖 s2 已安装的 pyarrow，不安装任何软件。SQLite 构建在本地执行，检查最终 audit 标记、数量、主键、外键、每条样本的双相机和非空 instructions，成功后替换数据库。

数据库表：`episodes`（正式任务名、源目录名、RRD、split、帧数、时长、来源与异常），`instructions`（episode + ordinal + 文本），`videos`（双相机原始/导出位置、导出片段时间、拟输出位置与状态），`audit`（采集审计 JSON）。按任务建索引，后续 API 可分页查询，避免前端加载全量清单。压缩完成并验证后再更新 asset 状态，并生成不包含内部路径的公开 API/manifest。

`instruction_input_mismatch` 表示最终列表与输入列表原样比较有差异，并不表示样本错误或需要排除。另行全量对照 plan 与标注/合并输入，44 条有变化：42 条可由去空白、去空项或精确去重解释；episode 9111 和 9121 则是 `Juice`/`juice` 大小写重复被合并。详情见 `data/instruction-normalization-audit.json`。保留最终导出的列表，不重新加入重复指令。

环境快照里的代码仓库 `/share_data_exp/yifan/egosteer-data-convert` 在本次 s2 上不存在；不影响当前 metadata/provenance 索引，但后续研究导出裁剪逻辑时需要定位该代码。
