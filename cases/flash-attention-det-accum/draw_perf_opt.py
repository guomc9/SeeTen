#!/usr/bin/env python3
"""v3-perf-opt.pptx：v3 → v3.1 → v3.2 版本性能对比（第 10 章式组织）。

数据源（三方交错 bench，median of 25，msprof Task Duration）：
  /data/g00977778/tmp-prof/vcmp_{bsnd,tnd}.csv   v3@02c043b / v3.1@af9c56b / v3.2@1909a89
  /data/g00977778/tmp-prof/latewait_opst.csv     opst（参考实现）det
配色 = DeepSeek benchmark 家族：opst 卡其、v3 灰、v3.1 浅蓝、v3.2 深蓝斜纹。
"""
import csv
import os
import sys

sys.path.insert(0, "/data/g00977778/SeeTen/scripts")
import seeten_draw as sd

TMP = "/data/g00977778/tmp-prof"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import perf_matrix as pm

V3, V31, V32, OPST = sd.PERF_REF, sd.PERF_SELF_ALT, sd.PERF_SELF, sd.PERF_ACCENT
GRAY = "9A9A9A"

SIZES = {
    "bsnd_small_mha_causal": 0.3, "bsnd_small_mha_nc": 0.3,
    "bsnd_small_gqa_tail_causal": 0.9, "bsnd_small_mqa_tail_nc": 1.2,
    "bsnd_tiny_unaligned_causal": 0.3,
    "bsnd_mid_mha_square_causal": 10.5, "bsnd_mid_mha_square_nc": 10.5,
    "bsnd_mid_mha_rect_causal": 2.6, "bsnd_mid_mha_rect_nc": 3.1,
    "bsnd_mid_gqa_square_causal": 7.3, "bsnd_mid_gqa_square_nc": 7.3,
    "bsnd_mid_mqa_causal": 1.2, "bsnd_mid_mqa_nc": 1.2,
    "bsnd_mid_gqa_rect_causal": 7.4, "bsnd_mid_gqa_rect_nc": 7.4,
    "bsnd_mid_mha_hd64_nc": 4.1,
    "bsnd_long_mha_causal": 21.0, "bsnd_long_mha_nc": 21.0,
    "bsnd_long_gqa_causal": 14.7, "bsnd_large_mha_causal": 21.0,
    "bsnd_large_mha_nc": 21.0,
    "tnd_small_mha_causal": 3.3, "tnd_small_mha_nc": 3.3,
    "tnd_ragged_mqa_causal": 1.8, "tnd_ragged_mqa_nc": 1.6,
    "tnd_ragged_mha_nc": 2.1, "tnd_ragged_gqa_causal": 6.8,
    "tnd_ragged_gqa_nc": 6.8,
    "tnd_eq_mha_causal": 41.9, "tnd_eq_mha_nc": 41.9,
    "tnd_eq_gqa_causal": 14.7, "tnd_eq_gqa_nc": 14.7,
    "tnd_pack8_mha_causal": 41.9, "tnd_pack8_mha_nc": 41.9,
    "tnd_large4_mha_causal": 41.9, "tnd_large_mha_nc": 21.0,
    "tnd_large4_gqa_causal": 29.4, "tnd_large4_mqa_causal": 14.7,
}

LABEL = {name: label for name, _, label in pm.CASES}
SHAPE = {name: shp for (name, _, _), shp in zip(pm.CASES, pm.SHAPE)}
BSND = [n for n, lay, _ in pm.CASES if lay == "BSND"]
TND = [n for n, lay, _ in pm.CASES if lay == "TND"]
GIDX = {n: i + 1 for i, n in enumerate(BSND + TND)}
BANDS = [("小", BSND[:5], TND[:7]), ("中", BSND[5:16], TND[7:13]),
         ("大", BSND[16:], TND[13:])]
BAND_EN = {"小": "small", "中": "mid", "大": "large"}


def load_vcmp():
    d = {}
    for f in ("vcmp_bsnd.csv", "vcmp_tnd.csv"):
        for r in csv.DictReader(open(f"{TMP}/{f}")):
            d.setdefault(r["case"], {})[r["variant"]] = float(r["median_us"])
    op = {}
    for r in csv.DictReader(open(f"{TMP}/latewait_opst.csv")):
        if r["det_med_us"]:
            op[r["case"].split(":", 1)[-1]] = float(r["det_med_us"])
    return d, op


VC, OP = load_vcmp()


