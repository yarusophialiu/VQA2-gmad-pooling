# VQA2 gMAD temporal pooling

本项目用 **gMAD（群体最大差异化竞争）**，从渲染视频中挑选适合主观画质实验的视频对，以比较 15 条逐帧质量分数的时间池化规则。当前仓库保存的是**选片初筛结果**；尚未完成被试评分，因此没有规则的主观胜负排名。

## 先看结果

- [中文版选片报告](results/gmad_selection_skip_negative_no_offset_time_converted/report.html)
- [English report](results/gmad_selection_skip_negative_no_offset_time_converted/report_en.html)
- [预实验 84 对视频清单](results/gmad_selection_skip_negative_no_offset_time_converted/pilot_pairs.csv)
- [全部去重 gMAD 视频对](results/gmad_selection_skip_negative_no_offset_time_converted/gmad_pairs.csv)
- [每个攻击任务及其选对结果](results/gmad_selection_skip_negative_no_offset_time_converted/attack_tasks.csv)
- [参数、时间窗口和输入文件哈希](results/gmad_selection_skip_negative_no_offset_time_converted/config.json)
- [新增 bistro 360p／480p：CVVDP 和 gMAD 报告](results/gmad_bistro_360p480p_skip_negative_no_offset_time_converted/report_en.html)
- [bistro 全部分辨率 360p／480p／720p／1080p：CVVDP 和 gMAD 报告](results/gmad_bistro_all_resolutions_skip_negative_no_offset_time_converted/report_en.html)

当前结果目录是 `results/gmad_selection_skip_negative_no_offset_time_converted/`。其他实验版本、对比文件及本地逐帧分数输入位于 [`results/legacy/`](results/legacy/README.md)。

## 实验与选片方法

当前数据有 6 个场景（bistro、gallery、makeway、rogue、school、sibenik）。每个场景的每个 1.5 秒 chunk 有 2 种分辨率（720p、1080p）× 3 种帧率（30、60、120 fps），共 6 种设置。三个 chunk 拼成 4.5 秒视频，因此每场景有 `6³ = 216` 个候选、总计 **1,296** 个候选。程序先在统一的 120 Hz 时间轴上计算各 chunk 的逐帧质量代理分数，再拼接分数序列进行选片；此阶段没有拼接全部候选视频。

每条池化规则把一段视频的逐帧分数压成一个预测分数。gMAD 让规则轮流担任“防守者”和“攻击者”：在防守者认为质量接近的候选视频中，找攻击者认为差异尽量大的一对。候选按**该防守规则在该场景的预测分数**分成 `K = 3` 个质量档，分别尝试选对；同一对中的两个视频必须在同一档，且满足防守分差和最小攻击分差门槛。三个档是分数范围，**不是**视频的三个 chunk，也不是人评确认的画质等级。

当前参数下共有 `6 场景 × 15 防守规则 × 14 攻击规则 × 3 档 = 3,780` 个攻击任务。其中 **3,414** 个任务选出有效视频对；不同任务可能选中同一对，去重后为 **1,225 对**。预实验每场景选 10 对 gMAD、2 对随机、2 对诊断，共 **84 对**、涉及 **133 段不同视频**。gMAD 预实验对依次按尚未覆盖的“防守—攻击—质量档”组合数量挑选；覆盖相同时，再看攻击分差。它不是简单按某对视频出现的任务次数排序，也不保证三个质量档在预实验中数量相等。

本版采用 `--time-policy converted --skip-negative --input-offset 0`：把原研究 25 fps 下的 100/125 帧时间长度换算为 120 Hz 下的 480/600 帧；删除输入中 **18 个负分帧**，不把它们改成 0，也不施加正值偏移。负分来自 108 份原始 chunk 逐帧 CSV，导致 **216 个候选**的分数序列短于 540 帧；实际视频仍长 4.5 秒。详细规则、分差门槛及每条负分记录见中英文报告。

## 目录与脚本

