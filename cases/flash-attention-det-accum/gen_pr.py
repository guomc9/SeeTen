#!/usr/bin/env python3
"""Generate PR.md (the PR write-up for the det-bwd perf work) from the same
sources the deck uses: perf_matrix.py (median-of-25 kernel times),
profile_data.py (msprof PipeUtilization), and the figures embedded in
out/v3-index-schedules.pptx.

Run:  python gen_pr.py          (writes figs/*.png and PR.md)
"""
from __future__ import annotations

import math
import os
import shutil

import perf_matrix as pm
import profile_data as pf
from draw_case import SIZES, _rate, _size_class, _trunc2
from pptx import Presentation

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = os.path.join(HERE, "out", "v3-index-schedules.pptx")
FIGS = os.path.join(HERE, "figs")
OUT = os.path.join(HERE, "PR.md")

# 图：幻灯片序号 → 文件名（9 页各一张；确定性开销 / 确定性 vs 确定性 / 非确定性 × 小中大）
FIG_SLIDES = {
    19: "det-overhead-small.png", 20: "det-overhead-mid.png",
    21: "det-overhead-large.png",
    22: "det-vs-det-small.png", 23: "det-vs-det-mid.png",
    24: "det-vs-det-large.png",
    25: "nd-vs-nd-small.png", 26: "nd-vs-nd-mid.png", 27: "nd-vs-nd-large.png",
}


def extract_figs():
    os.makedirs(FIGS, exist_ok=True)
    prs = Presentation(DECK)
    for i, slide in enumerate(prs.slides, 1):
        name = FIG_SLIDES.get(i)
        if not name:
            continue
        for sh in slide.shapes:
            if sh.shape_type == 13:                      # PICTURE
                open(os.path.join(FIGS, name), "wb").write(sh.image.blob)
                break


def gm(xs):
    xs = [v for v in xs if v is not None]
    return math.exp(sum(math.log(v) for v in xs) / len(xs)) if xs else None


OD, OND, PD, PND = pm.OURS_DET, pm.OURS_ND, pm.OPST_DET, pm.OPST_ND
DET_R = [None if (a is None or b is None) else b / a for a, b in zip(OD, PD)]
ND_R = [None if (a is None or b is None) else b / a for a, b in zip(OND, PND)]
PEN_O = [d / n for d, n in zip(OD, OND)]
PEN_P = [None if (d is None or n is None) else d / n for d, n in zip(PD, PND)]


def idx_of(lay=None, sz=None):
    return [i for i, c in enumerate(pm.CASES)
            if (lay is None or c[1] == lay)
            and (sz is None or _size_class(c[0]) == sz)]


def fnum(v, spec=".1f"):
    return "—" if v is None else f"{v:{spec}}"


def rnum(v):                       # 比值：截断两位，与 PPT 一致
    return "—" if v is None else f"{_trunc2(v):.2f}"


def group_gm_table(ratio, with_pass=True):
    head = "| 分组 | case 数 | 小 shape | 中 shape | 大 shape |\n|---|---:|---:|---:|---:|\n"
    rows = ""
    for lay in ("BSND", "TND"):
        cells = []
        for sz in SIZES:
            idx = idx_of(lay, sz)
            v = gm([ratio[i] for i in idx])
            cells.append(f"{v:.3f}" + (f"（{_rate([ratio[i] for i in idx]):.0%}）"
                                       if with_pass else ""))
        rows += f"| {lay} | {len(idx_of(lay))} | " + " | ".join(cells) + " |\n"
    return head + rows