def gm(xs):
    import math
    xs = [x for x in xs if x and x > 0]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else 0


def v(name, ver):
    return VC[name][ver]


def ratio(a, b):
    return a / b if a and b else None


# ================================================================ 页面 0：总览

def draw_overview(prs):
    s = sd.blank_slide(prs)
    sd.title(s, "0. 总览：v3 → v3.1 → v3.2 确定性反向性能递进", y=0.62)
    sd.text(s, 0.73, 1.22,
            "同一测试矩阵（38 case = BSND 21 + TND 17）、同一会话三方交错采集（msprof Task Duration，median of 25）；"
            "nd 路径三版同实例化（无回归），对比针对 det。",
            w=15.2, h=0.55, size=13.5, color=sd.BODY_TEXT)

    rows = [
        ("v3", "02c043b", "BN2S2 det 调度 + TND causal/flat 调度（PR 基线）",
         "—", f"{gm([v(n, 'v3') for n in BSND + TND]):.1f}"),
        ("v3.1", "af9c56b", "idle-core trim（小 shape 按调度所需最小核数启动）"
         "+ tiny 单块方格 causal 改 dense",
         "小档 −21%", f"{gm([v(n, 'v3.1') for n in BSND + TND]):.1f}"),
        ("v3.2", "1909a89", "late-wait 轮屏障：WAIT 延后一轮、交替奇偶 flag，"
         "前端滑入屏障阴影（排序语义不变）",
         "中大档 −5~−10%", f"{gm([v(n, 'v3.2') for n in BSND + TND]):.1f}"),
    ]
    sd.spec_table(s, 0.73, 2.02, ("版本", "commit", "机制改动", "主要收益", "det 几何均值 µs"),
                  rows, col_w=(0.95, 1.55, 8.30, 2.20, 2.30),
                  row_h=[0.50, 0.86, 0.86, 0.86], zebra=True, size=12.5)

    sd.text(s, 0.73, 5.30, "分档几何均值（det 核时 µs，38 case 三方交错）",
            w=8.0, h=0.30, size=15, bold=True)
    bands_rows = []
    for bn, b, t in BANDS:
        names = b + t
        g3 = gm([v(n, "v3") for n in names])
        g31 = gm([v(n, "v3.1") for n in names])
        g32 = gm([v(n, "v3.2") for n in names])
        bands_rows.append((bn, f"{g3:.1f}", f"{g31:.1f}", f"{g32:.1f}",
                           f"{g31 / g3:.3f}", f"{g32 / g3:.3f}"))
    bands_rows.append(("合计", f"{gm([v(n, 'v3') for n in BSND + TND]):.1f}",
                       f"{gm([v(n, 'v3.1') for n in BSND + TND]):.1f}",
                       f"{gm([v(n, 'v3.2') for n in BSND + TND]):.1f}",
                       f"{gm([v(n, 'v3.1') for n in BSND + TND]) / gm([v(n, 'v3') for n in BSND + TND]):.3f}",
                       f"{gm([v(n, 'v3.2') for n in BSND + TND]) / gm([v(n, 'v3') for n in BSND + TND]):.3f}"))
    sd.spec_table(s, 0.73, 5.70, ("档位", "v3", "v3.1", "v3.2", "v3.1/v3", "v3.2/v3"),
                  bands_rows, col_w=(1.45, 1.30, 1.30, 1.30, 1.45, 1.45),
                  row_h=[0.44] + [0.42] * len(bands_rows), zebra=True, size=12.5)

    # 头部图：三版 + opst 的分档几何均值
    panels = [dict(
        title="det geomean (us, lower is better)",
        groups=[BAND_EN[bn] for bn, _, _ in BANDS],
        series=[
            ("opst det", [gm([OP[n] for n in b + t if n in OP]) for _, b, t in BANDS], OPST),
            ("v3 @02c043b", [gm([v(n, "v3") for n in b + t]) for _, b, t in BANDS], V3),
            ("v3.1 @af9c56b", [gm([v(n, "v3.1") for n in b + t]) for _, b, t in BANDS], V31),
            ("v3.2 @1909a89", [gm([v(n, "v3.2") for n in b + t]) for _, b, t in BANDS], V32),
        ],
        ylabel="us", best=3, show_values=True, value_size=9, bar_w=0.20)]
    sd.perf_figure(s, 9.55, 5.55, 6.15, 4.30, panels)
    sd.note(s, 0.73, 10.55,
            "配色（DeepSeek benchmark 家族）：卡其 = opst 参考、灰 = v3、浅蓝 = v3.1、深蓝斜纹 = v3.2（本版主角）。"
            "v3.2/v3 全矩阵几何均值 0.904；v3.2 的 det/nd 开销 1.076 已低于 opst 1.319。",
            w=15.2, h=0.62, size=12.5)
    return s


