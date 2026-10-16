shot 是一个4.5s 的路径
native 是"一个 chunk 一个分数"，frames 是"一帧一个分数"，features 是两者共同的原始数据。

run_dsis_gmad_480p1080p.m：
SESSION_TRIALS 是每次运行最多做多少个 trial，它的作用是把一个很长的实验拆成几次做。
每个 trial 大约 15 s，120 个大约 30 分钟，这是 BT.500 建议的单次时长上限

run_dsis_version_a.m，指向 version A 的 recipes。
跑run_dsis_version_a.m matlab 放到另一个显示屏上

实验结果写到：
VQA2-gmad-pooling\results\dsis_all_shots_version_a\

run_dsis_gmad_480p1080p.m 
默认用 results/gmad_bistro_480p720p1080p_.../selected_video_recipes.json，共 209 条，都是 bistro。
run_dsis_version_a.m 
用 results/gmad_all_shots_.../selection_all_scenes/video_recipes.json，共 239 条，来自 28 个 shot。