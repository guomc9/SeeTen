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
MATRIX_ROW_H = 0.50        # 格内两行（S1/S2 + B/N2/G），再矮就贴边了
LEFTX, COL_LIMIT = 2.10, 9.05
RIGHT_X = 11.30

AXIS_PANEL = ["B  = batch 序号", "N2 = KV head 序号", "G  = GQA 里第几个 Q head",
              "S1 = Q 方向第几块（每块 128 行）",
              "S2 = KV 方向第几块（每块 128 列）",
              "D  = head dim，tile 内不切分"]

# 每种规则的英文名 + 中文一句话 + 适用标签 + "为什么这样分"
META = {
    ix.KIND_DENSE_SWIZZLE: dict(
        en="Dense Swizzle", cn="列私有 swizzle", low=lambda s, kw: "S2 列",
        tags=lambda s, kw: [("layout", "TND" if "cu_q" in kw else "BSND"),
                            ("causal", "否"), ("头型", "MHA (g=1)"),
                            ("dk/dV", "列私有")],
        why=["task id 的低位是 S2 列，所以同一轮里相邻两条核落到相邻的两列上；",
             "一条核在 m 轮内 task id 不变 → 它一直守着同一列，只在列内把 S1 转一圈。",
             "同一个 S2 出现在多条核上时，那是不同 batch、不同轮。"]),
    ix.KIND_DENSE_INDEX: dict(
        en="Dense Index", cn="批优先旋转", low=lambda s, kw: "B 批次",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "否"),
                            ("头型", "MHA (g=1)"), ("dk/dV", "列私有"),
                            ("核数", "> S1 块数")],
        why=["低位换成了 batch：同一轮各核落在不同 batch、同一列上，S1 不会撞；",
             "所以核数可以超过 S1 块数 —— 代价是核不再独占整条列，改由切片保证有序。"]),
    ix.KIND_CAUSAL_SWIZZLE: dict(
        en="Causal Swizzle", cn="因果折叠", low=lambda s, kw: "S2（fold 后）",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "是，方形"),
                            ("头型", "MHA (g=1)"), ("buffer", "2 个 (parity)")],
        why=["fold 把两个相邻 batch 的三角拼成一个 m x (n+1) 的满矩形，task id 在矩形里按同样的低位规则排；",
             "奇数列用 parity-0 buffer、偶数列用 parity-1，所以一条核在两个 batch 之间交替。",
             "矩形是满的 → 没有 idle 槽位，也不需要在 epilogue 打 mask。"]),
    ix.KIND_LEFT_UP_CAUSAL: dict(
        en="Left-Up Causal", cn="左上对齐", low=lambda s, kw: "S2（虚拟）",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "是，S1 > S2"),
                            ("头型", "MHA (g=1)"), ("buffer", "2 个 (parity)")],
        why=["S1 比 S2 长时换一套几何：虚拟高 = 2m-n+1，每列只有 m 行有活；",
             "多出来的行是 idle，落在因果区外的块由 epilogue 的 mask 打掉（贡献精确 0）。"]),
    ix.KIND_GQA_DENSE: dict(
        en="GQA Dense", cn="任务切片", low=lambda s, kw: "S2（切片）",
        tags=lambda s, kw: [("layout", "BSND"), ("causal", "跟随 epilogue mask"),
                            ("头型", "GQA (g>1)"), ("dk/dV", "共享 workspace")],
        why=["GQA 里一个 KV head 对应 g 个 Q head，一条 KV 列会横跨多条核 → 没法列私有；",
             "改用连续 task id 切片分给各核，靠 gcd 修正让同一轮各核的 (B,N2,G,S1) 互不相同，",
             "跨核的 atomic add 因此有确定的先后。"]),
    ix.KIND_TND_DENSE: dict(
        en="TND Dense Swizzle", cn="逐批列私有", low=lambda s, kw: "本批 S2 列",
        tags=lambda s, kw: [("layout", "TND (变长)"), ("causal", "否"),
                            ("头型", "MHA (g=1)"), ("dk/dV", "列私有")],
        why=["每个 batch 有自己的 round 前缀（长度可以不同），批内仍然按列私有排；",
             "核数超过本批的列数时，该轮这条核空转 —— 这是变长 batch 的代价。"]),
    ix.KIND_TND_GQA_DENSE: dict(
        en="TND GQA Dense", cn="按面积展平", low=lambda s, kw: "展平索引",
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
            key="一条核在 m 轮里守着同一条 S2 列 —— dK/dV 因此是单核顺序累加。",
            ex_sub="把任务矩阵摊到 S1×S2 平面上：纵轴 S1、横轴 S2；色相 = batch、深浅 = S2，格内是 core 与轮次",
            read=["一行里三格深浅不同 = 同 batch 的三条 KV 列；S1 不参与配色，所以行内颜色一致。",
                  "两条 core 各包 3 条列，9 轮正好把 18 个块铺满。"])
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
            read=["同一个格子在两张真实图上各出现一次（色相不同 = batch 不同）。",
                  "一条 core 在两个 batch 之间来回切，所以每核要两个累加 buffer（parity 0/1）。"])
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
            read=["同一格上两个 G 的任务用两行文字分开；色相仍是 batch、深浅仍是 S2。",
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
         (not causal) and g == 1 and k > m, f"core 数 {k} > S1 块数 {m}"),
        (ix.KIND_CAUSAL_SWIZZLE, "Causal Swizzle", causal, "causal 形状才用"),
        (ix.KIND_LEFT_UP_CAUSAL, "Left-Up Causal",
         causal and b % 2 == 0 and m == n, "batch 为偶且 S1 = S2"),
        (ix.KIND_GQA_DENSE, "GQA Dense", g > 1, f"g={g} > 1 才用"),
    ]
    rows = []
    for kk, cn, fits, why in cands:
        rows.append((cn, "★ 本页" if kk == kind else ("也能用" if fits else "用不上"),
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
        ("本页规则\n（逐 batch）", mr, "各按自己的长度排，\n短 batch 不被拖慢"),
        ("按最长 batch 对齐\n（示意）", padded, "所有 batch 按最长的排，\n短 batch 大量空转")]


# ---------------------------------------------------------------- 页面构件

def grid_cells(ts, batch, head=None):
    """覆盖图格内写 core 与轮次；配色交给调用方按 (batch, S2) 决定。"""
    out = {}
    for (j, r), c in ts.items():
        if c is None or c.batch != batch:
            continue
        if head is not None and (c.n2, c.g) != head:
            continue
        out[(c.s1, c.s2)] = (f"C{j}\n第{r}轮", c.batch, c.s2)
    return out


def virtual_cells(kind, shape, mr, kw):
    """虚拟矩形：格内写 core 与轮次，配色同样按 (batch, 虚拟列) 走。"""
    m, n = shape.M(), shape.N()
    cells = {}
    for j in range(1, shape.coreNum + 1):
        for r in range(1, mr + 1):
            c = ix.decode(kind, shape, r, j, **kw)
            if c is None:
                continue
            label = f"C{j}\n第{r}轮"
            if kind == ix.KIND_CAUSAL_SWIZZLE:
                n_new = n + 1 if m == n else (n - m + 2) + (n + 1)
                v = ix.Raw()
                ix.cal_dense_swizzle_index(shape.coreNum, m, n_new, shape.Bh() >> 1,
                                           j, r, v)
                if v.w:
                    cells[(v.s1 - 1, v.s2 - 1)] = (label, c.batch, v.s2)
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
                cells[(vs1 - 1, vs2 - 1)] = (label, c.batch, vs2)
    return cells


def batch_mn(shape, kw, b):
    if "cu_q" in kw:
        lens = kw["cu_q"][b] - (0 if b == 0 else kw["cu_q"][b - 1])
        klen = kw["cu_k"][b] - (0 if b == 0 else kw["cu_k"][b - 1])
        return (lens + 127) // 128, (klen + 127) // 128
    return shape.M(), shape.N()


def repeat_rows(shape):
    """读者一定会问：同一个 S2 / S1 为什么出现在多条 core 的任务里？四行讲清。

    每行都压到一行说得完 —— 表宽在一栏里放得下，才谈得上"补空白"。
    """
    gqa = shape.groupNum > 1
    rows = [("同一个 S2 在多条 core", "低位先走 S2 列：跨轮、跨 batch 就会重复"),
            ("同一个 S1 在多条 core", "列内旋转：每条列都要走一遍所有 S1")]
    if gqa:
        rows += [("一条 KV 列横跨多条 core", "一条列要服务 g 个 Q head，只能切片分派"),
                 ("同一个 (S2,S1) 只出现一次", "双射：每个块只被派一次")]
    else:
        rows += [("同一个 (S2,S1) 只出现一次", "双射：每个块只被派一次"),
                 ("空泡不是 mask", "空泡是没派活，mask 是派了不累加")]
    return rows


def repeat_panel(slide, x, y, shape, col_w=None):
    """同一个值为什么会重复出现 —— 放在哪一栏就按哪一栏的宽度分两列。"""
    rows = repeat_rows(shape)
    return sd.panel(slide, x, y, "同一个值为什么会重复出现", ("看到的现象", "为什么"), rows,
                    col_w=col_w or (2.05, 4.90), row_h=0.38, size=12.0)


# ---------------------------------------------------------------- 排版流

class Col:
    """一栏的排版游标：x 与宽度固定，y 往下走，bottom 是这一栏的底边。"""

    def __init__(self, x, w, y, bottom):
        self.x, self.w, self.y, self.bottom = x, w, y, bottom

    def room(self, h, gap):
        return self.y + gap + h <= self.bottom + 1e-6


def flow(cols, items, gap=0.26):
    """把表按优先级放进"放得下的那一栏"。

    items: [(名字, 偏好栏顺序, make)]，make(栏宽) 给出 (高度, 画法) 或 None（这栏不合适）。
    放不下的表直接跳过 —— 宁可少一块表，也不要压到已经画好的东西上。
    返回被跳过的名字。
    """
    dropped = []
    for name, prefer, make in items:
        for key in prefer:
            col = cols[key]
            spec = make(col.w)
            if not spec:
                continue
            h, draw = spec
            if col.room(h, gap):
                y = col.y + gap
                draw(col.x, y)
                col.y = y + h
                break
        else:
            dropped.append(name)
    return dropped


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
            w=(n_cols + 1) * cell_w, h=0.30, size=13.0, bold=True)
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
                     str(mr),
                     m["low"](shape, kw)))
    sd.spec_table(s, 0.73, 1.72,
                  ("规则", "layout", "causal", "头型", "列私有", "总轮数", "低位先走哪个轴"),
                  rows,
                  col_w=(2.75, 1.10, 0.95, 0.95, 0.95, 0.95, 2.10),
                  row_h=(0.58,) + (0.62,) * 7)
    sd.note(s, 0.73, 7.00,
            "所有规则都是纯算术：(round, core) 一确定，结果就唯一 —— 这就是确定性的来源。",
            w=15.2, h=0.36)
    sd.text(s, 0.73, 7.72, "怎么读后面的例子", w=13.0, h=0.34, size=18, bold=True)
    for i, line in enumerate([
            "· 第 1 页先认公用的轴遍历顺序 b → n2 → s2 → s1 → d，以及 dS 的一列怎么变成 dK/dV 的一行。",
            "· 算法页：伪代码讲逻辑 → 任务矩阵（行 = round，列 = core）→ 为什么这样分。",
            "· 例子页：网格纵轴 S1、横轴 S2，格内写「哪条 core / 第几轮」；灰格 = 这一轮这条 core 空闲。",
            "· 颜色只编码两个轴：色相 = 哪个 batch，同色相的深浅 = 第几条 KV 列（S2）；S1 不参与配色。"]):
        sd.text(s, 0.73, 8.22 + i * 0.42, line, w=9.90, h=0.36, size=15.0,
                color=sd.BODY_TEXT)
    sd.panel(s, 10.60, 1.72, "格子里写什么", ("记号", "含义"),
             [("B", "batch"), ("N2", "KV head"), ("G", "GQA 里的 Q head"),
              ("S1", "Q 方向第几块（128 行）"), ("S2", "KV 方向第几块（128 列）"),
              ("D", "head dim，tile 内不切分")], col_w=(1.10, 4.15), row_h=0.44,
             size=13.0)
    sd.panel(s, 10.60, 5.62, "每个例子都满足的三条不变量", ("不变量", "含义"),
             [("任务不重复", "每个块只被派给一个 (round, core)"),
              ("同一轮 S1 不撞", "各核这一轮写的输出块互不相同"),
              ("列私有", "swizzle 类：一条列只归一条 core")],
             col_w=(1.85, 3.40), row_h=0.52, size=12.5)
    sd.panel(s, 10.60, 8.44, "七种规则归成三条路线", ("路线", "用它的规则"),
             [("列私有", "1 Dense Swizzle、3/4 Causal、6 TND"),
              ("切片 + gcd 修正", "5 GQA Dense（核数不受 S1 块数限制）"),
              ("按面积展平", "7 TND GQA（变长 batch，不分列）")],
             col_w=(1.75, 3.50), row_h=0.52, size=12.5)
    return s