def full_matrix_table():
    head = ("| # | case | shape (b n g s2 s1 d causal/non-causal) | ours det | ours nd | "
            "opst det | opst nd | ours det/nd | opst det/nd | det ratio | nd ratio |\n"
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    body = ""
    for i, (name, lay, _) in enumerate(pm.CASES):
        body += (f"| {i+1} | {name} | {pm.SHAPE[i]} | {fnum(OD[i])} | {fnum(OND[i])} | "
                 f"{fnum(PD[i])} | {fnum(PND[i])} | {rnum(PEN_O[i])} | {rnum(PEN_P[i])} | "
                 f"{rnum(DET_R[i])} | {rnum(ND_R[i])} |\n")
    for lay in ("BSND", "TND"):
        idx = idx_of(lay)
        body += (f"| GM | {lay} |  | {gm([OD[i] for i in idx]):.1f} | "
                 f"{gm([OND[i] for i in idx]):.1f} | {gm([PD[i] for i in idx]):.1f} | "
                 f"{gm([PND[i] for i in idx]):.1f} | "
                 f"{gm([PEN_O[i] for i in idx]):.2f} | {gm([PEN_P[i] for i in idx]):.2f} | "
                 f"{gm([DET_R[i] for i in idx]):.2f} | {gm([ND_R[i] for i in idx]):.2f} |\n")
        body += (f"| pass | {lay} |  |  |  |  |  |  |  | "
                 f"{_rate([DET_R[i] for i in idx]):.0%} | {_rate([ND_R[i] for i in idx]):.0%} |\n")
    return head + body


def pipe_table(rows):
    head = ("| case | 实现 | duration | MAC | MTE2 | MTE1 | fixpipe | scal_c | vec | "
            "scal_v | cube% |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    return head + "".join(
        "| " + " | ".join([tag, impl] + [f"{v:.1f}" for v in vals]) + " |\n"
        for tag, impl, vals in rows)


COLS_HDR = ["duration", "MAC", "MTE2", "MTE1", "fixpipe", "scal_c", "vec", "scal_v", "cube%"]


def pipe_rows(rows):
    return [(tag, impl, vals) for tag, impl, vals in rows]


def stats_block():
    all_idx, bs, tn = idx_of(), idx_of("BSND"), idx_of("TND")
    le = sum(1 for i in all_idx if PEN_P[i] is None or PEN_O[i] <= PEN_P[i])
    return (f"- 确定性开销（det/nd）：本实现 GM {gm([PEN_O[i] for i in all_idx]):.3f}，"
            f"opst GM {gm([PEN_P[i] for i in all_idx]):.3f}；"
            f"逐 case 比较 **{le}/38** 个本实现开销 ≤ opst\n"
            f"- det-vs-det：GM {gm([DET_R[i] for i in all_idx]):.3f}（BSND "
            f"{gm([DET_R[i] for i in bs]):.3f} / TND {gm([DET_R[i] for i in tn]):.3f}），"
            f"达标 {_rate([DET_R[i] for i in all_idx]):.0%}\n"
            f"- nd-vs-nd：GM {gm([ND_R[i] for i in all_idx]):.3f}（BSND "
            f"{gm([ND_R[i] for i in bs]):.3f} / TND {gm([ND_R[i] for i in tn]):.3f}），"
            f"达标 {_rate([ND_R[i] for i in all_idx]):.0%}")


def main():
    extract_figs()
    doc = f"""# PR：确定性反向（BN2S2 + TND causal 调度）性能对比与分析

源分支：`det-cmp-v3-swizzle`（HEAD `02c043b`）
目标分支：`integration/FAG-V3-A5`（基线 `13e835c`「cube Optimize」已并入，PR 无冲突）

## Related Issue

支持 FAG v3（Ascend950）反向的**确定性分支**（deterministic bwd）：补齐 TND
causal 专用调度与 TND ragged flat 分区，并完成与 ops-transformer（opst）的性能
对齐。（仓库内无对应 issue 编号）

## Summary

本 PR 让 `deterministic=True` 的反向覆盖下列布局，并给出与 ops-transformer 的
达标情况。口径：msprof device 侧 kernel 时间（`Task Duration`），**median of 25**
（warmup 5 + repeat 20）；比值 = opst / 本实现，**≥0.8 达标**。

**支持的布局**

| 维度 | 覆盖 |
|---|---|
| layout | BSND（dense / causal）、TND（dense / causal，含 ragged / 不等长分段） |
| head 结构 | MHA / GQA / MQA（n2 = 1~8，g = 1~4） |
| head dim | 64 / 128 |
| 形状 | 方阵、矩形（sq ≠ sk）、非对齐尺寸（如 33×77）、奇 batch |
| 前提 | `deterministic=True` 走 BN2S2 调度（`mha_bwd.cpp` 显式校验） |

**每种布局的性能达标情况**（38 case = BSND 21 + TND 17）

| layout | 确定性 vs 确定性 | 小 shape | 中 shape | 大 shape | 非确定性 vs 非确定性 | 确定性开销 ours / opst |
|---|---|---|---|---|---|---|
| BSND | 0.683（29%） | 0.637（40%） | 0.767（36%） | 0.567（0%） | 0.681（5%） | 1.222 / 1.226 |
| TND | **0.819（41%）** | **1.101（100%）** | 0.665（0%） | 0.666（0%） | 0.655（24%） | **1.158 / 1.447** |
| 合计 | 0.741（34%） | — | — | — | 0.669（13%） | **1.193 / 1.320**（23/38 个开销 ≤ opst） |

一句话：确定性开销整体优于 opst（1.193 vs 1.320）；确定性核时 TND 整体达标
（0.819，小档 100%），BSND 小档 40%、中/大档仍有差距（0.57–0.77）；非确定性
路径的差距来自既有主流水，与本 PR 的确定性改动无关（分 pipe 归因见 Validation）。

## Validation

### 性能对比：确定性开销

倍率 = det 核时 / nd 核时（>1 = det 更慢）；虚线 = 1.0；横轴 = case 序号 · 数据量
（MB）。加粗 = 双方更优的 det / nd 核时。

| 小 shape | 中 shape | 大 shape |
|---|---|---|
| ![确定性开销（小）](figs/det-overhead-small.png) | ![确定性开销（中）](figs/det-overhead-mid.png) | ![确定性开销（大）](figs/det-overhead-large.png) |

| 分组 | case 数 | 小 shape | 中 shape | 大 shape |
|---|---:|---:|---:|---:|
"""
    for lay in ("BSND", "TND"):
        cells = []
        for sz in SIZES:
            idx = idx_of(lay, sz)
            cells.append(f"{gm([PEN_O[i] for i in idx]):.3f} / "
                         f"{gm([PEN_P[i] for i in idx]):.3f}")
        doc += f"| {lay} | {len(idx_of(lay))} | " + " | ".join(cells) + " |\n"
    all_i = idx_of()
    doc += (f"\n跨档合并（38 case）：ours **{gm([PEN_O[i] for i in all_i]):.3f}** / "
            f"opst {gm([PEN_P[i] for i in all_i]):.3f}；逐 case 比较 "
            f"**{sum(1 for i in all_i if PEN_P[i] is None or PEN_O[i] <= PEN_P[i])}/38** "
            f"个本实现开销 ≤ opst。\n")

    doc += f"""
### 性能对比：确定性 vs 确定性

比值 = opst / 本实现（≥0.8 达标，<0.8 的柱标灰）；虚线 = 0.8 目标线。

| 小 shape | 中 shape | 大 shape |
|---|---|---|
| ![确定性 vs 确定性（小）](figs/det-vs-det-small.png) | ![确定性 vs 确定性（中）](figs/det-vs-det-mid.png) | ![确定性 vs 确定性（大）](figs/det-vs-det-large.png) |

{group_gm_table(DET_R)}

### 性能对比：非确定性 vs 非确定性

比值 = opst-nd / 本实现-nd（≥0.8 达标）；该差距为目标主流水既有问题，与本 PR 的
确定性改动无关。

| 小 shape | 中 shape | 大 shape |
|---|---|---|
| ![nd-vs-nd（小）](figs/nd-vs-nd-small.png) | ![nd-vs-nd（中）](figs/nd-vs-nd-mid.png) | ![nd-vs-nd（大）](figs/nd-vs-nd-large.png) |

{group_gm_table(ND_R)}

### vs. ops-transformer 性能对比明细

逐 case 全矩阵（核时 µs，median of 25）；`ours det/nd` 与 `opst det/nd` 为
确定性开销倍率，`det ratio` / `nd ratio` = opst / 本实现；空值 = opst 无法运行
（TND causal 要求 mask Skv = 2048）。

{full_matrix_table()}
### Profiling：BSND（0.26MB → 41.9MB，五档典型案例）

shape：1) 0.26MB 2×33×77 H4/4 D64 causal　2) 0.33MB 1×128×128 H2/2 D128 causal　
3) 0.92MB 2×200×300 H4/2 D64 causal　4) 10.5MB 1×1024² H8 D128 non-causal　
5) 41.9MB 1×4096² H4 D128 causal

{pipe_table(pf.BSND_ROWS)}
- 0.26 / 0.33 MB：各 pipe ≤0.5 µs、MAC 0.1 µs，而 duration 20–34 µs ⇒ 差距 100%
  在固定开销（启动 + 轮次/同步结构），实测落后 det 2.3–2.4×、nd 1.4–1.7×；
- 0.92 MB 起 det 占优（实测 1.09×）；中/大档 det 缺口集中在 MTE2 与 fixpipe
  （+26.6 / +8.9、+44.8 / +35.0），nd 各口 ≤ opst 而 duration 仍 1.35–1.49×。

### Profiling：TND causal（小 / 中 / 大典型案例）

shape：1) 小 2 段 256+384 H4 D128　2) 中 2×2048 H8 D128　3) 大 4×2048 H4 D128
（均 causal；数据量 3.3MB / 41.9MB / 41.9MB）

{pipe_table(pf.TND_ROWS)}
- 中/大档 nd 每条 pipe ≤ opst、duration 1.45–1.51× ⇒ 重叠/串联受限；
- det 缺口 = MTE2 +62.5 / +54.3、fixpipe +80.9 / +64.1；MAC、scalar 均不高于 opst；
- 小档（3.3MB）本实现占优：实测 nd 1.19×、det 1.29×。

### Profiling 结论与优化优先级

| 观察 | 证据 | 判断 | 行动 |
|---|---|---|---|
| nd 主流水（共同瓶颈） | TND 中/大：duration 283.7 / 282.0 vs opst 188.4 / 194.0（1.51× / 1.45×），但 MTE2、fixpipe、scal_c 均更低；cube% 86 / 89 vs 95 / 95 | 重叠 / 每任务串联受限 | ① 主流水重叠（round、barrier、双缓冲） |
| det 增量在加载与写回 | TND 中：MTE2 +62.5（194.4 vs 131.9）、fixpipe +80.9（261.8 vs 180.9）；TND 大 +54.3 / +64.1；BSND 中 +26.6 / +8.9、大 +44.8 / +35.0；MAC 均不高于 opst | 重复加载 Q / Kᵀ / K / dY + fp32 原子累加与每列 cast | ② BN2S2 det 引入 KV 驻留 + L0C 累积 |
| scalar / 解码不是瓶颈 | nd scal_c 全面低于 opst（78.1 / 75.5 vs 94.4 / 96.1；20.9 / 67.4 vs 29.6 / 77.8）；det 仅 +21.0/+14.0/+0.6 | 不是瓶颈 | ③ 解码 / scalar 不做 |
| 极小 shape（0.26–0.33MB）仍未占优 | 0.33MB：det 24.6 vs 10.4（2.4×）、nd 15.0 vs 10.4（1.4×）；0.26MB：20.2 vs 8.9（2.3×）、14.6 vs 8.9（1.6×）；全部 pipe ≤0.5 µs、MAC 0.1 µs，duration 22–34 µs | 固定开销（启动 + 轮次/同步结构） | ④ 固定开销专项（低优先级，暂不投入） |
| ≥0.9MB 已占优或持平 | 0.92MB：det 24.8 vs 26.9（1.09×）、nd 20.5 vs 20.4（1.00×）；TND 3.3MB：nd 1.19×、det 1.29× | 规模够大后固定开销摊薄 | 维持现状 |

## Additional Information

- **测试覆盖**：`tests/test_flash_attn_npu_v3_bwd_det.py` 38 case（BSND 21 + TND 17），
  每 case 跑 det 与 nondet 两条路径，校验 golden 一致、det 多次调用逐位一致、
  det 与 nd 互验；causal 用例按每 batch `sq ≤ sk` 生成（否则 golden 自身退化 NaN）。
- **对比对象的可运行边界**：opst 的 TND causal 要求 `atten_mask` 的 Skv 恰为 2048，
  单段长度 > 2048 的 causal 用例 opst 无法运行（明细表中记为空缺）。
- **确定性前提**：`deterministic=True` 必须落到 BN2S2 调度（有显式校验，不再回退
  旧流内方案）；非确定路径保持原实例化（`09b51d6` 隔离）。
- **极小档与中/大档结论相反**：0.92 MB 起 det 占优，而 0.26–0.33 MB 档因固定开销
  落后 2.3–2.4×（det）；引用"小 shape 已占优"时需注明档位。
- **nd 差距的来源**：合并目标「cube Optimize」后 nd 与纯目标构建一致（A/B 对照通过），
  该差距为分支既有主流水问题，非本 PR 引入；目标自身的优化亦使部分 mid nd shape
  变慢（GQA s1024 nc 69→93 µs、square nc 73→82、rect 28→33）。
- **FWD 侧已知问题（仅记录，不影响本 PR 的 bwd 接口）**：`flash_attn_func` /
  `flash_attn_varlen_func` 返回的 `softmax_lse` 目前为 `+inf`（fwd 未落地 lse
  写出），走 autograd 端到端时梯度会全 0；直接调用 bwd 接口（传入合法 lse）
  不受影响。基线分支同样存在。
- 数据源：SeeTen 案例 `flash-attention-det-accum`（`perf_matrix.py` /
  `profile_data.py` / `gen_pr.py`，`check_case.py` 逐格回读校验）。
"""
    open(OUT, "w", encoding="utf-8").write(doc)
    # 同步到 flash-attention-npu/.docs（PR 用：PR.md + figs/）
    docs = "/data/g00977778/flash-attention-npu/.docs"
    if os.path.isdir(docs):
        docs_figs = os.path.join(docs, "figs")
        os.makedirs(docs_figs, exist_ok=True)
        for fn in os.listdir(FIGS):
            shutil.copyfile(os.path.join(FIGS, fn), os.path.join(docs_figs, fn))
        shutil.copyfile(OUT, os.path.join(docs, "fag_v3_det_bwd_perf_pr.md"))
        print(f"copied to {docs}/fag_v3_det_bwd_perf_pr.md and {docs}/figs/")
    print(f"wrote {OUT} ({len(doc)} chars) and {len(os.listdir(FIGS))} figs")


if __name__ == "__main__":
    main()
