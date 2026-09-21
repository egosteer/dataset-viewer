# EgoSteer Dataset Website 数据契约 v1

更新时间：2026-09-21。目标主机：s1。共享目录：`/share_data/zhangtingrui/egosteer-dataset-website/`。

本文定义正在实现的输出接口；文档存在不代表全量视频已生成。前端开发可以按下面的字段开始。实际完成情况以 `progress.json` 和 `index.ready.jsonl` 为准。

2026-09-21 执行状态：全量 index 已生成（54,454 个样本、193 个任务，中文缺失 0）。首批 64 个样本的 128 个视频全部校验通过；32 并发耗时 29.27 秒，采样 FFmpeg 总 RSS 约 4 GiB。首批文件体积相对对应原始 MP4 减少 62.69%（来源裁剪与重编码均有贡献，不代表全量比例）。全量后台任务已启动，进度继续更新。

## 目录布局

```text
egosteer-dataset-website/
├── DATA_LAYOUT.md             # 本数据契约
├── index.jsonl                # 全量 54,454 个最终样本，每行一个 JSON 对象
├── index.ready.jsonl          # 仅双相机均转码、校验完成的样本；字段与 index.jsonl 相同
├── index.metadata.json        # schema_version、来源、数量、编码参数等
├── tasks.json                 # 正式任务名及样本数，用于筛选器
├── progress.json              # 原子更新的处理进度
├── assets/
│   └── episodes/
│       ├── 000000/
│       │   ├── head.mp4       # 头部 RGB
│       │   └── chest.mp4      # 胸部 RGB
│       └── 000001/...
└── pipeline/                 # 后台生成工具，不作为网站静态资源发布
    ├── prepare.py
    ├── transcode.py
    ├── jobs.sqlite           # 转码输入片段、断点状态、错误
    └── transcode.log
```

所有视频相对路径以此目录为根，包含 `assets/` 前缀。例如将该目录挂载为 `/dataset/` 后，视频 URL 为 `/dataset/assets/episodes/000000/head.mp4`。

## 样本索引格式

UTF-8 JSON Lines，禁止把整文件当成一个 JSON 数组解析。每行是完整对象。下面只展示 episode 0 的部分指令说明字段，实际输出会保留全部文本：

```json
{
  "schema_version": 1,
  "episode_index": 0,
  "rrd_path": "/share_data/yifan/vla-teleop-data/Arrange_magnets_by_color/episode_000000.rrd",
  "task_name_original": "Arrange_magnets_by_color",
  "task_name": "Arrange Magnets of the Same Color in a Row on the Whiteboard",
  "split": "train",
  "num_frames": 642,
  "fps": 30,
  "duration_seconds": 21.4,
  "videos": {
    "head": "assets/episodes/000000/head.mp4",
    "chest": "assets/episodes/000000/chest.mp4"
  },
  "annotations": {
    "en": ["Attach the two yellow magnets and the two red magnets on the left side of the table to the white board in the center respectively."],
    "zh": ["此处为原始人工中文标注；实际文件保存原文，不自动翻译。"]
  },
  "annotation_sources": [
    {
      "rrd_path": "/share_data/yifan/vla-teleop-data/Arrange_magnets_by_color/episode_000000.rrd",
      "role": "primary",
      "annotation_id": 138086,
      "annotation_jsonl_path": "/share_data/zhangtingrui/xiaozi-webui-test/django_annotation_backend/annotations_20260618_dice_fixed_6.jsonl",
      "annotation_line_one_based": 100,
      "en": ["示意：该来源标注中的 annotation.text.labels 原文"],
      "zh": ["示意：该来源标注中的 annotation.text.texts 原文"]
    }
  ],
  "duplicate_rrd_paths": [],
  "instruction_metadata_path": "/share_data/yifan/EgoSteer-RealWorld/meta/episodes/chunk-000/file-000.parquet"
}
```

示例中的中文、行号、指令列表和 duplicate 列表为说明用途，不是可直接用于生产的 episode 0 完整记录。请用生成的 index 中记录作为真实数据。

| 字段 | 约定 |
| --- | --- |
| `episode_index` | 最终数据集全局整数 ID；网站主键。目录名补足六位；不要用原始 episode 文件名作主键。 |
| `rrd_path` | 原始 RRD 绝对路径，仅供溯源，不是 HTTP URL。包含主目录、multitask 目录和更深的日期目录。 |
| `task_name_original` | 转换前的源任务名。 |
| `task_name` | 经官方映射修正后的英文任务名，建议作为界面标题和筛选字段。 |
| `split` | `train` 或 `val`。 |
| `num_frames`, `fps`, `duration_seconds` | 最终导出片段的帧数、帧率和时长；时长为帧数 / fps。 |
| `videos.head`, `videos.chest` | 网站专用 MP4 相对路径；胸部相机统一叫 `chest`，原始目录中的 `_breast.mp4` 不直接用于这些输出。 |
| `annotations.en` | 最终开源数据 episode metadata 的英文 instructions，原样保留顺序。 |
| `annotations.zh` | 主样本及合并重复样本的中文标注，按来源顺序汇总、去空项和精确去重，不生成新翻译。 |
| `annotation_sources` | 各原始标注的完整中英文数组及溯源；`role` 为 `primary` 或 `duplicate`。 |
| `duplicate_rrd_paths` | 已归并到当前样本的重复 RRD 路径；这些不是额外的网站样本。 |
| `instruction_metadata_path` | 最终英文 instructions 所在的 episode parquet 文件。用 episode_index 查找行。 |

