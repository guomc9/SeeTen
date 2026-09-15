"""性能矩阵数据（msprof device 侧 kernel 时间，median of 25，μs）。

本仓库 = det-cmp-v3-swizzle @ 合并 integration/FAG-V3-A5(cube Optimize) 后；
opst = 参考仓库（det 用 torch.use_deterministic_algorithms(True)）。
口径：msprof Task Duration 中位数（warmup 5 + repeat 20），非 event record。
None = 该 case 参考实现无法运行。
"""

# (case_name, layout, label)
CASES = [
    ("bsnd_small_mha_causal", "BSND", "b1·128×128·c·H2/2·D128"),
    ("bsnd_small_mha_nc", "BSND", "b1·128×128·nc·H2/2·D128"),
    ("bsnd_small_gqa_tail_causal", "BSND", "b2·200×300·c·H4/2·D64"),
    ("bsnd_small_mqa_tail_nc", "BSND", "b2·300×500·nc·H4/1·D64"),
    ("bsnd_tiny_unaligned_causal", "BSND", "b2·33×77·c·H4/4·D64"),
    ("bsnd_mid_mha_square_causal", "BSND", "b1·1024×1024·c·H8/8·D128"),
    ("bsnd_mid_mha_square_nc", "BSND", "b1·1024×1024·nc·H8/8·D128"),
    ("bsnd_mid_mha_rect_causal", "BSND", "b2·333×777·c·H4/4·D64"),
    ("bsnd_mid_mha_rect_nc", "BSND", "b2·777×333·nc·H4/4·D64"),
    ("bsnd_mid_gqa_square_causal", "BSND", "b1·1024×1024·c·H8/2·D128"),
    ("bsnd_mid_gqa_square_nc", "BSND", "b1·1024×1024·nc·H8/2·D128"),
    ("bsnd_mid_mqa_causal", "BSND", "b2·300×500·c·H4/1·D64"),
    ("bsnd_mid_mqa_nc", "BSND", "b2·300×500·nc·H4/1·D64"),
    ("bsnd_mid_gqa_rect_causal", "BSND", "b2·500×900·c·H6/3·D128"),
    ("bsnd_mid_gqa_rect_nc", "BSND", "b2·500×900·nc·H6/3·D128"),
    ("bsnd_mid_mha_hd64_nc", "BSND", "b2·777×333·nc·H6/3·D64"),
    ("bsnd_long_mha_causal", "BSND", "b1·2048×2048·c·H8/8·D128"),
    ("bsnd_long_mha_nc", "BSND", "b1·2048×2048·nc·H8/8·D128"),
    ("bsnd_long_gqa_causal", "BSND", "b1·2048×2048·c·H8/2·D128"),
    ("bsnd_large_mha_causal", "BSND", "b1·4096×4096·c·H4/4·D128"),
    ("bsnd_large_mha_nc", "BSND", "b1·4096×4096·nc·H4/4·D128"),
    ("tnd_small_mha_causal", "TND", "256+384·c·H4/4·D128"),
    ("tnd_small_mha_nc", "TND", "256+384·nc·H4/4·D128"),
    ("tnd_ragged_mqa_causal", "TND", "100+800/300+1300·c·H4/1·D64"),
    ("tnd_ragged_mqa_nc", "TND", "100+800/300+400·nc·H4/1·D64"),
    ("tnd_ragged_mha_nc", "TND", "100+800/300+400·nc·H4/4·D64"),
    ("tnd_ragged_gqa_causal", "TND", "512+1024/768+1280·c·H4/2·D128"),
    ("tnd_ragged_gqa_nc", "TND", "512+1024/768+1280·nc·H4/2·D128"),
    ("tnd_eq_mha_causal", "TND", "2×2048·c·H8/8·D128"),
    ("tnd_eq_mha_nc", "TND", "2×2048·nc·H8/8·D128"),
    ("tnd_eq_gqa_causal", "TND", "2×1024·c·H8/2·D128"),
    ("tnd_eq_gqa_nc", "TND", "2×1024·nc·H8/2·D128"),
    ("tnd_pack8_mha_causal", "TND", "8×512·c·H8/8·D128"),
    ("tnd_pack8_mha_nc", "TND", "8×512·nc·H8/8·D128"),
    ("tnd_large4_mha_causal", "TND", "4×2048·c·H4/4·D128"),
    ("tnd_large_mha_nc", "TND", "1×4096·nc·H4/4·D128"),
    ("tnd_large4_gqa_causal", "TND", "4×1024·c·H8/2·D128"),
    ("tnd_large4_mqa_causal", "TND", "4×2048·c·H4/1·D64"),
]

# 图中用短标签（横轴空间有限）
SHORT = [
    "b1·128×128c MHA",
    "b1·128×128nc MHA",
    "b2·200×300c GQA",
    "b2·300×500nc MQA",
    "b2·33×77c MHA",
    "b1·1024×1024c MHA",
    "b1·1024×1024nc MHA",
    "b2·333×777c MHA",
    "b2·777×333nc MHA",
    "b1·1024×1024c GQA",
    "b1·1024×1024nc GQA",
    "b2·300×500c MQA",
    "b2·300×500nc MQA",
    "b2·500×900c GQA",
    "b2·500×900nc GQA",
    "b2·777×333nc GQA",
    "b1·2048×2048c MHA",
    "b1·2048×2048nc MHA",
    "b1·2048×2048c GQA",
    "b1·4096×4096c MHA",
    "b1·4096×4096nc MHA",
    "R2·384/384c MHA",
    "R2·384/384nc MHA",
    "R2·800/1300c MQA",
    "R2·800/400nc MQA",
    "R2·800/400nc MHA",
    "R2·1024/1280c GQA",
    "R2·1024/1280nc GQA",
    "2×2048c MHA",
    "2×2048nc MHA",
    "2×1024c GQA",
    "2×1024nc GQA",
    "8×512c MHA",
    "8×512nc MHA",
    "4×2048c MHA",
    "1×4096nc MHA",
    "4×1024c GQA",
    "4×2048c MQA",
]