# ================================================================ 页面 1.x：分档版本对比

def band_table_rows(names):
    rows = []
    for n in names:
        a, b, c, o = v(n, "v3"), v(n, "v3.1"), v(n, "v3.2"), OP.get(n)
        rows.append((f"#{GIDX[n]}", SHAPE[n],
                     f"{a:.1f}", f"{b:.1f}", f"{c:.1f}",
                     f"{o:.1f}" if o else "—",
                     f"{a / c:.2f}", f"{o / c:.2f}" if o else "—"))
    g3 = gm([v(n, "v3") for n in names])
    g31 = gm([v(n, "v3.1") for n in names])
    g32 = gm([v(n, "v3.2") for n in names])
    go = gm([OP[n] for n in names if n in OP])
    rows.append(("GM", "", f"{g3:.1f}", f"{g31:.1f}", f"{g32:.1f}",
                 f"{go:.1f}", f"{g3 / g32:.2f}", f"{go / g32:.2f}"))
    return rows


def draw_band_page(prs, num, bn, b, t):
    s = sd.blank_slide(prs)
    sd.title(s, f"{num}. 版本对比：{bn} shape（det 核时 µs）", y=0.62)
    sd.text(s, 0.73, 1.20,
            "三方交错采集（median of 25）· 柱越低越好 · v3.2÷v3 = 提速倍率（>1 好）· opst÷v3.2 = 对参考达标度（≥0.8 达标）",
            w=15.2, h=0.30, size=12.0, color=sd.BODY_TEXT)

    panels = []
    for lay, names in (("BSND", b), ("TND", t)):
        panels.append(dict(
            title=f"{lay} {BAND_EN[bn]} ({len(names)})",
            groups=[f"#{GIDX[n]}·{SIZES[n]}MB" for n in names],
            series=[
                ("opst", [OP.get(n, 0.0) for n in names], OPST),
                ("v3", [v(n, "v3") for n in names], V3),
                ("v3.1", [v(n, "v3.1") for n in names], V31),
                ("v3.2", [v(n, "v3.2") for n in names], V32),
            ],
            ylabel="us", best=3, show_values=False, xrot=30, bar_w=0.21))
    fig_bottom = sd.perf_figure(s, 0.73, 1.66, 15.2, 4.60, panels)

    ty = fig_bottom + 0.18
    hdr = ("#", "shape", "v3", "v3.1", "v3.2", "opst", "v3.2\n÷v3", "opst\n÷v3.2")
    for x, lay, names in ((0.73, "BSND", b), (8.47, "TND", t)):
        rows = band_table_rows(names)
        n = len(rows)
        row_h = min(0.40, (11.55 - ty - 0.44) / (n + 1))
        sd.text(s, x, ty, f"{lay} {bn}（{len(names)} case）", w=4.0, h=0.28,
                size=13.5, bold=True)
        sd.spec_table(s, x, ty + 0.36, hdr, rows,
                      col_w=(0.44, 3.62, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58),
                      row_h=[0.38] + [row_h] * n, zebra=True, size=9.5,
                      header_size=9.5)
    return s


# ================================================================ 页面 2.1：v3.1 机制

