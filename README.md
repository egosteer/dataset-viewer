# EgoSteer Dataset Browser

A Vite + Vue 3 dataset browser with head-camera preview grids, animated transitions to a thumbnail list and dual-camera detail view, synchronized playback, and original English/Chinese annotations. Animations use Motion for Vue.

## Run locally

Requires Node.js 20.19+ (or 22.12+) and FFmpeg on PATH. Dataset files are supplied separately and are not included in this repository.

```bash
npm ci
DATASET_DIR=/absolute/path/to/dataset npm run dev -- --port 5174
```

Open http://127.0.0.1:5174. The dataset directory must contain `index.ready.jsonl`, `tasks.json`, `progress.json`, and `assets/`, following [DATA_LAYOUT.md](DATA_LAYOUT.md). Only ready episodes appear in the browser. Without `DATASET_DIR`, the server uses `data/preview/`; a fresh clone does not include that local preview.

## Build and serve

```bash
npm test
npm run build
DATASET_DIR=/absolute/path/to/dataset PORT=4173 npm start
```

The server binds to `127.0.0.1`. Use a reverse proxy for public hosting. The frontend needs the accompanying Node API and media server; `dist/` alone is not a complete deployment. `npm run preview` also includes the API.

- `DATASET_DIR`: directory containing the ready index and videos.
- `FFMPEG_PATH`: optional FFmpeg executable path.
- `THUMBNAIL_DIR`: optional writable thumbnail cache directory (defaults to `data/thumbnails/`).

The API paginates episodes and strips internal provenance fields. Video serving supports HTTP Range. Thumbnails are generated on demand from the first frame, cached locally, and limited to two concurrent FFmpeg jobs. Only the selected episode's two videos load in the browser.

The Python tools under `scripts/` are maintainer utilities for the original dataset environment; they are not required to run the viewer against an existing dataset. `npm run samples` additionally needs SSH access to `s1`, a prepared `data/discovery.jsonl`, and local/remote FFmpeg.

Generated datasets, SQLite catalogs, videos, thumbnails, dependencies, build output, and environment files are excluded from Git.

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
