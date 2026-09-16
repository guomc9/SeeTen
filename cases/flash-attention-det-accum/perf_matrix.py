"""性能矩阵数据（msprof device 侧 kernel 时间，median of 25，μs）。

本仓库 = det-cmp-v3.2-swizzle @ 1909a89（v3 + v3.1 tiny-trim + v3.2 late-wait）；
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
    "b1 n2 g1 s2=128 s1=128 d128 dense",
    "b2 n2 g2 s2=300 s1=200 d64 causal",
    "b2 n1 g4 s2=500 s1=300 d64 dense",
    "b2 n4 g1 s2=77 s1=33 d64 causal",
    "b1 n8 g1 s2=1024 s1=1024 d128 causal",
    "b1 n8 g1 s2=1024 s1=1024 d128 dense",
    "b2 n4 g1 s2=777 s1=333 d64 causal",
    "b2 n4 g1 s2=333 s1=777 d64 dense",
    "b1 n2 g4 s2=1024 s1=1024 d128 causal",
    "b1 n2 g4 s2=1024 s1=1024 d128 dense",
    "b2 n1 g4 s2=500 s1=300 d64 causal",
    "b2 n1 g4 s2=500 s1=300 d64 dense",
    "b2 n3 g2 s2=900 s1=500 d128 causal",
    "b2 n3 g2 s2=900 s1=500 d128 dense",
    "b2 n3 g2 s2=333 s1=777 d64 dense",
    "b1 n8 g1 s2=2048 s1=2048 d128 causal",
    "b1 n8 g1 s2=2048 s1=2048 d128 dense",
    "b1 n2 g4 s2=2048 s1=2048 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 dense",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 causal",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 dense",
    "b2 n1 g4 s2=300+1300 s1=100+800 d64 causal",
    "b2 n1 g4 s2=300+400 s1=100+800 d64 dense",
    "b2 n4 g1 s2=300+400 s1=100+800 d64 dense",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 causal",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 dense",
    "b2 n8 g1 s2=2048 s1=2048 d128 causal",
    "b2 n8 g1 s2=2048 s1=2048 d128 dense",
    "b2 n2 g4 s2=1024 s1=1024 d128 causal",
    "b2 n2 g4 s2=1024 s1=1024 d128 dense",
    "b8 n8 g1 s2=512 s1=512 d128 causal",
    "b8 n8 g1 s2=512 s1=512 d128 dense",
    "b4 n4 g1 s2=2048 s1=2048 d128 causal",
    "b1 n4 g1 s2=4096 s1=4096 d128 dense",
    "b4 n2 g4 s2=1024 s1=1024 d128 causal",
    "b4 n1 g4 s2=2048 s1=2048 d64 causal",
]

# 数据量 MB（bf16：q + out + dy + k + v）
SIZE_MB = [
    0.33, 0.33, 0.92, 1.18, 0.26, 10.49, 10.49, 2.61, 3.07, 7.34, 7.34, 1.18, 1.18, 7.37, 7.37, 4.09, 20.97, 20.97, 14.68, 20.97, 20.97, 3.28, 3.28, 1.79, 1.56, 2.10, 6.82, 6.82, 41.94, 41.94, 14.68, 14.68, 41.94, 41.94, 41.94, 20.97, 29.36, 14.68,
]

OURS_DET = [
    16.6, 16.3, 21.4, 32.5, 12.9, 68.5, 96.8, 39.0, 34.6, 94.4, 99.3, 33.9, 32.5, 61.2, 62.7, 43.8, 157.2, 270.2, 225.3, 279.3, 442.0, 29.6, 36.0, 56.3, 54.0, 32.4, 64.0, 68.0, 316.7, 494.4, 112.3, 132.3, 168.2, 275.6, 301.8, 448.8, 214.2, 255.1,
]

OURS_ND = [
    15.3, 14.7, 20.3, 30.7, 14.4, 62.6, 81.6, 32.9, 33.2, 81.7, 95.6, 30.4, 31.3, 56.6, 63.9, 38.6, 146.0, 229.8, 183.8, 251.4, 471.3, 21.6, 23.8, 63.7, 52.1, 36.2, 57.3, 91.2, 275.1, 465.3, 119.7, 171.3, 152.1, 173.7, 280.5, 471.2, 200.1, 196.3,
]

OPST_DET = [
    10.4, 10.0, 26.3, 34.6, 8.8, 57.3, 70.5, 27.1, 28.7, 77.1, 75.1, 35.3, 34.8, 39.3, 51.5, 37.1, 122.5, 178.1, 141.8, 184.8, 306.0, 38.5, 36.4, 72.1, 61.8, 38.6, 65.8, 59.5, 248.4, 396.1, 89.6, 93.1, 156.2, 179.1, 258.3, 304.1, 141.7, 181.4,
]

OPST_ND = [
    10.3, 10.0, 20.6, 23.5, 8.9, 47.3, 58.1, 23.2, 27.7, 43.6, 55.9, 22.2, 23.0, 32.3, 48.0, 30.4, 104.5, 157.6, 97.8, 164.0, 271.7, 24.9, 26.5, 29.3, 27.6, 28.6, 37.2, 50.5, 176.9, 325.1, 70.9, 89.9, 86.0, 130.9, 178.4, 271.2, 114.6, 133.4,
]

N_BSND = 21
N_TND = 17