| 路径 | 用途 |
| --- | --- |
| `run_iridium_lossless_chunks.py`、`extract_gmad_frame_scores.py` | 在 Iridium 上生成无损 HEVC 设置并导出 ColorVideoVDP 视频模式的逐帧代理分数；脚本默认路径依赖该服务器环境。 |
| `start_iridium_lossless_chunks.sh`、`fetch_iridium_gmad_scores.sh` | 启动远程处理、下载逐帧 CSV 和元数据；下载目标现位于 `results/legacy/gmad_frame_scores/`。 |
| `gmad/temporal_pooling_snapshot.py` | 本次使用的 15 条池化规则实现快照。 |
| `gmad/run_selection.py` | 拼接候选分数序列、计算规则预测、执行 gMAD 搜索并生成 CSV/JSON 清单。 |
| `gmad/build_result_report.py`、`gmad/build_english_result_report.py` | 从现有结果文件生成中英文 HTML；不重新执行选片。 |
| `gmad/render_selected_videos.py` | 按 JSON 配方实际拼接入选视频；需要源 MP4、`ffmpeg` 和 `ffprobe`。 |
| `results/gmad_selection_skip_negative_no_offset_time_converted/` | 当前采用的选片结果、报告和视频拼接配方。 |
| `results/legacy/` | 旧参数版本、对比结果和逐帧分数输入。 |

## 复现与后续步骤

本地运行选片需要 Python 环境中的 `numpy`、`scipy`、`torch`。远程逐帧打分还需要与原运行一致的 `pycvvdp`、显示模型及 VQA2 的 `per_frame_quality.py` 辅助代码；仓库目前没有锁定这些依赖版本。输入 CSV 和元数据已归档，可在**新的输出目录**中复算，而不覆盖当前结果：

若重新从视频生成逐帧分数，注意 `run_iridium_lossless_chunks.py` 的默认 `--scenes` 列表只有 5 个场景，不包含 `rogue`；要重建当前 6 场景输入，需显式加入 `rogue` 并准备对应源视频与参考视频。

```bash
python gmad/run_selection.py \
  --input results/legacy/gmad_frame_scores/lossless_spatiotemporal_chunks \
  --output results/legacy/reproduction_check \
  --time-policy converted \
  --skip-negative \
  --input-offset 0
```

上述命令会重新计算规则分数和选对，耗时取决于机器；生成的 `config.json` 记录参数及输入哈希。若只需根据**现有结果**重建报告，可运行：

```bash
python gmad/build_result_report.py gmad_selection_skip_negative_no_offset_time_converted
python gmad/build_english_result_report.py
```

入选视频的拼接清单在 [`pilot_video_recipes.json`](results/gmad_selection_skip_negative_no_offset_time_converted/pilot_video_recipes.json)；它记录了 Iridium 上的源视频路径。实际拼接时可用 `gmad/render_selected_videos.py --recipes ... --dataset-root ... --output ...` 将路径指向本地或远程可访问的无损视频。**逐段分数拼接仅用于初筛**：正式主观实验前，还需检查视频内容连续性，并对拼好的完整视频复核 ColorVideoVDP 分数，尤其是 chunk 切换处；被试实验中的 A/B 播放顺序也应随机化。

## 拼接预实验视频

预实验 84 对对应 133 段不同视频，每段由三个连续 chunk 组成。拼接脚本先用 **bicubic** 将各 chunk 统一到 1920×1080，再通过**重复帧**统一到 120 fps：30 fps 每帧重复 4 次，60 fps 每帧重复 2 次，120 fps 每帧保留一次。每个 chunk 精确为 180 帧，完整视频为 **540 帧、4.5 秒**，以 HEVC 无损模式编码。

```bash
python gmad/render_selected_videos.py \
  --recipes results/gmad_selection_skip_negative_no_offset_time_converted/pilot_video_recipes.json \
  --pair-list results/gmad_selection_skip_negative_no_offset_time_converted/pilot_pairs.csv \
  --dataset-root /path/to/lossless_spatiotemporal_chunks \
  --output results/gmad_selection_skip_negative_no_offset_time_converted/pilot_videos_bicubic_120fps
```

`--dataset-root` 必须包含真正的源 MP4；`results/legacy/gmad_frame_scores/` 只有下载的评分文件，不能替代视频输入。脚本缓存处理好的 chunk，再直接拼接码流，并记录参数和输入文件状态，方便中断后继续。

输出目录中的 `render_manifest.json` 对应每段视频及三个源 chunk；`pair_video_paths.csv` 给出 84 对视频的 A/B 文件路径；`normalized_chunks/` 存放缓存。生成的视频目录已加入 `.gitignore`。原选片用的 CVVDP 分数采用 bilinear 显示放大，而这次实际拼接采用 bicubic，因此完整视频复核应采用实际输出和最终显示设置。

