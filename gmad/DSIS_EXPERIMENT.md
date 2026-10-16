# DSIS 主观实验（MATLAB / Psychtoolbox）

用 DSIS（双刺激损伤量表，ITU-R BT.500）给 gMAD 选出的视频打分：每个 trial 先播放 reference，再播放 test，被试按 1–5 分评价 test 相对 reference 的损伤程度。

实验由两个 MATLAB 文件组成：

| 文件 | 做什么 |
| --- | --- |
| [`run_dsis_gmad_480p1080p.m`](run_dsis_gmad_480p1080p.m) | 实验程序本体：读视频列表、播放、打分、保存、续跑。直接运行时先让你选一个场景，只播放这个场景的视频。 |
| [`run_dsis_version_a.m`](run_dsis_version_a.m) | 一个很短的入口：让 `run_dsis_gmad_480p1080p.m` 一次播放 Version A 的全部 239 个视频（13 个场景混在一起随机播放）。 |

两者播放的视频都来自同一个 recipes 文件（见[下文](#recipes-文件)），区别只在于播放全部场景还是一个场景，以及结果写在哪个目录：

| 运行 | 播放的视频 | 结果目录 |
| --- | --- | --- |
| `run_dsis_gmad_480p1080p`，选一个场景 | 该场景在 Version A 里的 15–20 个视频 | `results/dsis_version_a_<场景>/` |
| `run_dsis_version_a` | Version A 全部 239 个视频 | `results/dsis_all_shots_version_a/` |

实验设置（时长、每次多少个 trial、字号等）都在 `run_dsis_gmad_480p1080p.m` 开头的 **User settings** 里，两种运行方式共用。

## 每个 trial 的流程

1. 灰屏 "Reference"（1 s）
2. reference 视频：该 shot 的 1080p120，3 个 chunk 共 4.5 s
3. 灰屏 "Test"（1.5 s）
4. test 视频：3 个 1.5 s chunk，各自的分辨率和帧率，共 4.5 s
5. 打分界面

视频直接从 HEVC chunk 文件逐帧读取，按各自的原生帧率（30/60/120 fps）在 120 Hz 屏幕上显示（低帧率靠重复帧），用 GPU 双线性缩放到全屏，不做插帧。同一个 shot 的连续 trial 不重新加载 reference。

### 打分量表和按键

| 分数 | 屏幕上的描述 |
| --- | --- |
| 5 | Excellent - Imperceptible |
| 4 | Good - Perceptible, but not annoying |
| 3 | Fair - Slightly annoying |
| 2 | Poor - Annoying |
| 1 | Bad - Very annoying |

| 按键 | 作用 |
| --- | --- |
| `1`–`5`（键盘上排数字键） | 选分数，选中的一行高亮 |
| `Enter` | 确认分数，进入下一个 trial（必须先选分） |
| `R` | 重播这个 trial 的 reference 和 test |
| `Esc` | 退出（已确认的分数都已保存，可以续跑） |

屏幕文字只有英文。

## 怎么运行

先在 MATLAB 里进入 `VQA2-gmad-pooling/gmad`。

### 单个场景：`run_dsis_gmad_480p1080p`

在编辑器里点 **Run**（或在命令窗口输入 `run_dsis_gmad_480p1080p`），命令窗口会列出场景：

```
Scenes in Version A:
   1  bistro     18 videos, 1 shot(s)
   2  car        20 videos, 3 shot(s)
   ...
  13  spiderman  18 videos, 3 shot(s)
Scene (number or name):
```

输入编号或场景名，然后输入被试编号（见[被试编号](#被试编号)），实验开始。

不想回答问题时，可以把参数直接写上：

```matlab
run_dsis_gmad_480p1080p('S01', false, false, [], [], 'bistro')        % 正式实验
run_dsis_gmad_480p1080p('S01', true,  false, [], [], 'bistro')        % 只检查文件，不开窗口
run_dsis_gmad_480p1080p('S01', false, true,  [], [], 'bistro')        % 窗口模式预览
```

参数依次是：被试编号、只检查、窗口预览、recipes 文件、结果目录、场景。recipes 文件和结果目录留空 `[]` 时用 Version A 和 `results/dsis_version_a_<场景>/`。也可以传入任何其他 recipes 文件和结果目录，例如 bistro 单独跑 gMAD 时选出的 209 个视频：

```matlab
run_dsis_gmad_480p1080p('S01', false, false, ...
    '../results/gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted/selected_video_recipes.json', ...
    '../results/dsis_bistro_480p720p1080p')
```

### 全部场景：`run_dsis_version_a`

```matlab
run_dsis_version_a            % 点 Run 也一样：只问被试编号
run_dsis_version_a('S01')     % 正式实验
run_dsis_version_a('S01', true)         % 只检查文件
run_dsis_version_a('S01', false, true)  % 窗口模式预览
```

### 正式实验前

- 先运行一次"只检查"模式，确认所有视频文件都在（会显示 `Validated N gMAD-selected videos ...`）。
- 正式实验用全屏（`FULL_SCREEN = true`，默认）和 120 Hz 显示器。窗口模式只用于检查流程，计时不可靠。
- 每个 trial 结束后命令窗口会打印 `skipped samples ref/test=...`，正式实验时应接近 0；如果很大，说明解码跟不上（例如 GPU 被其他程序占用）。
- 多显示器时，刺激显示器的 DPI 应与主显示器一致，否则 Psychtoolbox 全屏同步可能失败。

## 被试编号、分 session 和续跑

### 被试编号

不带编号运行时，程序会建议下一个没用过的编号：

```
Subject ID [Enter = S03_20261016, or the same ID to resume]:
```

- **新被试**：直接按回车，使用建议的编号（`S<序号>_<日期>`，序号取该结果目录里已有 `S<数字>` 编号的最大值加 1）。
- **续跑**：输入这个被试上次的**完整**编号（含日期）。直接回车会得到新编号，变成一个新被试从头开始。
- 编号只能包含字母、数字、`_`、`-`。每个结果目录单独编号，所以同一个人在不同场景可以都是 `S01`。

在命令行自己指定编号时（如 `run_dsis_version_a('S01')`）不会给出建议，也不检查重名：已存在的编号一律当作同一个人续跑。

### 分 session

`SESSION_TRIALS = 120`：一次运行最多做 120 个 trial（约 30 分钟），做完显示 "Session finished" 并退出。用同一个编号再运行，从下一个未打分的视频继续。`BREAK_EVERY = 40`：同一次运行里每 40 个 trial 显示一次休息画面，按 Enter 继续。

### 续跑

每确认一个分数就立即写入 CSV。按 `Esc`、程序出错或分 session 结束后，用同一个编号重新运行即可：顺序沿用 `_order.csv`，已打分的视频自动跳过，不会重复或遗漏。

## 输出文件

每个被试在结果目录里有两个文件（以 `S01` 为例）：

**`S01_order.csv`**：第一次运行时生成的随机播放顺序，之后不再改变。

| 列 | 内容 |
| --- | --- |
| `trial` | 播放位置 1…N |
| `candidate_id` | 视频名 |
| `seed` | 生成这个顺序的随机种子 |

**`S01_ratings.csv`**：每确认一个分数追加一行。

| 列 | 内容 |
| --- | --- |
| `subject` | 被试编号 |
| `seed` | 播放顺序的随机种子（同 `_order.csv`） |
| `trial` | 该视频在播放顺序里的位置 |
| `candidate_id` | 视频名，例如 `forza__forza_2__480p120-1080p30-1080p30` |
| `chunk1`、`chunk2`、`chunk3` | 三段的分辨率和帧率 |
| `score` | 1–5 |
| `replays` | 按 `R` 重播的次数 |
| `rating_time_s` | 从打分界面出现到确认的秒数 |
| `reference_skipped_samples`、`test_skipped_samples` | 播放时因解码不及时而跳过的帧数，正常应接近 0 |
| `timestamp` | 确认时间 |

## recipes 文件

recipes 文件告诉实验程序**播放哪些视频、每个视频由哪些文件组成**。它是一个 JSON 列表，每个 test 视频一条记录，文件里有几条记录就有几个 trial。两个实验用的都是 Version A 的 recipes：

```
results/gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted/selection_all_scenes/video_recipes.json
```

它由 [`build_selection_versions.py`](build_selection_versions.py) 从 28 个 shot 的 gMAD 结果中选出（Version A：13 个场景各 10 对视频，共 130 对、239 个不同视频），选法见同目录下的 `selection_versions.html`。

一条记录（路径已缩短）：

```json
{
  "candidate_id": "heros3__heros3_02__480p30-1080p120-1080p60",
  "scene": "heros3__heros3_02",
  "chunk1": "480p30", "chunk2": "1080p120", "chunk3": "1080p60",
  "is_fixed": false,
  "switches": 2,
  "source_videos": [
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/videos/chunk1_480p30_lossless_hevc.mp4",
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/videos/chunk2_1080p120_lossless_hevc.mp4",
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/videos/chunk3_1080p60_lossless_hevc.mp4"
  ],
  "source_references": [
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/references/ref_chunk1_lossless_hevc.mp4",
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/references/ref_chunk2_lossless_hevc.mp4",
    ".../VQA2-dataset/dataset-reference-chunks/heros3/heros3_02/references/ref_chunk3_lossless_hevc.mp4"
  ],
  "output_name": "heros3__heros3_02__480p30-1080p120-1080p60.mp4",
  "target_width": 1920, "target_height": 1080, "target_fps": 120, "expected_frames": 540
}
```

| 字段 | 含义 |
| --- | --- |
| `candidate_id` | 视频名：`<scene>__<chunk1>-<chunk2>-<chunk3>`，即 shot 名加三段设置 |
| `scene` | 视频所属的 shot（gMAD 按 shot 分组），`__` 前面是场景名，例如 `heros3` |
| `chunk1`–`chunk3` | 每个 1.5 s chunk 的分辨率（480/720/1080p）和帧率（30/60/120 fps） |
| `is_fixed`、`switches` | 三段设置是否全相同、相邻 chunk 之间切换了几次 |
| `source_videos` | test 视频的三个 chunk 文件（无损 HEVC，原生分辨率和帧率） |
| `source_references` | 同一 shot 的 reference 三个 chunk（1080p120） |
| `output_name`、`target_*`、`expected_frames` | 把视频拼成一个 1080p120 文件时用的参数（`render_selected_videos.py`）。DSIS 实验不拼接，不用这些字段 |

程序怎么使用 recipes：

- **不需要预先拼接视频**：实验时按顺序播放 `source_videos` 里的三个文件。
- **1080p120 的 chunk 用 reference 文件播放**：1080p120 本来就是 reference 本身，播放器用 `source_references` 里对应的文件代替。bistro 的 chunk 1 reference 指向 `gmad_frame_scores/bistro_360p480p/...`：它和原文件像素完全相同，只修正了最后一帧的时长（原文件时长 1.4917 s，修正后 1.5 s）；CVVDP 打分用的也是这一份。
- **选场景**：单独跑一个场景时，程序按 `scene` 字段 `__` 前面的场景名，从这 239 条记录里筛出该场景的记录，不会生成新的 JSON。
- **检查**：程序检查每条记录的三段设置都是 480/720/1080p × 30/60/120 fps、`candidate_id` 和设置一致、所有文件存在、同一个 shot 只有一组 reference。

### 路径和换机器

recipes 里的路径是生成它的机器上的绝对路径（`C:/Users/15142/Projects/vqa_workspace/VQA2-dataset/...`）。如果某个路径在当前机器上不存在，程序会取路径中 `VQA2-dataset/` 之后的部分，到当前 workspace 的 `VQA2-dataset` 下找同一个文件。所以只要两个目录并排放置，任何机器、任何盘符都能用：

```
<任意目录>/
├── VQA2-gmad-pooling/   ← git clone
└── VQA2-dataset/        ← 视频
```

## 在另一台机器上运行

视频不在 git 里（约 17 GB），要单独拷过去。

1. 在有视频的机器上打包，每个场景一个 zip（不压缩，写完做 CRC 校验，并为每个 zip 生成 `<场景>_files.csv` 文件清单）：

   ```
   cd VQA2-gmad-pooling/gmad
   python package_dsis_videos.py --dry-run                                  # 看每个场景多大
   python package_dsis_videos.py --output <打包目录> --zip-per-scene
   ```

   Version A 共 343 个文件、17.09 GB，13 个 zip 各 0.6–2.9 GB。不加 `--zip-per-scene` 时，改为直接复制成一个 `VQA2-dataset` 文件夹。只打包程序实际播放的文件（1080p120 test chunk 用 reference 文件代替，不重复打包）。

2. 在另一台机器上 `git clone` / `git pull` 得到 `VQA2-gmad-pooling`，把 zip 都解压到它所在的那一级目录（选"解压到当前文件夹"，不要按 zip 名建子文件夹）。zip 里的路径都以 `VQA2-dataset/` 开头，解压后自动合并成上面的结构。只跑某个场景时，只解压那个场景的 zip 即可。

3. 运行只检查模式：`run_dsis_version_a('S01', true)`，或 `run_dsis_gmad_480p1080p('S01', true, false, [], [], '<场景>')`。

另一台机器需要：MATLAB（R2023b 测试过）、Psychtoolbox 3、GStreamer（默认路径 `C:\gstreamer\1.0\msvc_x86_64\bin`；不同时修改 `GSTREAMER_BIN`）、120 Hz 显示器。

## User settings

`run_dsis_gmad_480p1080p.m` 开头：

| 设置 | 默认 | 含义 |
| --- | --- | --- |
| `FULL_SCREEN` | `true` | 全屏；`false` 为窗口模式 |
| `SCREEN_NUMBER` | `[]` | 显示器编号，空为编号最大的屏幕 |
| `WINDOW_RECT` | `[100 100 1380 820]` | 窗口模式的位置和大小 |
| `TITLE_SECONDS` | `1.0` | reference 前灰屏 "Reference" 的秒数 |
| `GAP_SECONDS` | `1.5` | reference 和 test 之间灰屏 "Test" 的秒数 |
| `GREY` | `128` | 灰屏亮度 |
| `BREAK_EVERY` | `40` | 每多少个 trial 休息一次，`0` 为不休息 |
| `SESSION_TRIALS` | `120` | 每次运行最多多少个 trial，`Inf` 为一次做完 |
| `TEXT_SIZE`、`TEXT_FONT` | `30`、`'Arial'` | 屏幕文字 |
| `GSTREAMER_BIN` | `C:\gstreamer\1.0\msvc_x86_64\bin` | GStreamer 路径 |
| `SCALE` | 见上文 | 五级量表的文字 |