def draw_mech_v31(prs):
    s = sd.blank_slide(prs)
    sd.title(s, "2.1. 机制① v3.1：idle-core trim + tiny 单块 causal 改 dense", y=0.62)
    sd.tag_row(s, 0.73, 1.22, [("commit", "af9c56b"), ("对象", "小 / tiny shape"),
                               ("nd", "无回归（±0.3µs 噪声内）")])

    sd.text(s, 0.73, 1.80, "① idle-core trim：小 shape 不再按 40 核空转启动", w=7.4,
            h=0.30, size=15, bold=True)
    idle_cells = {(0, j): (f"C{j + 1}" if j < 3 else ("…" if j == 3 else ""),
                         0 if j < 3 else 1, 0) for j in range(8)}
    sd.axis_grid(s, 0.73, 2.22, 1, 8, idle_cells, lane_set="cool",
                 cell_in=0.40, shade_count=2)
    sd.text(s, 0.73, 3.12, "v3：按 aicNum=40 启动（空转核也付 det 序言 + 每轮全网格 barrier）",
            w=7.2, h=0.26, size=11.5, color=sd.BODY_TEXT)
    trim_cells = {(0, j): (f"C{j + 1}", 0, 0) for j in range(2)}
    sd.axis_grid(s, 0.73, 3.50, 1, 2, trim_cells, lane_set="cool",
                 cell_in=0.40, shade_count=2)
    sd.text(s, 0.73, 4.40, "v3.1：保持轮数不变，取能维持该轮数的最小核数（如 2 核）",
            w=7.2, h=0.26, size=11.5, color=sd.BODY_TEXT)

    sd.text(s, 8.35, 1.80, "② tiny 单块方格 causal：fold 串行 → dense 并行", w=7.4,
            h=0.30, size=15, bold=True)
    rows_fold = [("第 1 轮", [{"lines": ["B1H1"], "lane": 0, "shade": 0}, None]),
                 ("第 2 轮", [{"lines": ["B2H1"], "lane": 1, "shade": 0}, None])]
    sd.task_matrix(s, 8.35, 2.22, ["C1", "C2"], rows_fold, col_w=1.45, row_h=0.38,
                   cell_size=10.5)
    sd.text(s, 8.35, 3.36, "v3 fold：两个 (B,H) 折进同一 lane，2 轮串行", w=4.6, h=0.26,
            size=11.5, color=sd.BODY_TEXT)
    rows_dense = [("第 1 轮", [{"lines": ["B1H1"], "lane": 0, "shade": 0},
                              {"lines": ["B2H1"], "lane": 1, "shade": 0}])]
    sd.task_matrix(s, 8.35, 3.78, ["C1", "C2"], rows_dense, col_w=1.45, row_h=0.38,
                   cell_size=10.5)
    sd.text(s, 8.35, 4.54, "v3.1 dense + mask：2 核 1 轮并行", w=4.6, h=0.26,
            size=11.5, color=sd.BODY_TEXT)

    sd.text(s, 0.73, 4.86, "收益（三方交错实测，µs）：v3 → v3.1", w=8.0, h=0.30,
            size=15, bold=True)
    names = ["bsnd_small_mha_causal", "bsnd_small_mha_nc",
             "bsnd_tiny_unaligned_causal", "bsnd_small_gqa_tail_causal",
             "bsnd_small_mqa_tail_nc", "bsnd_mid_mha_square_causal",
             "bsnd_long_mha_causal", "tnd_small_mha_causal"]
    rows = []
    for n in names:
        a, b = v(n, "v3"), v(n, "v3.1")
        rows.append((f"#{GIDX[n]}", SHAPE[n], f"{a:.1f}", f"{b:.1f}",
                     f"{a - b:+.1f}", f"{a / b:.2f}"))
    sd.spec_table(s, 0.73, 5.26, ("#", "case", "v3", "v3.1", "Δ", "v3÷v3.1"),
                  rows, col_w=(0.52, 4.20, 0.90, 0.90, 0.90, 1.00),
                  row_h=[0.40] + [0.38] * len(rows), zebra=True, size=11.0)

    sd.note(s, 0.73, 9.10,
            "小档 det 几何均值 24.1 → 19.1（−21%）；tiny causal 的 det 已快于 nd（det/nd 0.89–0.94）。"
            "中 / 大档顺带受益（trim 省掉空转核的序言与 barrier）：BSND 大档 −6.6%。",
            w=15.2, h=0.62, size=12.5)
    return s


# ================================================================ 页面 2.2：v3.2 机制

