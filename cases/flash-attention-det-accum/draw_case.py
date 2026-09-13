"""画出本案例的完整页面。

    python draw_case.py out/v4-index-schedules.pptx

页面顺序：0 总览 → 1 轴遍历顺序与 dS 分块 → 2..8 七种索引算法各两页。
术语约定：不适合直译的直接用英文原词（swizzle / layout / causal / mask / task id /
idle / fold / buffer / lane），解释句用中文。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)

import index_schedules as ix                                     # noqa: E402
import seeten_draw as sd                                         # noqa: E402

LANE_SET = "cool"
CELL_IN = 0.62
MATRIX_ROW_H = 0.48
LEFTX, COL_LIMIT = 2.10, 9.05
RIGHT_X = 11.30

AXIS_PANEL = ["B  = batch 序号", "N2 = KV head 序号", "G  = GQA 里第几个 Q head",
              "S1 = Q 方向第几块（每块 128 行）",
              "S2 = KV 方向第几块（每块 128 列）",
              "D  = head dim，tile 内不切分"]

# 每种规则的英文名 + 中文一句话 + 适用标签 + "为什么这样分"
META = {
    ix.KIND_DENSE_SWIZZLE: dict(
        en="Dense Swizzle", cn="列私有 swizzle",
        tags=lambda s, kw: [("layout", "TND" if "cu_q" in kw else "BSND"),
                            ("causal", "否"), ("头型", "MHA (g=1)"),
                            ("dk/dV", "列私有")],
        why=["task id 的低位是 S2 列，所以同一轮里相邻两条核落到相邻的两列上；",
             "一条核在 m 轮内 task id 不变 → 它一直守着同一列，只在列内把 S1 转一圈。",
             "同一个 S2 出现在多条核上时，那是不同 batch、不同轮。"]),
    ix.KIND_DENSE_INDEX: dict(
        en="Dense Index", cn="批优先旋转",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "否"),
                            ("头型", "MHA (g=1)"), ("dk/dV", "列私有"),
                            ("核数", "> S1 块数")],
        why=["低位换成了 batch：同一轮各核落在不同 batch、同一列上，S1 不会撞；",
             "所以核数可以超过 S1 块数 —— 代价是核不再独占整条列，改由切片保证有序。"]),
    ix.KIND_CAUSAL_SWIZZLE: dict(
        en="Causal Swizzle", cn="因果折叠",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "是，方形"),
                            ("头型", "MHA (g=1)"), ("buffer", "2 个 (parity)")],
        why=["fold 把两个相邻 batch 的三角拼成一个 m x (n+1) 的满矩形，task id 在矩形里按同样的低位规则排；",
             "奇数列用 parity-0 buffer、偶数列用 parity-1，所以一条核在两个 batch 之间交替。",
             "矩形是满的 → 没有 idle 槽位，也不需要在 epilogue 打 mask。"]),
    ix.KIND_LEFT_UP_CAUSAL: dict(
        en="Left-Up Causal", cn="左上对齐",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "是，S1 > S2"),
                            ("头型", "MHA (g=1)"), ("buffer", "2 个 (parity)")],
        why=["S1 比 S2 长时换一套几何：虚拟高 = 2m-n+1，每列只有 m 行有活；",
             "多出来的行是 idle，落在因果区外的块由 epilogue 的 mask 打掉（贡献精确 0）。"]),
    ix.KIND_GQA_DENSE: dict(
        en="GQA Dense", cn="任务切片",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "跟随 epilogue mask"),
                            ("头型", "GQA (g>1)"), ("dk/dV", "共享 workspace")],
        why=["GQA 里一个 KV head 对应 g 个 Q head，一条 KV 列会横跨多条核 → 没法列私有；",
             "改用连续 task id 切片分给各核，靠 gcd 修正让同一轮各核的 (B,N2,G,S1) 互不相同，",
             "跨核的 atomic add 因此有确定的先后。"]),
    ix.KIND_TND_DENSE: dict(
        en="TND Dense Swizzle", cn="逐批列私有",
        tags=lambda s, kw: [("layout", "TND (变长)"), ("causal", "否"),
                            ("头型", "MHA (g=1)"), ("dk/dV", "列私有")],
        why=["每个 batch 有自己的 round 前缀（长度可以不同），批内仍然按列私有排；",
             "核数超过本批的列数时，该轮这条核空转 —— 这是变长 batch 的代价。"]),
    ix.KIND_TND_GQA_DENSE: dict(
        en="TND GQA Dense", cn="按面积展平",
        tags=lambda s, kw: [("layout", "TND (变长)"), ("causal", "跟随 epilogue mask"),
                            ("头型", "GQA (g>1)"), ("dk/dV", "共享 workspace")],
        why=["按面积前缀把整个任务空间展平，再等分成 k 段，每条核顺序扫自己那段；",
             "不追求列私有，只保证同一轮各核的 (B,N2,G,S1) 互不相同。"]),
}


def page_text(kind, shape, mr, kw):
    m, n, b, g, k = shape.M(), shape.N(), shape.Bh(), shape.groupNum, shape.coreNum

    def rag():
        return ([kw["cu_q"][0]] + [kw["cu_q"][i] - kw["cu_q"][i - 1]
                                   for i in range(1, shape.batch)],
                [kw["cu_k"][0]] + [kw["cu_k"][i] - kw["cu_k"][i - 1]
                                   for i in range(1, shape.batch)])

    if kind == ix.KIND_DENSE_SWIZZLE:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b}",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                    "对每个 (round r, core j):",
                    "    task id = ((r-1) / m) * k + (j-1)   # 每个 m 轮跨度内不变",
                    "    第几列 = task id % n + 1             # 低位先走 S2 列",
                    "    第几批 = task id / n + 1             # 列走完才换 batch",
                    "    第几行 = (第几列-1 + r-1) % m + 1    # 列内 S1 每轮转一格",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="一条核在 m 轮里始终守着同一条 S2 列，只把 S1 转一圈 —— dK/dV 因此是单核顺序累加。",
            ex_sub="把任务矩阵摊到 S1×S2 平面上：纵轴 S1、横轴 S2，颜色是核，格内是第几轮",
            read=["同一列颜色相同 = 列私有；同一条核的任务用同色相的深浅区分轮次。",
                  "两条核各包 3 条列，9 轮正好把 18 个块铺满。"])
    if kind == ix.KIND_DENSE_INDEX:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b}（core 数 > S1 块数）",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                    "对每个 (round r, core j):",
                    "    task id = ((r-1) / m) * k + j        # 1 起算",
                    "    第几批 = task id % b，得 0 时取 b     # 低位先走 B（与上一页相反）",
                    "    第几列 = ceil(task id / b)",
                    "    第几行 = ((第几列 % m) + (r % m) - 1) % m",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="低位改成 batch 后，同一轮里各核落在不同 batch 上，S1 撞不到一起 —— 所以核数可以超过 S1 块数。",
            ex_sub="同一个块集（2 batch x 2x2 块）换成本页规则，只用 2 轮就铺满",
            read=[f"{k} 条核各守一条列，每列恰好 2 个块。",
                  "对比上一页：core 数 4 > S1 块数 2，列优先的规则在这里不能用。"])
    if kind == ix.KIND_CAUSAL_SWIZZLE:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b} · causal，S1 = S2",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                    "第 1 步：把相邻两个 batch 折成一个虚拟矩形",
                    f"    虚拟宽 = n+1 = {n + 1} 列,  虚拟高 = m = {m} 行,  虚拟 batch 数 = b/2",
                    "第 2 步：在虚拟矩形里按“列私有”规则取 task（同 Dense Swizzle）",
                    "第 3 步：把虚拟坐标折回真实坐标",
                    "    如果 虚拟行 >= 虚拟列+1:  # 右上三角",
                    "        batch = 2*虚拟批; 行 = m+1-虚拟行; 列 = 2n-m-虚拟列+2",
                    "    否则: batch = 2*虚拟批-1   # 左下三角，行列照抄"],
            key="两个三角正好拼成一个 m 行 n+1 列的满矩形：没有 idle 槽位、也不用打 mask。",
            ex_sub="先看下面的虚拟矩形（两个三角拼成的满矩形），再对照上面两张真实的块图",
            read=["同一个格子在两张真实图上各出现一次，颜色深浅说明同一条核的轮次推进。",
                  "一条核在两个 batch 之间来回切，所以每核要两个累加 buffer（parity 0/1）。"])
    if kind == ix.KIND_LEFT_UP_CAUSAL:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b} · causal，S1 > S2",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                    "如果 m <= n:  直接套用 Causal Swizzle",
                    "否则 (S1 更长):",
                    f"    虚拟高 = 2m-n+1 = {2 * m - n + 1}",
                    "    列号  = (r-1)/虚拟高 * active core 数 + (j-1)",
                    "    配对号 = 列号/n+1;  虚拟列 = 列号%n+1;  虚拟行 = (r-1)%虚拟高+1",
                    "    奇数 batch 可用行数 = m - 虚拟列 + 1",
                    "    如果 虚拟行 <= 可用行数: 奇数 batch, 行 = 虚拟列+虚拟行-1, 列 = 虚拟列",
                    "    否则:                  偶数 batch, 行 = m-(虚拟行-可用行数)+1, 列 = n-虚拟列+1"],
            key="虚拟矩形比真实 causal 区大：多出来的轮次是 idle，靠 mask 打掉。",
            ex_sub=f"虚拟高 {2 * m - n + 1} 行里，每列只有 {m} 行有活；灰格是凑不满的部分",
            read=["红色格 = 本轮该核没任务（idle）；灰格 = 落在 causal 区外、要靠 mask 的块。",
                  "注：选择器目前只在 S1 与 S2 等长时选 Left-Up，那时它会委托给 Causal Swizzle。"])
    if kind == ix.KIND_GQA_DENSE:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b} · GQA g={g}",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}, g={g}",
                    f"每条核要跑几轮: R = max(ceil(b*n*g/k), ceil(n/m), g) = {mr // m}",
                    "对每个 (round r, core j):",
                    "    task id = (j-1)*R + ceil(r/m)     # core j 独占 R 个连续 task id",
                    "    批 = ceil( (task id % (b*g) 或取满) / g )",
                    "    第几列 = ceil(task id / (b*g))",
                    "    第几组 = task id % g，得 0 时取 g",
                    "    起点偏移 = ceil( (第几列 % (t1*m) 或取满) / t1 ),  t1 = R/gcd(b*g, R)",
                    "    第几行 = (轮内序号 + 起点偏移 - 1) % m"],
            key="一条 KV 列横跨多条核，没法列私有 —— 改用共享 workspace 的轮序 atomic add，"
                "确定性靠“同轮各核的 (B,N2,G,S1) 互不相同”。",
            ex_sub="同一个 (S1,S2) 格上叠着两个 G 的任务，所以按 G 拆成两张图",
            read=["颜色色相 = 哪条核，深浅 = 第几轮；两张图合起来看，8 个任务各归各的核。",
                  "G1 和 G2 交替落位，避免同轮抢同一个 S1。"])
    if kind == ix.KIND_TND_DENSE:
        q, kk = rag()
        return dict(
            sub=("输入：core 数 " + str(k) + " · 各 batch 的 S1 块数 "
                 + str([(x + 127) // 128 for x in q]) + " · S2 块数 "
                 + str([(x + 127) // 128 for x in kk]) + "（长度不等）"),
            pseudo=[f"core 数 k={k}, batch 数 b={shape.batch}, 各 batch 长度不同",
                    "先算每个 batch 要跑几轮，存成前缀表（轮数可以逐 batch 不同）:",
                    "    每 batch 轮数 = ceil(该 batch 列数 * head 数 / k) * 该 batch S1 块数",
                    f"    例子: batch1 要 {kw['prefix'][1] - kw['prefix'][0]} 轮, "
                    f"batch2 要 {kw['prefix'][2] - kw['prefix'][1]} 轮 → 前缀 {kw['prefix']}",
                    "对每个 (round r, core j):",
                    "    在轮前缀表里查 r 落到哪个 batch, 批内轮号 = r - 该 batch 前缀",
                    "    task id = (批内轮号 / 该 batch S1 块数) * k + (j-1)",
                    "    第几列 = task id % 该 batch S2 块数",
                    "    第几行 = (第几列 + 批内轮号) % 该 batch S1 块数",
                    "    task id 超出该 batch 列数 → 本核本轮 idle"],
            key="每个 batch 按自己的长度排轮次，短 batch 不拖累长 batch；核数超过本 batch 列数时会有 idle。",
            ex_sub="两个 batch 的网格大小不同：batch1 是 3x2 块，batch2 是 2x3 块",
            read=["灰格 = 本轮该核没有可派的列（batch1 只有 2 列，第 4 轮只剩一条核有活）。",
                  "对比算法页的对照表：按最长 batch 对齐要多花好几轮。"])
    if kind == ix.KIND_TND_GQA_DENSE:
        q, kk = rag()
        return dict(
            sub=("输入：core 数 " + str(k) + " · 各 batch 的 S1 块数 "
                 + str([(x + 127) // 128 for x in q]) + " · S2 块数 "
                 + str([(x + 127) // 128 for x in kk]) + f" · GQA g={g}"),
            pseudo=[f"core 数 k={k}, batch 数 b={shape.batch}, g={g}, 各 batch 长度不同",
                    "先算每 batch 的任务面积并累加:",
                    "    面积 = 该 batch S1 块数 * S2 块数;  面积前缀 = 逐 batch 累加",
                    f"    例子: 面积前缀 {kw['area_prefix']}",
                    f"总轮数 = max(ceil(总面积*head数*g/k), 最大S1块数*g, 最大S2块数) = {mr}",
                    "对每个 (round r, core j):",
                    "    全局 task id = (j-1) * 总轮数 + r     # 每条核独占一段，顺序扫",
                    "    用面积前缀查出它属于哪个 batch;  批内号 = 全局 task id - 该 batch 面积前缀*head数",
                    "    第几组 = 批内号 换算;  第几行 = 批内号 % m;  第几列 = ceil(批内号 / (m*g))"],
            key="变长 GQA 无法逐 batch 对齐，直接把整个任务空间展平等分给各核，顺序扫过。",
            ex_sub="面积大的 batch 分到的格子多；每个 (S1,S2) 格上有两个 G 的任务，按 G 拆图",
            read=["四个小块合起来 = 12 个任务，正好被 2 条核 x 6 轮扫完，零 idle。",
                  "batch2 只有 1x2 块，所以它那两张图更矮。"])
    raise KeyError(kind)


# ---------------------------------------------------------------- 辅助表

def numbers_rows(kind, shape, mr, kw):
    r = ix.check(kind, shape, mr, **kw)
    rows = [("任务总数", r["valid"]), ("总槽位（core x round）", r["slots"]),
            ("idle 槽位", r["holes"])]
    if shape.groupNum == 1:
        cols = sum(len(v) for v in r["cols_per_lane"].values())
        rows.append(("每核独占的列数", cols // max(1, shape.coreNum)))
    return rows


def lane_column_rows(kind, shape, mr, kw):
    r = ix.check(kind, shape, mr, **kw)
    rows = []
    for j in sorted(r["cols_per_lane"]):
        cols = r["cols_per_lane"][j]
        txt = "  ".join(f"B={a} S2={c}" for a, c in cols) if cols else "（无）"
        rows.append((f"C{j}", txt))
    return ("core", "负责的 (B, S2) 列（按先后顺序）"), rows


def applicability_rows(kind, shape, mr):
    m, n, b, g, k = shape.M(), shape.N(), shape.Bh(), shape.groupNum, shape.coreNum
    causal = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    cands = [
        (ix.KIND_DENSE_SWIZZLE, "Dense Swizzle",
         (not causal) and g == 1 and k <= m, f"core 数 {k} ≤ S1 块数 {m}"),
        (ix.KIND_DENSE_INDEX, "Dense Index",
         (not causal) and g == 1 and k > m, f"core 数 {k} > S1 块数 {m} 时才需要"),
        (ix.KIND_CAUSAL_SWIZZLE, "Causal Swizzle", causal, "causal 形状才用"),
        (ix.KIND_LEFT_UP_CAUSAL, "Left-Up Causal",
         causal and b % 2 == 0 and m == n, f"batch {b} 为偶且 S1 与 S2 等长"),
        (ix.KIND_GQA_DENSE, "GQA Dense", g > 1, f"g={g} > 1 才用"),
    ]
    rows = []
    for kk, cn, fits, why in cands:
        rows.append((cn, "★ 本页用它" if kk == kind else ("也能用" if fits else "用不上"),
                     why))
    return ("规则", "本形状下", "条件"), rows


def tnd_compare_rows(shape, mr, kw):
    q, kk = [], []
    for b in range(shape.batch):
        q.append(kw["cu_q"][b] - (0 if b == 0 else kw["cu_q"][b - 1]))
        kk.append(kw["cu_k"][b] - (0 if b == 0 else kw["cu_k"][b - 1]))
    s1max = max((x + 127) // 128 for x in q)
    s2max = max((x + 127) // 128 for x in kk)
    n1 = shape.kvHeadNum * shape.groupNum
    padded = shape.batch * max(1, -(-n1 * s2max // shape.coreNum)) * s1max
    return ("做法", "总轮数", "说明"), [
        ("本页规则（逐 batch）", mr, "每 batch 按自己的长度排，短 batch 不拖累长 batch"),
        ("按最长 batch 对齐（示意）", padded, "所有 batch 按最长的排，短 batch 大量空转")]


# ---------------------------------------------------------------- 页面构件

def grid_cells(ts, batch, head=None):
    out = {}
    for (j, r), c in ts.items():
        if c is None or c.batch != batch:
            continue
        if head is not None and (c.n2, c.g) != head:
            continue
        out[(c.s1, c.s2)] = (f"第{r}轮", j - 1, r - 1)      # 第三项 = 深浅序号
    return out


def virtual_cells(kind, shape, mr, kw):
    m, n = shape.M(), shape.N()
    cells = {}
    for j in range(1, shape.coreNum + 1):
        for r in range(1, mr + 1):
            if ix.decode(kind, shape, r, j, **kw) is None:
                continue
            if kind == ix.KIND_CAUSAL_SWIZZLE:
                n_new = n + 1 if m == n else (n - m + 2) + (n + 1)
                v = ix.Raw()
                ix.cal_dense_swizzle_index(shape.coreNum, m, n_new, shape.Bh() >> 1,
                                           j, r, v)
                if v.w:
                    cells[(v.s1 - 1, v.s2 - 1)] = (f"C{j} 第{r}轮", j - 1, r - 1)
            else:
                virtual_m = 2 * m - n + 1
                active_k = min(shape.coreNum, n * (shape.Bh() >> 1))
                if j > active_k:
                    continue
                column_id = (r - 1) // virtual_m * active_k + j - 1
                if column_id >= n * (shape.Bh() >> 1):
                    continue
                vs1 = (r - 1) % virtual_m + 1
                vs2 = column_id % n + 1
                cells[(vs1 - 1, vs2 - 1)] = (f"C{j} 第{r}轮", j - 1, r - 1)
    return cells


def batch_mn(shape, kw, b):
    if "cu_q" in kw:
        lens = kw["cu_q"][b] - (0 if b == 0 else kw["cu_q"][b - 1])
        klen = kw["cu_k"][b] - (0 if b == 0 else kw["cu_k"][b - 1])
        return (lens + 127) // 128, (klen + 127) // 128
    return shape.M(), shape.N()


def legend_row(slide, x, y, shape, mr, lane_set=LANE_SET, cell=0.72):
    """图例（两行，控制在左栏内）：色相 = core，深浅 = 轮次。"""
    sd.text(slide, x, y, "色相 = core", w=1.5, h=0.30, size=14, bold=True)
    cx = x + 1.15
    colors = sd.lane_colors(lane_set, shape.coreNum)
    for i in range(shape.coreNum):
        sd.block_grid(slide, cx + i * cell, y - 0.05, [[colors[i]["fill"]]],
                      [[f"C{i + 1}"]], cell_w=cell * 914400, cell_h=0.40 * 914400,
                      label_size=13.0)
    sd.text(slide, cx + shape.coreNum * cell + 0.25, y, "深浅 = 轮次", w=1.9, h=0.30,
            size=14, color=sd.BODY_TEXT)
    y2 = y + 0.46
    sd.text(slide, x, y2, "第几轮：", w=1.0, h=0.28, size=12.5, color=sd.BODY_TEXT)
    shades = sd.lane_shades(lane_set, 0, mr)
    for i, sh in enumerate(shades[:8]):
        sd.block_grid(slide, x + 0.95 + i * 0.40, y2 - 0.04, [[sh["fill"]]], [[""]],
                      cell_w=0.36 * 914400, cell_h=0.34 * 914400, label_size=9.0)
    sd.text(slide, x + 0.95 + min(8, mr) * 0.40 + 0.14, y2,
            f"越深越靠前，共 {mr} 轮", w=2.6, h=0.28, size=12.5, color=sd.BODY_TEXT)


def _virtual_grid(slide, x, y, n_cols, n_rows, cells, lane_set=LANE_SET,
                  cell_w=1.05, cell_h=0.62, shade_count=None):
    tbl = sd._plain_table(slide, x, y, n_rows + 1, n_cols + 1,
                          cell_w=int(cell_w * 914400), cell_h=int(cell_h * 914400))
    for i in range(n_cols + 1):
        tbl.columns[i].width = sd.Inches(cell_w)
    for i in range(n_rows + 1):
        tbl.rows[i].height = sd.Inches(cell_h)
    colors = sd.lane_colors(lane_set, 8)
    shades = ([sd.lane_shades(lane_set, i, shade_count) for i in range(8)]
              if shade_count else None)
    hole = sd.hole_color()
    for c in range(n_cols + 1):
        cell = tbl.cell(0, c)
        sd._cell_border(cell)
        if c:
            sd._fill_cell(cell, sd.ON_BLOCK)
            sd._write_cell_lines(cell, [f"虚拟列{c}"], size=11.0, colors=[sd.TITLE_TEXT])
    for r in range(1, n_rows + 1):
        cell = tbl.cell(r, 0)
        sd._cell_border(cell)
        sd._fill_cell(cell, sd.ON_BLOCK)
        sd._write_cell_lines(cell, [f"虚拟行{r}"], size=11.0, colors=[sd.TITLE_TEXT])
        for c in range(1, n_cols + 1):
            cell = tbl.cell(r, c)
            sd._cell_border(cell)
            got = cells.get((r - 1, c - 1))
            if got is None:
                sd._fill_cell(cell, hole["fill"])
                sd._write_cell_lines(cell, ["用不到"], size=10.5, colors=[hole["text"]])
            else:
                label, lane = got[0], got[1]
                shade = got[2] if len(got) > 2 else 0
                col = (shades[lane % 8][shade % shade_count] if shades
                       else colors[lane % 8])
                sd._fill_cell(cell, col["fill"])
                sd._write_cell_lines(cell, label.split(), size=11.0,
                                     colors=[col["text"]] * len(label.split()))
    sd.text(slide, x + 0.04, y - 0.40, "fold 后的虚拟矩形（行 = 虚拟 S1，列 = 虚拟 S2）",
            w=(n_cols + 1) * cell_w, h=0.30, size=14.0, bold=True)
    sd.arrow(slide, x + 0.10, y - 0.08, x + 0.10, y, width_pt=0.75, color=sd.BORDER)
    return y + (n_rows + 1) * cell_h


# ---------------------------------------------------------------- 页面

def draw_overview(prs):
    s = sd.blank_slide(prs)
    sd.title(s, "0. 总览：7 种任务索引", y=0.62)
    sd.text(s, 0.73, 1.22,
            "同一个问题：给定 (round, core)，这一轮这条 core 该算哪一块？七种规则给出七种分派方式。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    rows = []
    for i, (name, kind, shape, mr, kw, causal) in enumerate(ix.cases(), start=1):
        m = META[kind]
        rows.append((f"{i}. {m['en']}",
                     "TND" if "cu_q" in kw else "BSND",
                     "是" if causal else "否",
                     "GQA" if shape.groupNum > 1 else "MHA",
                     "是" if shape.groupNum == 1 else "否",
                     str(mr)))
    sd.spec_table(s, 0.73, 1.72,
                  ("规则", "layout", "causal", "头型", "列私有", "总轮数"), rows,
                  col_w=(4.00, 1.60, 1.40, 1.40, 1.40, 1.40),
                  row_h=(0.55,) + (0.58,) * 7)
    sd.note(s, 0.73, 6.90, "所有规则都是纯算术：(round, core) 一确定，结果就唯一 —— 这就是确定性的来源。",
            w=15.2, h=0.36)
    sd.text(s, 0.73, 7.65, "怎么读后面的例子", w=13.0, h=0.34, size=18, bold=True)
    for i, line in enumerate([
            "· 先看第 1 页：所有规则共用同一个轴遍历顺序 b → n2 → s2 → s1 → d。",
            "· 算法页：伪代码讲逻辑 → 任务矩阵（行 = round，列 = core）→ 为什么这样分。",
            "· 例子页：网格纵轴 S1、横轴 S2；色相 = core，深浅 = 轮次，灰格 = idle。"]):
        sd.text(s, 0.73, 8.15 + i * 0.42, line, w=13.0, h=0.36, size=16,
                color=sd.BODY_TEXT)
    sd.panel(s, 11.30, 7.65, "格子里写什么", ("记号", "含义"),
             [("B", "batch"), ("N2", "KV head"), ("G", "GQA 里的 Q head"),
              ("S1", "Q 方向第几块（128 行）"), ("S2", "KV 方向第几块（128 列）"),
              ("D", "head dim，tile 内不切分")], col_w=(1.10, 3.55), row_h=0.42,
             size=13.0)
    return s


def draw_axis_page(prs):
    """轴遍历顺序 + dS 分块：解释"为什么这样划分"。"""
    s = sd.blank_slide(prs)
    sd.title(s, "1. 轴遍历顺序与 dS 分块", y=0.62)
    sd.text(s, 0.73, 1.22,
            "七种规则共用同一个铺 task id 的顺序：外层慢、内层快。先认这个顺序，后面的分派才看得懂。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    # 轴链：b -> n2 -> s2 -> s1 -> d
    chain = [("b", "最外层：一个 batch 的活排完再换下一个"),
             ("n2", "KV head"),
             ("s2", "一条 KV 列 —— “列私有”就是在这个粒度上"),
             ("s1", "列内旋转的粒度"),
             ("d", "head dim：tile 内最内层，不参与调度")]
    cx, cy = 0.90, 1.72
    for i, (ax, note) in enumerate(chain):
        w = 0.62
        sd.block_grid(s, cx, cy - 0.02, [[sd.GROUP0 if i < 3 else sd.GROUP1]],
                      [[ax]], cell_w=w * 914400, cell_h=0.46 * 914400, label_size=16.0)
        sd.text(s, cx - 0.14, cy + 0.50, note, w=1.10, h=0.62, size=11.5,
                color=sd.BODY_TEXT, wrap=True)
        if i < len(chain) - 1:
            sd.arrow(s, cx + w + 0.06, cy + 0.21, cx + w + 0.60, cy + 0.21)
        cx += w + 0.68

    # dS 分块：先走完一列（S1 快），再换下一列（S2 慢）
    m, n = 3, 3
    sd.text(s, 0.90, 3.05, "dS 的分块顺序：先沿 S1 走完一列，再换下一列（S2）",
            w=9.0, h=0.30, size=15, bold=True)
    shades = sd.lane_shades("mist", 0, m * n)
    fills, labels = [], []
    for r in range(m):
        row_f, row_l = [], []
        for c in range(n):
            row_f.append(shades[c * m + r]["fill"])
            row_l.append(str(c * m + r + 1))
        fills.append(row_f)
        labels.append(row_l)
    sd.panel(s, 4.30, 3.74, "task id 展开（前 8 个）",
             ("task id", "B", "N2", "S2", "S1"),
             [(str(t), "1", "1", str((t - 1) // m + 1), str((t - 1) % m + 1))
              for t in range(1, 9)],
             col_w=(1.10, 0.80, 0.90, 0.90, 0.90), row_h=0.40, size=12.5)
    sd.text(s, 1.60, 3.42, "S2 →", w=1.2, h=0.26, size=13, color=sd.BODY_TEXT)
    sd.block_grid(s, 1.60, 3.74, fills, labels, cell_w=0.80 * 914400,
                  cell_h=0.62 * 914400, label_size=15.0)
    sd.axis_arrow(s, 1.22, 3.74, (m + 1) * 0.62 - 0.40, "down", "S1", label_off=0.10)
    sd.text(s, 1.60, 5.72, "一列 = 一条 KV 列，走完再换下一列", w=3.6, h=0.28, size=12,
            color=sd.BODY_TEXT)

    # 右侧：这套顺序解释了什么
    sd.text(s, 10.60, 1.85, "为什么这样排", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate([
            "· task id 低位走内层轴 → 同一轮里各 core 拿到",
            "  连续的 task id，落在相邻的 S2 列（或相邻 batch）上。",
            "· 一条 core 在 m 轮里 task id 不变 → 它守着同一条列，",
            "  只在列内把 S1 转一圈，这才是“单核顺序累加”。",
            "· 所以同一个 S2 会出现在多条 core 的任务里 —— 那是",
            "  不同轮次、不同 batch；而在同一条 core 内部它始终",
            "  是同一列连续多轮。"]):
        sd.text(s, 10.60, 2.25 + i * 0.33, line, w=5.30, h=0.30, size=13.5,
                color=sd.BODY_TEXT)
    sd.panel(s, 10.60, 4.80, "五个轴各自是什么", ("轴", "含义"),
             [("b", "batch"), ("n2", "KV head"),
              ("s2", "KV 方向第几块（128 列）"), ("s1", "Q 方向第几块（128 行）"),
              ("d", "head dim，tile 内最内层")], col_w=(0.80, 3.85), row_h=0.42,
             size=12.5)
    sd.note(s, 0.73, 10.15,
            "后面每种规则，只是把“低位先走哪个轴”换一下；换法不同，就得到不同的分派与不同的 idle 分布。",
            w=15.2, h=0.52)
    sd.text(s, 0.73, 10.85, "· 数字 = task id 顺序；颜色越深 = 越早执行。",
            w=15.2, h=0.36, size=16, color=sd.BODY_TEXT)
    return s


def draw_algo_page(prs, num, name, kind, shape, mr, kw, causal):
    meta = META[kind]
    txt = page_text(kind, shape, mr, kw)
    s = sd.blank_slide(prs)
    sd.title(s, f"{num}. {meta['en']}：{meta['cn']}", y=0.62)
    sd.text(s, 0.73, 1.22, txt["sub"], w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    sd.tag_row(s, 0.73, 1.58, meta["tags"](shape, kw))

    blk = sd.pseudocode_block(s, 0.73, 2.02, 9.6, txt["pseudo"])
    ty = 2.02 + sd.est_box(blk)[3] + 0.30

    ts = ix.tasks_of(kind, shape, mr, **kw)
    rows = []
    for r in range(1, mr + 1):
        cs = []
        for j in range(1, shape.coreNum + 1):
            c = ts.get((j, r))
            if c is None:
                cs.append(None)
                continue
            lines = [f"S1={c.s1 + 1}  S2={c.s2 + 1}"]
            if shape.groupNum > 1 or shape.kvHeadNum > 1:
                lines.append(f"B={c.batch + 1} N2={c.n2 + 1} G={c.g + 1}")
            elif shape.batch > 1:
                lines.append(f"B={c.batch + 1}")
            cs.append({"lines": lines, "lane": j - 1, "shade": r - 1})
        rows.append((f"第 {r} 轮", cs))
    col_w = min(4.4, (9.95 - 0.73 - 1.05) / max(1, shape.coreNum))
    sd.task_matrix(s, 0.73, ty, [f"C{j}" for j in range(1, shape.coreNum + 1)], rows,
                   col_w=col_w, row_h=MATRIX_ROW_H, lane_set=LANE_SET,
                   shade_count=mr)
    bottom = ty + (mr + 1) * MATRIX_ROW_H

    # 「为什么这样分」——直接放在矩阵下面，回答"为什么这么划"
    sd.text(s, 0.73, bottom + 0.28, "为什么这样分", w=4.0, h=0.30, size=15, bold=True)
    for i, line in enumerate(meta["why"]):
        sd.text(s, 0.73, bottom + 0.62 + i * 0.30, line, w=9.60, h=0.28, size=13.0,
                color=sd.BODY_TEXT)

    # 右栏
    yy = 2.02
    sd.text(s, RIGHT_X, yy, "格子里写什么", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate(AXIS_PANEL):
        sd.text(s, RIGHT_X, yy + 0.36 + i * 0.28, line, w=4.7, h=0.26, size=13,
                color=sd.BODY_TEXT)
    yy = yy + 0.36 + len(AXIS_PANEL) * 0.28 + 0.30
    yy = sd.panel(s, RIGHT_X, yy, "这个例子的数字", ("项", "值"),
                  numbers_rows(kind, shape, mr, kw), col_w=(3.20, 1.45), row_h=0.44,
                  size=13.0) + 0.30
    if "cu_q" in kw and shape.groupNum > 1:
        sd.panel(s, RIGHT_X, yy, "换成按最长 batch 对齐（示意）",
                 *tnd_compare_rows(shape, mr, kw), col_w=(1.60, 0.95, 2.10),
                 row_h=0.46, size=12.0)
    else:
        sd.panel(s, RIGHT_X, yy, "同一形状下其它规则能不能用",
                 *applicability_rows(kind, shape, mr), col_w=(1.40, 0.95, 2.30),
                 row_h=0.46, size=12.0)
    sd.note(s, 0.73, 11.15, txt["key"], w=15.2, h=0.52)
    return s


def draw_example_page(prs, num, name, kind, shape, mr, kw, causal):
    meta = META[kind]
    txt = page_text(kind, shape, mr, kw)
    s = sd.blank_slide(prs)
    sd.title(s, f"{num}. {meta['en']} —— 例子", y=0.62)
    sd.text(s, 0.73, 1.22, txt["ex_sub"], w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    ts = ix.tasks_of(kind, shape, mr, **kw)
    n_max = max(batch_mn(shape, kw, b)[1] for b in range(shape.batch))
    cell = max(CELL_IN, min(0.95, 2.80 / (n_max + 1)))

    gx, gy, first, row_h = LEFTX, 2.60, True, 0.0
    for b in range(shape.batch):
        m, n = batch_mn(shape, kw, b)
        heads = sorted({(c.n2, c.g) for (_, _), c in ts.items()
                        if c is not None and c.batch == b})
        for head in heads:
            gw = (n + 1) * cell
            if gx > LEFTX and gx + gw > COL_LIMIT:
                gx, gy, row_h = LEFTX, gy + row_h + 1.15, 0.0
            tag = "" if len(heads) == 1 and shape.groupNum == 1 else \
                  f" N2={head[0] + 1} G={head[1] + 1}"
            sd.axis_grid(s, gx, gy, m, n, grid_cells(ts, b, head), f"B={b + 1}{tag}",
                         lane_set=LANE_SET, cell_in=cell, shade_count=mr)
            if first:
                sd.axis_arrow(s, gx - 0.68, gy, (m + 1) * cell - cell * 0.6, "down", "S1")
                sd.axis_arrow(s, gx, gy - 0.72, (n + 1) * cell - cell * 0.6, "right", "S2")
                first = False
            row_h = max(row_h, (m + 1) * cell)
            gx += gw + 1.35
    left_bottom = gy + row_h

    # 图例紧跟网格，并且要把它的高度算进左栏占用（否则下面的表会压上来）
    legend_row(s, LEFTX, left_bottom + 0.12, shape, mr)
    left_bottom += 0.86

    causal_kind = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    m0, n0 = shape.M(), shape.N()
    v_cols = n0 if m0 > n0 else n0 + 1
    v_rows = (2 * m0 - n0 + 1) if m0 > n0 else m0
    wide = (v_cols + 1) * 1.05 > 4.70
    v_cells = virtual_cells(kind, shape, mr, kw) if causal_kind else None

    if causal_kind and wide:
        left_bottom = _virtual_grid(s, LEFTX, left_bottom + 0.55, v_cols, v_rows,
                                    v_cells, lane_set=LANE_SET, shade_count=mr) + 0.35

    r = ix.check(kind, shape, mr, **kw)
    priv = ("— 不适用" if shape.groupNum > 1
            else ("✓ 整列只归一条 core" if r["column_private"] else "✗ 有重复"))
    props = ("这个例子为什么是确定的", ("性质", "本例情形"),
             [("任务不重复", "✓ 每个块只被派一次" if not r["dup"] else "✗ 有重复"),
              ("同一轮 S1 不撞", "✓ 各核的 S1 互不相同" if not r["dq_conflict"]
               else "✗ 有冲突"),
              ("每条 core 列私有", priv)])

    ry = 2.60
    if causal_kind and not wide:
        ry = _virtual_grid(s, 10.60, ry, v_cols, v_rows, v_cells,
                           lane_set=LANE_SET, shade_count=mr) + 0.45
    ry = sd.panel(s, 10.60, ry, "每条 core 负责哪些列",
                  *lane_column_rows(kind, shape, mr, kw),
                  col_w=(0.95, 4.30), row_h=0.44, size=12.5) + 0.45
    ry = sd.panel(s, 10.60, ry, "这个例子的数字", ("项", "值"),
                  numbers_rows(kind, shape, mr, kw), col_w=(3.20, 1.45), row_h=0.44,
                  size=13.0) + 0.45
    props_h = 0.36 + 4 * 0.44
    if (not (causal_kind and wide)) and left_bottom + props_h <= 10.05:
        sd.panel(s, LEFTX, left_bottom, *props, col_w=(2.20, 2.45), row_h=0.44,
                 size=12.0)
    elif ry + props_h <= 11.85:
        sd.panel(s, 10.60, ry, *props, col_w=(2.20, 2.45), row_h=0.44, size=12.0)

    sd.note(s, 0.73, 10.10, txt["key"], w=9.70, h=0.52)
    for i, line in enumerate(txt["read"]):
        sd.text(s, 0.73, 11.00 + i * 0.42, "· " + line, w=9.70, h=0.36, size=16,
                color=sd.BODY_TEXT)
    return s


def main(path):
    prs = sd.new_deck("4:3")
    draw_overview(prs)
    draw_axis_page(prs)
    for i, (name, kind, shape, mr, kw, causal) in enumerate(ix.cases(), start=2):
        draw_algo_page(prs, i, name, kind, shape, mr, kw, causal)
        draw_example_page(prs, i, name, kind, shape, mr, kw, causal)
    sd.save(prs, path)
    errors, warns = sd.check_layout(prs)
    print(f"wrote {path}  ({len(prs.slides._sldIdLst)} 页)")
    print(f"版心检查: {len(errors)} 越界 / {len(warns)} 重叠")
    for e in errors[:10]:
        print("  !", e)
    for w in warns[:10]:
        print("  ~", w)
    return len(errors)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/v4-index-schedules.pptx"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sys.exit(1 if main(out) else 0)