# 表里用的 shape 描述（b n g s2 s1 d c/nc）
SHAPE = [
    "b1 n2 g1 s2=128 s1=128 d128 causal",
    "b1 n2 g1 s2=128 s1=128 d128 non-causal",
    "b2 n2 g2 s2=300 s1=200 d64 causal",
    "b2 n1 g4 s2=500 s1=300 d64 non-causal",
    "b2 n4 g1 s2=77 s1=33 d64 causal",
    "b1 n8 g1 s2=1024 s1=1024 d128 causal",
    "b1 n8 g1 s2=1024 s1=1024 d128 non-causal",
    "b2 n4 g1 s2=777 s1=333 d64 causal",
    "b2 n4 g1 s2=333 s1=777 d64 non-causal",
    "b1 n2 g4 s2=1024 s1=1024 d128 causal",
    "b1 n2 g4 s2=1024 s1=1024 d128 non-causal",
    "b2 n1 g4 s2=500 s1=300 d64 causal",
    "b2 n1 g4 s2=500 s1=300 d64 non-causal",
    "b2 n3 g2 s2=900 s1=500 d128 causal",
    "b2 n3 g2 s2=900 s1=500 d128 non-causal",
    "b2 n3 g2 s2=333 s1=777 d64 non-causal",
    "b1 n8 g1 s2=2048 s1=2048 d128 causal",
    "b1 n8 g1 s2=2048 s1=2048 d128 non-causal",
    "b1 n2 g4 s2=2048 s1=2048 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 non-causal",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 causal",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 non-causal",
    "b2 n1 g4 s2=300+1300 s1=100+800 d64 causal",
    "b2 n1 g4 s2=300+400 s1=100+800 d64 non-causal",
    "b2 n4 g1 s2=300+400 s1=100+800 d64 non-causal",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 causal",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 non-causal",
    "b2 n8 g1 s2=2048 s1=2048 d128 causal",
    "b2 n8 g1 s2=2048 s1=2048 d128 non-causal",
    "b2 n2 g4 s2=1024 s1=1024 d128 causal",
    "b2 n2 g4 s2=1024 s1=1024 d128 non-causal",
    "b8 n8 g1 s2=512 s1=512 d128 causal",
    "b8 n8 g1 s2=512 s1=512 d128 non-causal",
    "b4 n4 g1 s2=2048 s1=2048 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 non-causal",
    "b4 n2 g4 s2=1024 s1=1024 d128 causal",
    "b4 n1 g4 s2=2048 s1=2048 d64 causal",
]

# 数据量 MB（bf16：q + out + dy + k + v）
SIZE_MB = [
    0.33, 0.33, 0.92, 1.18, 0.26, 10.49, 10.49, 2.61, 3.07, 7.34, 7.34, 1.18, 1.18, 7.37, 7.37, 4.09, 20.97, 20.97, 14.68, 20.97, 20.97, 3.28, 3.28, 1.79, 1.56, 2.10, 6.82, 6.82, 41.94, 41.94, 14.68, 14.68, 41.94, 41.94, 41.94, 20.97, 29.36, 14.68,
]

OURS_DET = [
    24.6, 18.7, 24.8, 35.1, 20.2, 75.6, 112.1, 38.9, 37.5, 98.7, 104.8, 36.5, 35.0, 67.4, 66.3, 43.8, 189.9, 324.0, 248.5, 335.8, 551.7, 29.9, 36.5, 56.7, 53.4, 33.7, 66.0, 68.3, 404.2, 602.6, 114.0, 152.4, 188.6, 304.7, 335.0, 543.2, 211.8, 279.1,
]

OURS_ND = [
    15.0, 15.6, 20.5, 32.0, 14.6, 62.4, 85.2, 31.5, 34.1, 82.2, 97.8, 30.7, 32.2, 57.0, 63.4, 40.3, 146.5, 229.3, 184.8, 250.4, 472.4, 21.3, 23.2, 65.4, 51.9, 35.5, 55.9, 95.3, 269.4, 462.2, 120.5, 171.3, 148.0, 169.5, 277.5, 476.9, 202.1, 197.3,
]

OPST_DET = [
    10.4, 9.9, 26.9, 34.4, 8.9, 61.1, 71.5, 26.7, 28.6, 77.0, 74.8, 35.0, 34.7, 38.9, 51.1, 37.3, 120.0, 178.9, 142.0, 179.4, 303.0, 38.7, 36.8, 72.9, 62.5, 38.6, 66.3, 59.3, 256.8, 369.7, 89.6, 92.7, 144.2, 184.3, 251.0, 306.6, 145.5, 189.0,
]

OPST_ND = [
    10.4, 10.1, 20.4, 23.6, 8.9, 47.5, 58.6, 23.0, 26.6, 43.1, 56.1, 22.6, 23.5, 32.2, 48.1, 30.9, 105.0, 155.9, 95.5, 164.6, 279.5, 25.4, 26.6, 29.2, 27.9, 28.6, 37.3, 50.4, 183.2, 336.0, 64.1, 89.4, 81.3, 137.3, 174.7, 271.3, 111.7, 133.0,
]

N_BSND = 21
N_TND = 17
