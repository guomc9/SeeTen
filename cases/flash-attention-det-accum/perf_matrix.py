"""性能矩阵数据（msprof device 侧 kernel 时间，min of 25，μs）。

本仓库 = det-cmp-v3-swizzle @ 合并 integration/FAG-V3-A5(cube Optimize) 后；
opst = 参考仓库（det 用 torch.use_deterministic_algorithms(True)）。
口径：msprof Task Duration 最小值（warmup 5 + repeat 20），非 event record。
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
    "b1 128×128\nn2 g1 d128 c",
    "b1 128×128\nn2 g1 d128 nc",
    "b2 200×300\nn2 g2 d64 c",
    "b2 300×500\nn1 g4 d64 nc",
    "b2 33×77\nn4 g1 d64 c",
    "b1 1024×1024\nn8 g1 d128 c",
    "b1 1024×1024\nn8 g1 d128 nc",
    "b2 333×777\nn4 g1 d64 c",
    "b2 777×333\nn4 g1 d64 nc",
    "b1 1024×1024\nn2 g4 d128 c",
    "b1 1024×1024\nn2 g4 d128 nc",
    "b2 300×500\nn1 g4 d64 c",
    "b2 300×500\nn1 g4 d64 nc",
    "b2 500×900\nn3 g2 d128 c",
    "b2 500×900\nn3 g2 d128 nc",
    "b2 777×333\nn3 g2 d64 nc",
    "b1 2048×2048\nn8 g1 d128 c",
    "b1 2048×2048\nn8 g1 d128 nc",
    "b1 2048×2048\nn2 g4 d128 c",
    "b1 4096×4096\nn4 g1 d128 c",
    "b1 4096×4096\nn4 g1 d128 nc",
    "b2 256+384/256+384\nn4 g1 d128 c",
    "b2 256+384/256+384\nn4 g1 d128 nc",
    "b2 100+800/300+1300\nn1 g4 d64 c",
    "b2 100+800/300+400\nn1 g4 d64 nc",
    "b2 100+800/300+400\nn4 g1 d64 nc",
    "b2 512+1024/768+1280\nn2 g2 d128 c",
    "b2 512+1024/768+1280\nn2 g2 d128 nc",
    "b2 2048×2048\nn8 g1 d128 c",
    "b2 2048×2048\nn8 g1 d128 nc",
    "b2 1024×1024\nn2 g4 d128 c",
    "b2 1024×1024\nn2 g4 d128 nc",
    "b8 512×512\nn8 g1 d128 c",
    "b8 512×512\nn8 g1 d128 nc",
    "b4 2048×2048\nn4 g1 d128 c",
    "b1 4096×4096\nn4 g1 d128 nc",
    "b4 1024×1024\nn2 g4 d128 c",
    "b4 2048×2048\nn1 g4 d64 c",
]

# 单行 shape（表格用）：b n g s2 s1 d + c/nc
SHAPE = [
    "b1 n2 g1 s2=128 s1=128 d128 c",
    "b1 n2 g1 s2=128 s1=128 d128 nc",
    "b2 n2 g2 s2=300 s1=200 d64 c",
    "b2 n1 g4 s2=500 s1=300 d64 nc",
    "b2 n4 g1 s2=77 s1=33 d64 c",
    "b1 n8 g1 s2=1024 s1=1024 d128 c",
    "b1 n8 g1 s2=1024 s1=1024 d128 nc",
    "b2 n4 g1 s2=777 s1=333 d64 c",
    "b2 n4 g1 s2=333 s1=777 d64 nc",
    "b1 n2 g4 s2=1024 s1=1024 d128 c",
    "b1 n2 g4 s2=1024 s1=1024 d128 nc",
    "b2 n1 g4 s2=500 s1=300 d64 c",
    "b2 n1 g4 s2=500 s1=300 d64 nc",
    "b2 n3 g2 s2=900 s1=500 d128 c",
    "b2 n3 g2 s2=900 s1=500 d128 nc",
    "b2 n3 g2 s2=333 s1=777 d64 nc",
    "b1 n8 g1 s2=2048 s1=2048 d128 c",
    "b1 n8 g1 s2=2048 s1=2048 d128 nc",
    "b1 n2 g4 s2=2048 s1=2048 d128 c",
    "b1 n4 g1 s2=4096 s1=4096 d128 c",
    "b1 n4 g1 s2=4096 s1=4096 d128 nc",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 c",
    "b2 n4 g1 s2=256+384 s1=256+384 d128 nc",
    "b2 n1 g4 s2=300+1300 s1=100+800 d64 c",
    "b2 n1 g4 s2=300+400 s1=100+800 d64 nc",
    "b2 n4 g1 s2=300+400 s1=100+800 d64 nc",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 c",
    "b2 n2 g2 s2=768+1280 s1=512+1024 d128 nc",
    "b2 n8 g1 s2=2048 s1=2048 d128 c",
    "b2 n8 g1 s2=2048 s1=2048 d128 nc",
    "b2 n2 g4 s2=1024 s1=1024 d128 c",
    "b2 n2 g4 s2=1024 s1=1024 d128 nc",
    "b8 n8 g1 s2=512 s1=512 d128 c",
    "b8 n8 g1 s2=512 s1=512 d128 nc",
    "b4 n4 g1 s2=2048 s1=2048 d128 c",
    "b1 n4 g1 s2=4096 s1=4096 d128 nc",
    "b4 n2 g4 s2=1024 s1=1024 d128 c",
    "b4 n1 g4 s2=2048 s1=2048 d64 c",
]

# 数据 size（MB，bf16；q/out/dout 各一份 + k/v 各一份）
SIZE_MB = [
    0.33, 0.33, 0.92, 1.18, 0.26, 10.49, 10.49, 2.61, 3.07, 7.34, 7.34, 1.18, 1.18, 7.37, 7.37, 4.09, 20.97, 20.97, 14.68, 20.97, 20.97, 3.28, 3.28, 1.79, 1.56, 2.10, 6.82, 6.82, 41.94, 41.94, 14.68, 14.68, 41.94, 41.94, 41.94, 20.97, 29.36, 14.68,
]

OURS_DET = [
    23.5, 18.0, 23.9, 33.9, 19.1, 74.4, 107.3, 37.7, 36.5, 98.1, 103.3, 35.6, 33.8, 65.2, 64.3, 42.0, 183.8, 317.1, 247.5, 329.4, 540.7, 29.2, 35.5, 55.3, 52.5, 33.1, 63.5, 66.4, 379.4, 594.9, 112.9, 145.1, 180.5, 301.4, 326.0, 529.1, 210.9, 278.2,
]

OURS_ND = [
    14.5, 14.6, 19.8, 30.7, 13.9, 61.6, 82.1, 30.4, 32.4, 81.1, 96.3, 29.3, 29.6, 55.3, 60.0, 37.7, 143.2, 222.2, 182.5, 247.9, 444.5, 20.6, 22.4, 60.7, 49.7, 34.0, 53.4, 88.6, 265.0, 446.4, 118.8, 167.3, 144.8, 164.2, 271.9, 458.8, 198.2, 190.2,
]

OPST_DET = [
    10.1, 9.8, 25.0, 33.2, 8.5, 59.5, 70.2, 25.2, 26.7, 75.9, 73.2, 33.1, 33.1, 37.2, 50.2, 35.2, 118.3, 176.7, 140.0, 177.7, 300.7, 37.0, 35.7, 71.2, 61.3, 37.4, 65.2, 58.1, 252.6, 365.5, 88.1, 91.0, 140.9, 180.9, 249.0, 304.3, 143.7, 185.5,
]

OPST_ND = [
    10.2, 9.8, 19.1, 22.7, 8.6, 45.8, 57.5, 22.1, 25.4, 42.3, 54.5, 21.3, 21.8, 31.1, 46.6, 29.4, 103.4, 154.4, 94.1, 163.2, 277.3, 24.6, 24.3, 27.9, 25.6, 26.8, 36.2, 49.0, 181.3, 332.9, 63.3, 87.8, 79.5, 134.1, 172.4, 269.5, 110.4, 131.5,
]

N_BSND = 21
N_TND = 17