def draw_axis_page(prs):
    """轴遍历顺序 + dS 分块：先认顺序，再认分派，最后认"一列 dS 怎么变成一行 dK/dV"。"""
    s = sd.blank_slide(prs)
    sd.title(s, "1. 轴遍历顺序与 dS 分块", y=0.62)
    sd.text(s, 0.73, 1.22,
            "七种规则共用同一个铺 task id 的顺序：外层慢、内层快。先认这个顺序，后面的分派才看得懂。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    # 轴链 b -> n2 -> s2 -> s1 -> d
    chain = [("b", "最外层"), ("n2", "KV head"), ("s2", "一条 KV 列"),
             ("s1", "列内旋转"), ("d", "tile 内最内层")]
    cx, cy = 1.62, 1.54
    for i, (ax, lab) in enumerate(chain):
        sd.text(s, cx - 0.45, cy, ax, w=0.90, h=0.44, size=24, bold=True,
                align=sd.PP_ALIGN.CENTER)
        sd.text(s, cx - 0.62, cy + 0.52, lab, w=1.24, h=0.28, size=12.0,
                color=sd.BODY_TEXT, align=sd.PP_ALIGN.CENTER)
        if i < len(chain) - 1:
            sd.arrow(s, cx + 0.50, cy + 0.20, cx + 0.86, cy + 0.20)
        cx += 1.36
    sd.text(s, 0.90, 2.42,
            "低位先走内层轴：同一轮里各 core 拿到连续的 task id，落在相邻的 S2 列上。",
            w=8.4, h=0.26, size=13.5, color=sd.BODY_TEXT)

    # ① 顺序 → ② 分派：1 个 batch、9 个块、3 条 core（每条 core 独占一列、轮内旋转 S1）
    dm, dn, dk, dmr = 3, 3, 3, 3
    demo = ix.Shape(batch=1, qSeqLen=384, kvSeqLen=384, qHeadNum=1,
                    kvHeadNum=1, coreNum=dk)
    tdemo = ix.tasks_of(ix.KIND_DENSE_SWIZZLE, demo, dmr)
    cell, gy = 0.68, 3.30
    sd.text(s, 1.70, 2.92, "① task id 铺开的顺序", w=3.20, h=0.28, size=14.0, bold=True)
    order = {(r, c): (str(c * dm + r + 1), 0) for r in range(dm) for c in range(dn)}
    sd.axis_grid(s, 1.70, gy, dm, dn, order, lane_set="plain", cell_in=cell,
                 label_size=14.0)
    sd.axis_arrow(s, 1.24, gy, (dm + 1) * cell - 0.46, "down", "S1")
    sd.text(s, 5.90, 2.92, "② 分派：色相 = core", w=3.20, h=0.28, size=14.0, bold=True)
    disp = {(c.s1, c.s2): (f"C{j}\n第{r}轮", j - 1) for (j, r), c in tdemo.items()}
    sd.axis_grid(s, 5.90, gy, dm, dn, disp, lane_set=LANE_SET, cell_in=cell,
                 label_size=11.0)

    # ③ dS 的一列 → dK/dV 的一行：列私有的理由
    hx, hy = 1.70, 6.72
    sd.text(s, hx, 6.34, "③ dS 的一列 → dK/dV 的一行（同一个 KV 块）",
            w=6.00, h=0.28, size=14.0, bold=True)
    ds_cells = {(r, c): ("", 1 if c == dn - 1 else 0) for r in range(dm) for c in range(dn)}
    sd.axis_grid(s, hx, hy, dm, dn, ds_cells, lane_set="plain", cell_in=cell,
                 label_size=11.0, empty_text="")
    kx = hx + (dn + 1) * cell + 0.66
    dkv = {(r, 0): ("", 1 if r == dm - 1 else 0) for r in range(dm)}
    sd.axis_grid(s, kx, hy, dm, 1, dkv, lane_set="plain", cell_in=cell,
                 label_size=11.0, empty_text="", row_label="S2", col_label="D")
    sd.arrow(s, hx + (dn + 1) * cell + 0.08, hy + (dm + 0.5) * cell,
             kx - 0.08, hy + (dm + 0.5) * cell)
    sd.text(s, kx + (1 + 1) * cell + 0.16, hy + 0.10,
            "dS 的每一列（固定 S2、\n走完所有 S1）累加成\ndK/dV 的一行。\n\n"
            "所以这一列必须由同一\n条 core 顺序算完 ——\n这就是「列私有」。\n\n"
            "D 方向不切分，\n所以只画一格。",
            w=2.20, h=2.90, size=12.5, color=sd.BODY_TEXT, wrap=True,
            anchor=sd.MSO_ANCHOR.TOP)

    # 右栏：为什么这样排 → 同一个值为什么会重复 → task id 展开
    sd.text(s, 10.60, 1.60, "为什么这样排", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate([
            "· 低位走内层轴 → 同一轮各 core 拿到连续的 task id，",
            "  落在相邻的 S2 列（或相邻 batch）上。",
            "· 一条 core 在 m 轮内 task id 不变 → 它守着同一条列，",
            "  只在列内把 S1 转一圈，这才是“单核顺序累加”。",
            "· 所以同一个 S2 会出现在多条 core 的任务里：那是不同轮、",
            "  不同 batch；同一条 core 内部它始终是同一列连续多轮。"]):
        sd.text(s, 10.60, 1.98 + i * 0.32, line, w=5.35, h=0.28, size=13.0,
                color=sd.BODY_TEXT)
    ry = repeat_panel(s, 10.60, 4.28, ix.Shape(batch=2, qSeqLen=384, kvSeqLen=384,
                                                qHeadNum=1, kvHeadNum=1, coreNum=2),
                      col_w=(1.95, 3.30)) + 0.40
    sd.panel(s, 10.60, ry, "task id 展开（1 个 batch，9 个块）",
             ("task id", "B", "N2", "S2", "S1", "core"),
             [(str(t), "1", "1", str((t - 1) // dm + 1), str((t - 1) % dm + 1),
               str((t - 1) % dk + 1)) for t in range(1, dm * dn + 1)],
             col_w=(1.15, 0.70, 0.85, 0.90, 0.90, 0.75), row_h=0.40, size=12.0)

    sd.note(s, 0.73, 10.32,
            "后面每种规则，只是把“低位先走哪个轴”换一下；换法不同，就得到不同的分派与不同的 idle 分布。",
            w=9.70, h=0.66)
    sd.text(s, 0.73, 11.08, "· ① 里的数字 = task id 顺序；② 里色相 = core，格内写第几轮算它。",
            w=9.70, h=0.32, size=16, color=sd.BODY_TEXT)
    sd.text(s, 0.73, 11.44, "· ③ 说明为什么要“列私有”：一个 KV 块的 dK/dV 由 dS 的一整列累加而来。",
            w=9.70, h=0.32, size=16, color=sd.BODY_TEXT)
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
    n_s2 = max(batch_mn(shape, kw, b)[1] for b in range(shape.batch))
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
            # 色相 = batch，深浅 = S2；S1 不参与配色
            cs.append({"lines": lines, "lane": c.batch, "shade": c.s2})
        rows.append((f"第 {r} 轮", cs))
    col_w = min(4.4, (9.95 - 0.73 - 1.05) / max(1, shape.coreNum))
    sd.task_matrix(s, 0.73, ty, [f"C{j}" for j in range(1, shape.coreNum + 1)], rows,
                   col_w=col_w, row_h=MATRIX_ROW_H, lane_set=LANE_SET,
                   shade_count=n_s2, cell_size=10.5)
    bottom = ty + (mr + 1) * MATRIX_ROW_H

    # 「为什么这样分」——直接放在矩阵下面，回答"为什么这么划"
    sd.text(s, 0.73, bottom + 0.30, "为什么这样分", w=4.0, h=0.30, size=15, bold=True)
    for i, line in enumerate(meta["why"]):
        sd.text(s, 0.73, bottom + 0.66 + i * 0.30, line, w=9.60, h=0.28, size=13.0,
                color=sd.BODY_TEXT)
    why_bottom = bottom + 0.66 + len(meta["why"]) * 0.30

    # 右栏
    yy = 2.02
    sd.text(s, RIGHT_X, yy, "格子里写什么", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate(AXIS_PANEL):
        sd.text(s, RIGHT_X, yy + 0.36 + i * 0.28, line, w=4.7, h=0.26, size=13,
                color=sd.BODY_TEXT)
    yy = yy + 0.36 + len(AXIS_PANEL) * 0.28 + 0.20

    # 矩阵和"为什么这样分"讲完之后，左下半和右栏还剩多少就补多少
    def spec_numbers(w):
        rws = numbers_rows(kind, shape, mr, kw)
        return (sd.panel_height(len(rws), 0.44),
                lambda x, y: sd.panel(s, x, y, "这个例子的数字", ("项", "值"), rws,
                                      col_w=(w - 1.40, 1.40), row_h=0.44, size=12.5))

    def spec_percore(w):
        head, rws = lane_column_rows(kind, shape, mr, kw)
        return (sd.panel_height(len(rws), 0.40),
                lambda x, y: sd.panel(s, x, y, "每条 core 负责哪些列", head, rws,
                                      col_w=(0.95, w - 0.95), row_h=0.40, size=12.0))

    def spec_repeat(w):
        return (sd.panel_height(4, 0.38),
                lambda x, y: repeat_panel(s, x, y, shape, col_w=(2.05, w - 2.05)))

    def spec_other(w):
        if "cu_q" in kw and shape.groupNum > 1:
            head, rws = tnd_compare_rows(shape, mr, kw)
            title, col_w = "换成按最长 batch 对齐（示意）", (1.55, 0.85, w - 2.40)
        else:
            head, rws = applicability_rows(kind, shape, mr)
            title, col_w = "同一形状下其它规则能不能用", (1.35, 0.95, w - 2.30)
        return (sd.panel_height(len(rws), 0.46),
                lambda x, y: sd.panel(s, x, y, title, head, rws, col_w=col_w,
                                      row_h=0.46, size=12.0))

    flow({"L": Col(0.73, 9.60, why_bottom, 10.98),
          "R": Col(RIGHT_X, 4.70, yy, 10.98)},
         [("这个例子的数字", ["R", "L"], spec_numbers),
          ("其它规则", ["R", "L"], spec_other),
          ("每条 core 负责哪些列", ["L", "R"], spec_percore),
          ("同一个值为什么会重复", ["L", "R"], spec_repeat)], gap=0.22)
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

    def wrap_rows(cell_in):
        """按给定格子大小先试排一遍，数出一共要占几行网格。"""
        x, rows_, h_ = LEFTX, 1, cell_in
        for b in range(shape.batch):
            m, n = batch_mn(shape, kw, b)
            gw = (n + 1) * cell_in
            if x > LEFTX and x + gw > COL_LIMIT:
                x, rows_, h_ = LEFTX, rows_ + 1, cell_in
            x += gw + 1.35
        return rows_, rows_ * ((n_max + 1) * cell_in) + (rows_ - 1) * 1.15

    cell = max(CELL_IN, min(0.95, 2.80 / (n_max + 1)))
    if wrap_rows(cell)[0] > 1:                 # 网格要占两行以上：缩小格子给下面的表腾地方
        cell = max(CELL_IN, min(cell, 0.78))

    # 覆盖图（S1 x S2）：纵轴 S1、横轴 S2，色相 = batch、深浅 = S2
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
                         lane_set=LANE_SET, cell_in=cell, shade_count=n_max)
            if first:
                sd.axis_arrow(s, gx - 0.68, gy, (m + 1) * cell - cell * 0.6, "down", "S1")
                sd.axis_arrow(s, gx, gy - 0.72, (n + 1) * cell - cell * 0.6, "right", "S2")
                first = False
            row_h = max(row_h, (m + 1) * cell)
            gx += gw + 1.35
    left_bottom = gy + row_h

    causal_kind = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    m0, n0 = shape.M(), shape.N()
    v_cols = n0 if m0 > n0 else n0 + 1
    v_rows = (2 * m0 - n0 + 1) if m0 > n0 else m0
    wide = (v_cols + 1) * 1.05 > 4.70
    v_cells = virtual_cells(kind, shape, mr, kw) if causal_kind else None

    if causal_kind and wide:
        left_bottom = _virtual_grid(s, LEFTX, left_bottom + 0.55, v_cols, v_rows,
                                    v_cells, lane_set=LANE_SET,
                                    shade_count=n_max) + 0.35

    # ---- 剩下的表交给排版流：哪一栏还有地方就放哪一栏
    r = ix.check(kind, shape, mr, **kw)
    priv = ("— 不适用" if shape.groupNum > 1
            else ("✓ 整列只归一条 core" if r["column_private"] else "✗ 有重复"))
    props_rows = [
        ("任务不重复", "✓ 每个块只被派一次" if not r["dup"] else "✗ 有重复"),
        ("同一轮 S1 不撞", "✓ 各核的 S1 互不相同" if not r["dq_conflict"] else "✗ 有冲突"),
        ("每条 core 列私有", priv)]
    compare = "cu_q" in kw and shape.groupNum > 1

    def spec_repeat(w):
        return (sd.panel_height(4, 0.38),
                lambda x, y: repeat_panel(s, x, y, shape, col_w=(2.05, w - 2.05)))

    def spec_percore(w):
        head, rows = lane_column_rows(kind, shape, mr, kw)
        return (sd.panel_height(len(rows), 0.44),
                lambda x, y: sd.panel(s, x, y, "每条 core 负责哪些列", head, rows,
                                      col_w=(0.95, w - 0.95), row_h=0.44, size=12.5))

    def spec_props(w):
        return (sd.panel_height(len(props_rows), 0.44),
                lambda x, y: sd.panel(s, x, y, "这个例子为什么是确定的", ("性质", "本例情形"),
                                      props_rows, col_w=(2.20, w - 2.20), row_h=0.44,
                                      size=12.0))

    def spec_numbers(w):
        rows = numbers_rows(kind, shape, mr, kw)
        return (sd.panel_height(len(rows), 0.44),
                lambda x, y: sd.panel(s, x, y, "这个例子的数字", ("项", "值"), rows,
                                      col_w=(w - 1.40, 1.40), row_h=0.44, size=12.5))

    def spec_trace(w):
        cw = (w - 1.05) / mr
        if cw < 0.52:                     # 格子太窄写不下 S2=…，这一栏就不放
            return None

        def draw(x, y):
            sd.text(s, x, y, "每核每轮守哪条列（表头 = 第几轮）", w=w, h=0.30,
                    size=15.0, bold=True)
            shades = {b: sd.lane_shades(LANE_SET, b, n_max) for b in range(shape.batch)}
            rows = []
            for j in range(1, shape.coreNum + 1):
                cells = []
                for rr in range(1, mr + 1):
                    c = ts.get((j, rr))
                    if c is None:
                        cells.append(None)
                    else:                  # 底色与覆盖图同一套：色相 = batch、深浅 = S2
                        col = shades[c.batch][c.s2 % n_max]
                        cells.append({"text": f"S2={c.s2 + 1}", "fill": col["fill"],
                                      "color": col["text"]})
                rows.append((f"C{j}", cells))
            sd.trace_table(s, x, y + 0.44, [str(rr) for rr in range(1, mr + 1)], rows,
                           total_w=w, first_col_w=1.05, row_h=0.32, size=10.0,
                           head=["轮 \\ 核"])
        return (0.44 + (shape.coreNum + 1) * 0.32, draw)

    def spec_other(w):
        if compare:
            head, rows = tnd_compare_rows(shape, mr, kw)
            title, col_w = "换成按最长 batch 对齐（示意）", (1.55, 0.85, w - 2.40)
        else:
            head, rows = applicability_rows(kind, shape, mr)
            title, col_w = "同一形状下其它规则能不能用", (1.35, 0.95, w - 2.30)
        return (sd.panel_height(len(rows), 0.46),
                lambda x, y: sd.panel(s, x, y, title, head, rows, col_w=col_w,
                                      row_h=0.46, size=12.0))

    cols = {"L": Col(LEFTX, 6.95, left_bottom, 10.16),
            "R": Col(10.60, 5.25, 2.60, 11.72)}
    if causal_kind and not wide:
        def spec_virtual(w):
            def draw(x, y):
                _virtual_grid(s, x, y + 0.44, v_cols, v_rows, v_cells,
                              lane_set=LANE_SET, shade_count=n_max)
            return ((v_rows + 1) * 0.62 + 0.44, draw)
        flow(cols, [("折叠后的虚拟矩形", ["R"], spec_virtual)])
    dropped = flow(cols, [
        ("为什么确定", ["L", "R"], spec_props),
        ("每核列", ["R", "L"], spec_percore),
        ("重复解释", ["L", "R"], spec_repeat),
        ("轮次轨迹", ["L", "R"], spec_trace),
        ("代价数字", ["R", "L"], spec_numbers),
        ("其它规则", ["R", "L"], spec_other),
    ])
    if dropped:
        print(f"   第 {num} 页放不下的表: {dropped}")

    sd.note(s, 0.73, 10.32, txt["key"], w=9.70, h=0.66)
    for i, line in enumerate(txt["read"]):
        sd.text(s, 0.73, 11.08 + i * 0.36, "· " + line, w=9.70, h=0.32, size=16,
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