处理参数参考 FFmpeg 官方的 [bicubic 缩放文档](https://ffmpeg.org/ffmpeg-scaler.html)和 [fps 重复帧文档](https://ffmpeg.org/ffmpeg-filters.html#fps)。

方法参考：K. Ma *et al.*, “Group maximum differentiation competition: Model comparison with few samples,” *IEEE Transactions on Pattern Analysis and Machine Intelligence*, vol. 42, no. 4, pp. 851–864, 2020. [doi:10.1109/TPAMI.2018.2889948](https://doi.org/10.1109/TPAMI.2018.2889948).

### 本地播放 bistro Pilot pairs

当前结果中的 bistro 有 14 对、24 段不同视频。将 `pilot_pairs.csv` 中 `scene=bistro` 的记录保存为 `pilot_pairs_bistro.csv`，然后使用上面的拼接命令，将 `--pair-list` 指向该筛选清单，`--output` 指向 `pilot_videos_bicubic_120fps/bistro`。本地数据根目录为 `../VQA2-dataset/gmad_frame_scores/lossless_spatiotemporal_chunks`。

拼接完成后，生成浏览器用的无损 H.264 副本及离线 A/B 播放页面：

```bash
python gmad/build_local_pair_player.py \
  --directory results/gmad_selection_skip_negative_no_offset_time_converted/pilot_videos_bicubic_120fps/bistro \
  --pair-list results/gmad_selection_skip_negative_no_offset_time_converted/pilot_videos_bicubic_120fps/bistro/pilot_pairs_bistro.csv
```

打开输出目录中的 `play_pairs.html`，可以选择视频对、单独播放 A/B、依次播放 A → B，以及全屏查看。H.264 转码使用 `libx264 -crf 0`，保留拼接输出的像素、帧率和时长；HEVC 原文件也保留。重新运行 `gmad/build_english_result_report.py` 后，英文报告的 Pilot pair list 上方会显示本地播放链接。播放器保留清单顺序，用于查看视频；正式被试实验的随机化及完整视频 CVVDP 复核仍需另行完成。

视频目录现已移动到 `../VQA2-dataset/pilot_videos_bicubic_120fps/bistro`，原 MP4 和浏览器副本均保留在该目录。英文报告生成器也支持这个位置。

### MATLAB / Psychtoolbox 播放 HEVC

[`gmad/play_gmad_pairs_hevc.m`](gmad/play_gmad_pairs_hevc.m) 直接播放 HEVC 文件。当前默认读取新的 360p／480p Pilot list（14 对、22 段视频），视频位于 `../VQA2-dataset/pilot_videos_360p480p_120fps/bistro`；默认配对清单直接读取结果目录中的 `pilot_pairs.csv`。脚本根据当前位置和候选 ID 找视频，不使用移动前的 manifest 绝对路径。在 MATLAB 中运行：

```matlab
addpath('C:\Users\15142\Projects\vqa_workspace\VQA2-gmad-pooling\gmad');
play_gmad_pairs_hevc;
```

左键从头播放当前 pair 的 A，右键从头播放 B；Enter 显示纯黑屏至少 0.5 秒后进入下一对的 A，最后一对之后退出；Esc 随时退出。视频播完保留最后一帧，等待按键。左上角按解码帧的时间戳显示当前 chunk 的源分辨率／fps、Pair ID、A/B 和 `Linked gMAD tasks` 数量。所有拼接文件的实际编码尺寸／帧率仍是 1920×1080／120 fps。

在脚本顶部修改 `FULL_SCREEN`（默认 `false`）、`SCREEN_NUMBER` 和 `WINDOW_RECT`。窗口预览默认跳过同步检查，全屏默认执行同步检查。播放保持纵横比。启动时打开当前清单的全部视频，减少切换时的重新加载；黑屏实际结束时间还受首帧解码和屏幕刷新影响。GStreamer 路径默认 `C:\gstreamer\1.0\msvc_x86_64\bin`，可修改 `GSTREAMER_BIN`，或设为 `''` 使用已有环境。源分辨率标注支持 640×360、854×480、1280×720 和 1920×1080。

只验证配对清单和 HEVC 渲染元数据、不打开窗口：

```matlab
pairs = play_gmad_pairs_hevc([], true);
% 如果再次移动目录，也可以传入新位置（父目录或 bistro 子目录）：
play_gmad_pairs_hevc('D:\videos\pilot_videos_bicubic_120fps');
% 在本机播放之前的 720p/1080p 清单：
play_gmad_pairs_hevc('C:\Users\15142\Projects\vqa_workspace\VQA2-dataset\pilot_videos_bicubic_120fps');
% 自定义配对清单可以作为第三个参数：
play_gmad_pairs_hevc(videoRoot, false, pairListCsv);
```

### bistro 的 360p / 480p 无损 chunk

[`gmad/encode_low_resolution_chunks.py`](gmad/encode_low_resolution_chunks.py) 将现有 gMAD 的三个 reference chunk 编成 640×360、854×480，各 30／60／120 fps，共 18 个 HEVC 无损视频。空间缩小使用 bicubic，时间降采样使用 FFmpeg `fps`，每段统一为 1.5 秒。源 reference 各有 180 帧；编码时重设 120 Hz 时间戳，处理末帧的包时长，再裁到目标帧数。输出后检查尺寸、帧数、时长并完整解码验证。

```bash
python gmad/encode_low_resolution_chunks.py \
  --source-dir ../VQA2-dataset/gmad_frame_scores/lossless_spatiotemporal_chunks/bistro/bistro_path2_seg3_1/references \
  --output ../VQA2-dataset/gmad_frame_scores/lossless_spatiotemporal_chunks/bistro/bistro_path2_seg3_1/videos \
  --expected-source-frames 180 --replace
```

新文件命名为 `chunk{1,2,3}_{360,480}p{30,60,120}_lossless_hevc.mp4`，编码来源和参数记录在输出目录的 `low_resolution_encode_manifest.json`。30／60／120 fps 的输出分别有 45／90／180 帧。`--replace` 仅替换这 18 个低分辨率文件；不指定时拒绝覆盖已有文件。原 `dataset-reference-chunks` 中较短的片段未用于这组最终输出。此编码步骤只更新视频；CVVDP 打分和 gMAD 流程见下一节。

### 本地重跑 360p / 480p 的 CVVDP 和 gMAD

[`run_local_chunk_scores.py`](run_local_chunk_scores.py) 在独立目录计算这 18 个 chunk 的 CVVDP 视频模式分数及每段 180 个逐帧代理分数。使用 `standard_fhd`，bilinear 放大到 1920×1080，并在共同的 120 Hz 时间轴上通过重复帧处理 30／60 fps 输入。本次使用本机原版 ColorVideoVDP checkout（模型版本 0.5.6），不启用 motion/SPEM 扩展；实现、显示配置和参数的哈希记录在 `scoring_config.json`。第一个 reference 的末帧包时长不完整时，在独立副本中重设时间戳，不更改其像素或源文件。

[`per_frame_quality.py`](per_frame_quality.py) 保留 CVVDP 的空间频带权重和通道池化，在时间池化之前导出帧域 JOD 代理，并检查该帧域响应重新池化后能复现原始视频 JOD。它不是逐帧独立图像模式。输出有来源签名，重复运行仅复用来源和参数一致的缓存。

在本仓库目录依次运行：

```bash
python -X utf8 run_local_chunk_scores.py \
  --source-root ../VQA2-dataset/gmad_frame_scores/lossless_spatiotemporal_chunks \
  --output-root ../VQA2-dataset/gmad_frame_scores/bistro_360p480p \
  --cvvdp-root C:/Users/15142/Projects/ColorVideoVDP/ColorVideoVDP

python -X utf8 gmad/run_selection.py \
  --input ../VQA2-dataset/gmad_frame_scores/bistro_360p480p \
  --output results/gmad_bistro_360p480p_skip_negative_no_offset_time_converted \
  --time-policy converted --skip-negative --input-offset 0

python -X utf8 gmad/build_local_chunk_report.py \
  results/gmad_bistro_360p480p_skip_negative_no_offset_time_converted
```

gMAD 的输入只包含 bistro 的 360p／480p × 30／60／120 fps，三个 chunk 组成 `6³ = 216` 个候选、630 个攻击任务。沿用先前的池化规则及阈值，结果保存在新目录；此前 720p／1080p 的结果不变。输入 manifest 为 `../VQA2-dataset/gmad_frame_scores/bistro_360p480p/manifest.json`，每段 CVVDP JOD 和逐帧代理分别在其 `native/` 和 `frames/` 子目录。这轮仍是基于 chunk 分数序列的初筛，完整拼接视频的切换边界复核另行进行。

已完成的本机运行：18 个 chunk、3,240 个帧域代理分数，没有负值；630 个攻击任务中 575 个选出有效视频对，去重后为 228 对，Pilot list 为 14 对、22 段不同视频。新结果目录中的 `cvvdp_chunk_scores.csv` 汇总原始 CVVDP JOD，`report_en.html` 展示打分及 Pilot list，`validation.json` 记录检查结果。

### 在 MATLAB 播放新的 360p / 480p Pilot list

新清单的 22 段视频生成到 `../VQA2-dataset/pilot_videos_360p480p_120fps/bistro`，每段由三个 chunk 顺序拼接成 1920×1080／120 fps、540 帧、4.5 秒的 HEVC 无损视频。空间放大使用 bilinear，与这轮 CVVDP 的放大参数一致；低帧率内容仍通过重复帧呈现。HEVC 使用 `medium` 无损压缩，并在缓存 chunk 最后一次使用后删除缓存，降低磁盘占用。

```bash
python -X utf8 gmad/render_selected_videos.py \
  --recipes results/gmad_bistro_360p480p_skip_negative_no_offset_time_converted/pilot_video_recipes.json \
  --pair-list results/gmad_bistro_360p480p_skip_negative_no_offset_time_converted/pilot_pairs.csv \
  --output ../VQA2-dataset/pilot_videos_360p480p_120fps/bistro \
  --spatial-filter bilinear --preset medium --discard-cache
```

在 MATLAB 运行 `play_gmad_pairs_hevc` 即可查看新清单。左右键播放 A/B，Enter 黑屏 0.5 秒后进入下一对，Esc 退出；`FULL_SCREEN` 开关及源分辨率／fps、Linked gMAD tasks 标注保留。

### bistro 全部分辨率和帧率的联合 gMAD

联合条件为 360p、480p、720p、1080p × 30、60、120 fps，每个 chunk 有 12 种设置，共 36 个 chunk，组成 `12³ = 1,728` 个 4.5 秒候选。攻击任务仍为一个场景 × 15 防守规则 × 14 攻击规则 × 3 档 = 630。选片程序按 manifest 自动推导条件数量，并要求三个 chunk 的设置集合一致。

全部分辨率使用同一 CVVDP 0.5.6、`standard_fhd`、bilinear 放大、120 Hz 时间轴和视频模式。360p／480p 仅在视频、参考文件、模型和导出实现的签名匹配时复用缓存；720p／1080p 重新计算，不混用旧版本的评分。1080p／120 fps 的第一段与参考文件字节一致，但末帧包时长不完整，打分使用已修正时间轴的同像素参考副本。源视频保持不变。

```bash
python -X utf8 run_local_chunk_scores.py \
  --source-root ../VQA2-dataset/gmad_frame_scores/lossless_spatiotemporal_chunks \
  --output-root ../VQA2-dataset/gmad_frame_scores/bistro_360p480p720p1080p \
  --cvvdp-root C:/Users/15142/Projects/ColorVideoVDP/ColorVideoVDP \
  --heights 360 480 720 1080 \
  --reuse-root ../VQA2-dataset/gmad_frame_scores/bistro_360p480p

python -X utf8 gmad/run_selection.py \
  --input ../VQA2-dataset/gmad_frame_scores/bistro_360p480p720p1080p \
  --output results/gmad_bistro_all_resolutions_skip_negative_no_offset_time_converted \
  --time-policy converted --skip-negative --input-offset 0

python -X utf8 gmad/build_local_chunk_report.py \
  results/gmad_bistro_all_resolutions_skip_negative_no_offset_time_converted
```

新结果单独保存，包含全部联合候选的规则预测、gMAD 对清单、Pilot list 和拼接配方。此步骤不生成新的拼接视频。

本轮已完成 36 个 chunk 的 6,480 个逐帧代理分数和全部 1,728 个候选的 gMAD：600／630 个攻击任务选出有效对，去重后 285 对；Pilot list 为 14 对、26 段不同候选。没有负分帧。`validation.json` 验证完整条件组合、同档及分差阈值，并确认之前 216 个低分辨率候选的 15 条规则预测在此次扩展中保持一致。


### MATLAB playback of the all-resolution bistro Pilot list

Run the latest 14 pairs (26 candidates) directly from the original HEVC chunks:

```matlab
addpath('C:/Users/15142/Projects/vqa_workspace/VQA2-gmad-pooling/gmad');
play_gmad_all_resolutions;
```

`gmad/play_gmad_all_resolutions.m` reads
`results/gmad_bistro_all_resolutions_skip_negative_no_offset_time_converted/pilot_pairs.csv`.
It opens only the current pair's HEVC chunks and decodes frames sequentially
on demand, without creating concatenated MP4s or a disk cache. It retains
one texture per source (at most six, plus one temporary replacement), rather
than preloading entire clips. Three 1.5-second chunks play consecutively;
source frame indices are bounded to 45, 90, or 180 frames, lower frame rates
use frame repetition, and spatial scaling uses bilinear filtering. Shared
chunks use one decoder per pair. A/B replay rewinds the relevant decoders.
Finished-video diagnostics report source samples skipped during presentation
when decoding/display timing cannot keep up. The first 1080p/120 fps chunk
uses the same-pixel, corrected-timestamp reference from the 360p/480p scoring
run. The playback area has a fixed 16:9 aspect ratio.

Left restarts A; Right restarts B; Enter shows pure black for at least 0.5 s
before loading the next pair, which starts at A; Esc exits. The next pair has
a loading screen after the black interval. Videos hold their last frame when
finished. Source resolution/fps and the number of linked gMAD tasks appear in
the upper left. Set `FULL_SCREEN = true` at the top for fullscreen playback;
the default windowed preview skips synchronization checks, while fullscreen
checks synchronization. Use a 120 Hz display to present 120 fps content.

```matlab
pairs = play_gmad_all_resolutions(true); % Validate CSV and source paths only
play_gmad_all_resolutions(false, 'C:/path/to/pilot_pairs.csv');
```

The earlier `play_gmad_pairs_hevc` entry remains available for the previously
rendered movie sets.


### bistro gMAD and MATLAB playback for 480p through 1080p

The input subset `../VQA2-dataset/gmad_frame_scores/bistro_480p720p1080p`
contains the 27 existing CVVDP chunks for 480p/720p/1080p x 30/60/120 fps.
Its `subset_provenance.json` records the source manifest and identical hashes
for every copied score CSV and metadata file. No videos were re-encoded and
CVVDP scores were reused from the verified all-resolution run.

```bash
python -X utf8 gmad/run_selection.py --input ../VQA2-dataset/gmad_frame_scores/bistro_480p720p1080p --output results/gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted --time-policy converted --skip-negative --input-offset 0
python -X utf8 gmad/build_local_chunk_report.py results/gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted
```

This independent run has 729 candidates, 585 selected attack tasks out of
630, 255 distinct gMAD pairs, and 14 Pilot pairs containing 25 candidates.
`validation.json` checks the full 9^3 grid, matching predictions for all 729
retained candidates, selected-pair inequalities and bins, Pilot recipes and
HEVC source paths. Full-video boundary scoring has not been performed.

```matlab
addpath('C:/Users/15142/Projects/vqa_workspace/VQA2-gmad-pooling/gmad');
play_gmad_480p1080p; % Uses the user's fullscreen/window setting
% Explicit windowed preview (does not change FULL_SCREEN in the source):
play_gmad_480p1080p(false, true);
% Validate without opening a window:
pairs = play_gmad_480p1080p(true);
```

This entry reads the new Pilot list and shares the HEVC chunk player and its
`FULL_SCREEN` setting in `gmad/play_gmad_all_resolutions.m`. Left/Right restart
A/B, Enter displays black for at least 0.5 s before next-pair loading, and Esc
exits. Source resolution/fps and linked-task counts remain visible.

The local fullscreen launch failed Psychtoolbox synchronization checks. The
current 480p-through-1080p session was opened with the explicit windowed
preview option. This preview does not establish accurate 120 Hz presentation
timing; fullscreen synchronization must pass for timing-sensitive use.

The HEVC chunk player now uses bounded streaming to avoid the texture-memory
exhaustion encountered while preloading the second pair. Fatal Screen errors
can close all resources internally; cleanup checks live window/texture handles
before closing them to avoid secondary invalid-handle errors.