def _timeline(slide, x, y, title, core_rows, note, cell_w=1.52, row_h=0.46):
    """双核时间线：列 = 时间槽，行 = 快/慢核；格 = (文字, 底色, 字色)。

    一眼看出快核的空等（灰格）与它被谁填满（蓝格）。
    """
    sd.text(slide, x, y, title, w=10.5, h=0.30, size=14.5, bold=True)
    heads = ["核 \\ 时间"] + [f"t{i}" for i in range(1, len(core_rows[0][1]) + 1)]
    tbl = sd._plain_table(slide, x, y + 0.40, 1 + len(core_rows), len(heads),
                          cell_w=int(cell_w * 914400), cell_h=int(row_h * 914400))
    tbl.columns[0].width = sd.Inches(0.92)
    for c, h in enumerate(heads):
        cell = tbl.cell(0, c)
        sd._cell_border(cell)
        sd._fill_cell(cell, sd.ON_BLOCK if c else None)
        sd._write_cell_lines(cell, [h], size=10.5, colors=[sd.TITLE_TEXT])
    for ri, (label, cells) in enumerate(core_rows, start=1):
        hc = tbl.cell(ri, 0)
        sd._cell_border(hc)
        sd._write_cell_lines(hc, [label], size=10.5, colors=[sd.TITLE_TEXT])
        for ci, (txt, fill) in enumerate(cells, start=1):
            cell = tbl.cell(ri, ci)
            sd._cell_border(cell)
            sd._fill_cell(cell, fill)
            lines = txt.split("\n")
            sd._write_cell_lines(cell, lines, size=9.5,
                                 colors=[sd.text_on(fill)] * len(lines))
    sd.fit_table(tbl)
    sd.text(slide, x, y + 0.40 + row_h * (len(core_rows) + 1) + 0.10, note,
            w=10.6, h=0.30, size=11.5, color=sd.BODY_TEXT)
    return y + 0.40 + row_h * (len(core_rows) + 1) + 0.44


def draw_mech_v32(prs):
    s = sd.blank_slide(prs)
    sd.title(s, "2.2. 机制② v3.2：late-wait 轮屏障（交替奇偶 flag）", y=0.62)
    sd.tag_row(s, 0.73, 1.22, [("commit", "1909a89"), ("对象", "全部 det（TND 收益最大）"),
                               ("正确性", "38 case 位级验证全过")])

    FE, BE, SETC, IDLE, NEXT = ("AAC1FF", "4D6BFE", "E8D2A0", "C9C9C9", "D8E2FF")
    # -- v3：轮末立刻 SET+WAIT；快核 t4/t5 两格白等慢核
    y = _timeline(
        s, 0.73, 1.80,
        "v3 —— 轮末 SET(r) 之后立刻 WAIT(r)：快核被挡在屏障上空等",
        [("快核", [("C1/C2", FE), ("C5", FE), ("C34", BE), ("空等", IDLE),
                    ("空等", IDLE), ("下轮\nC1/C2", FE), ("下轮\nC5", FE), ("下轮\nC34", BE)]),
         ("慢核", [("C1/C2", FE), ("C5", FE), ("C34（长）", BE), ("C34（长）", BE),
                    ("SET", SETC), ("下轮\nC1/C2", FE), ("下轮\nC5", FE), ("下轮\nC34", BE)])],
        "灰格 = 快核在屏障上白等慢核（straggler 浪费）：每轮都这样，轮数越多亏得越多")

    # -- v3.2：SET 仍在轮末，WAIT 延后到下一轮 C34 之前；空等被前端填满
    y = _timeline(
        s, 0.73, y + 0.42,
        "v3.2 —— SET(r) 仍在轮末，WAIT(r−1) 挪到本轮 C34 之前：空等被下一轮前端填满",
        [("快核", [("C1/C2", FE), ("C5", FE), ("C34", BE), ("下轮\nC1/C2", NEXT),
                    ("下轮\nC5", NEXT), ("WAIT", SETC), ("下轮\nC34", BE), ("…", FE)]),
         ("慢核", [("C1/C2", FE), ("C5", FE), ("C34（长）", BE), ("C34（长）", BE),
                    ("SET", SETC), ("下轮\nC1/C2", FE), ("下轮\nC5", FE), ("下轮\nC34", BE)])],
        "同一位置：灰格变成下一轮 C1/C2、C5（浅蓝）—— SET 语义不变，dq 仍按轮序，"
        "但屏障等待落进了别人工作的阴影里")

    sd.text(s, 0.73, y + 0.14, "交错 A/B 实测（det，µs，median of 25）", w=8.0,
            h=0.30, size=15, bold=True)
    rows = []
    for n in ["tnd_eq_mha_nc", "tnd_eq_mha_causal", "bsnd_large_mha_nc",
              "bsnd_large_mha_causal", "bsnd_long_mha_causal",
              "bsnd_mid_mha_square_nc"]:
        a, c = v(n, "v3"), v(n, "v3.2")
        rows.append((f"#{GIDX[n]}", SHAPE[n], f"{a:.1f}", f"{c:.1f}",
                     f"{c - a:+.1f}", f"{a / c:.2f}"))
    sd.spec_table(s, 0.73, y + 0.54,
                  ("#", "case", "v3", "v3.2", "Δ", "v3.2\n÷v3"),
                  rows, col_w=(0.50, 3.60, 0.85, 0.85, 0.85, 0.55),
                  row_h=[0.40] + [0.38] * len(rows), zebra=True, size=11.0,
                  header_size=9.5)

    sd.text(s, 9.00, y + 0.14, "轮末 SET/WAIT 的作用", w=6.0, h=0.30, size=15, bold=True)
    sd.text(s, 9.00, y + 0.54,
            "SET(r) = 广播「本核轮 r 的 dq/dk/dv 原子加已落盘」；"
            "WAIT(r−1) = 等全部核的上一轮到齐。",
            w=6.9, h=0.60, size=12.0, color=sd.BODY_TEXT, wrap=True)
    sd.text(s, 9.00, y + 1.24,
            "跨核 fp32 原子加没有交换律，谁先到结果就不同 —— "
            "SET/WAIT 把它钉成全局轮序，这就是逐位确定性的来源。",
            w=6.9, h=0.60, size=12.0, color=sd.BODY_TEXT, wrap=True)
    for i, line in enumerate([
            "· 轮 r 的 dq 原子加仍严格晚于全部核的轮 r−1 写；",
            "· MHA：dk/dv 走核私有 buffer，只有 dq 需要轮序；",
            "· GQA / TND-flat：dv 共享 workspace，WAIT 提前到 C5；",
            "· 两个交替 flag（10/15）让 WAIT 总落在已就绪的旧代上；",
            "· 空轮照等保持代际对齐；drain 等最后一轮代。"]):
        sd.text(s, 9.00, y + 1.94 + i * 0.34, line, w=6.9, h=0.30, size=12.0,
                color=sd.BODY_TEXT)
    sd.note(s, 0.73, 10.60,
            "TND 代表 case 回收 53~88µs（去屏障上限的 60~76%）；BSND 大档 −6~−59µs。38 case 的 det/nd 开销 "
            "1.076 ≤ opst 1.319（31/38 更低）—— det 专项收官，剩余差距 = 共享主流水（nd）。",
            w=15.2, h=0.62, size=12.5)
    return s


