# VQA2 gMAD temporal pooling

本项目用 **gMAD（群体最大差异化竞争）**，从渲染视频中挑选适合主观画质实验的视频对，以比较 15 条逐帧质量分数的时间池化规则。当前仓库保存的是**选片初筛结果**；尚未完成被试评分，因此没有规则的主观胜负排名。

## 先看结果

- [中文版选片报告](results/gmad_selection_skip_negative_no_offset_time_converted/report.html)
- [English report](results/gmad_selection_skip_negative_no_offset_time_converted/report_en.html)
- [预实验 84 对视频清单](results/gmad_selection_skip_negative_no_offset_time_converted/pilot_pairs.csv)
- [全部去重 gMAD 视频对](results/gmad_selection_skip_negative_no_offset_time_converted/gmad_pairs.csv)
- [每个攻击任务及其选对结果](results/gmad_selection_skip_negative_no_offset_time_converted/attack_tasks.csv)
- [参数、时间窗口和输入文件哈希](results/gmad_selection_skip_negative_no_offset_time_converted/config.json)

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