**中英文数组不保证长度相同或逐项对应。** 最终英文经过合并、去重，中文保留原始标注。界面应切换中英文列表展示，不要直接 zip 两个数组做逐句翻译。需要原始配对上下文时使用 annotation_sources，并检查对应数组长度。

`annotations.zh` 若没有可用原始中文则为 `[]`；准备步骤会统计缺失数量，不填充机器翻译。无效或找不到的标注来源会阻止准备完成，以免静默丢失。

## 网站如何读取

1. 转码期间优先使用 `index.ready.jsonl`，其中每条记录都已有可播放的两路视频。顺序是完成顺序，不保证按 ID 递增。
   读取运行中的文件时，只消费以换行符结束的完整 JSON 行；末尾尚未写完的行留到下次。断点续跑时 ready 索引会由数据库重建，按 episode_index 去重即可。
2. `index.jsonl` 从准备阶段起包含全量记录，只说明计划资源路径，**不能据此认定视频已存在**。
3. 后端导入 JSONL 后按 task_name、episode_index、split 分页查询，返回当前页。不要让浏览器启动时解析全量带溯源信息的索引。
4. 列表页按需加载视频；详情页显示 head/chest 两路，并可共享播放、暂停和定位控制。
5. HTML video 建议 `controls playsinline preload="none"`；用户打开详情后再加载。双相机以相同 episode 的时间零点对齐。
6. MP4 使用 H.264 / yuv420p，640×480，30 fps，CRF 26，preset medium，faststart，无音轨。素材来自最终导出 RGB 分片，按 metadata 时间裁切与帧数约束。
7. 静态媒体服务器应支持 HTTP Range 和 `video/mp4`。绝对 RRD/标注路径只留在后台索引，公开 API 按需选取字段。

## 辅助文件约定

`tasks.json` 为数组：

```json
[{"task_name": "Stand the Screw Upright", "episode_count": 305}]
```

任务数是全量样本数，不代表已完成转码数。实际字段内容以生成文件为准。

`progress.json` 包含：

```json
{
  "status": "running",
  "updated_at": "2026-09-21T00:00:00+00:00",
  "total_episodes": 54454,
  "ready_episodes": 0,
  "failed_episodes": 0,
  "pending_episodes": 54454,
  "workers": 32,
  "threads_per_codec": 2,
  "ffmpeg_memory_limit_mib": 2048
}
```

`status` 取值：`prepared` / `running` / `completed` / `completed_with_errors`。`pending_episodes` 包含尚未完成的运行中样本。失败记录及原因在 jobs.sqlite；ready 索引不包含失败或半完成样本。

## 执行边界

源目录和最终导出数据保持只读；仅写目标网站目录。32 个工作进程，每个工作进程一次运行一个 FFmpeg，解码和编码各限制 2 线程，filter 限制 1 线程，单 FFmpeg 虚拟内存上限 2 GiB。先写临时 MP4，校验帧数、尺寸、编码及文件非空后原子重命名；两路都成功才写入 ready 索引。支持断点续跑。

这里的工作进程数指并发 FFmpeg 子进程数，由 Python 有界线程池调度。每个 FFmpeg 还有少量内部管理线程，2 线程限制分别作用于编码器和解码器，不表示整个进程只有两个操作系统线程。当前 s1 可见 124 个逻辑 CPU，容器 CPU 配额为 120 核。

## 查看进度与断点续跑

```bash
ssh s1 'cat /share_data/zhangtingrui/egosteer-dataset-website/progress.json'
ssh s1 'tail -n 5 /share_data/zhangtingrui/egosteer-dataset-website/pipeline/transcode.log'
```

现有任务已在后台运行，不要重复启动。进程锁会拒绝并发启动另一个 runner。若进程退出后需要恢复或重试失败项，在 s1 执行：

```bash
nohup python3 /share_data/zhangtingrui/egosteer-dataset-website/pipeline/transcode.py \
  --workers 32 >> /share_data/zhangtingrui/egosteer-dataset-website/pipeline/transcode.log 2>&1 < /dev/null &
```

已完成的 episode 从 jobs.sqlite 直接跳过；半完成样本校验已有一路后继续另一路。不要重新执行 prepare.py 覆盖数据库；prepare.py 本身也会拒绝覆盖已有 jobs.sqlite。