# ================================================================ 页面 3.x：全量明细

def draw_detail_page(prs, num, lay, names):
    s = sd.blank_slide(prs)
    sd.title(s, f"{num}. 全量明细：{lay}（det 核时 µs，median of 25）", y=0.62)
    sd.text(s, 0.73, 1.20,
            "v3.2÷v3 = 提速倍率（>1 好）· opst÷v3.2 = 对参考达标度（≥0.8 达标，加粗）· 三方交错采集",
            w=15.2, h=0.30, size=12.0, color=sd.BODY_TEXT)
    rows = band_table_rows(names)
    hdr = ("#", "shape", "v3", "v3.1", "v3.2", "opst", "v3.2÷v3", "opst÷v3.2")
    row_h = min(0.44, (10.60 - 2.06) / (len(rows) + 1))
    sd.spec_table(s, 0.73, 1.66, hdr, rows,
                  col_w=(0.60, 5.60, 1.00, 1.00, 1.00, 1.00, 1.30, 1.40),
                  row_h=[0.40] + [row_h] * (len(rows)), zebra=True, size=11.5,
                  header_size=11.5)
    return s


# ================================================================ main

def main(path):
    prs = sd.new_deck("4:3")
    draw_overview(prs)
    for i, (bn, b, t) in enumerate(BANDS, start=1):
        draw_band_page(prs, f"1.{i}", bn, b, t)
    draw_mech_v31(prs)
    draw_mech_v32(prs)
    draw_detail_page(prs, "3.1", "BSND", BSND)
    draw_detail_page(prs, "3.2", "TND", TND)
    sd.save(prs, path)
    errors, warns = sd.check_layout(prs)
    cells = sd.check_cells(prs)
    print(f"wrote {path} ({len(prs.slides._sldIdLst)} 页)")
    print(f"版心检查: {len(errors)} 越界 / {len(warns)} 重叠 / {len(cells)} 格内问题")
    for e in errors[:8]:
        print("  !", e)
    for w in warns[:8]:
        print("  ~", w)
    for c in cells[:8]:
        print("  □", c)
    return len(errors)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/v3-perf-opt.pptx"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sys.exit(1 if main(out) else 0)
