"""画出本案例的完整页面。

    python draw_case.py out/v3-index-schedules.pptx

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
                            ("", "非 causal"), ("", "MHA"),
                            ("dk/dv", "列私有")],
        why=["低位是 S2 列 → 同一轮里相邻的核落在**相邻两列**上；",
             "task id 在 m 轮内不变 → 一条核**守死一条列**，列内把 S1 走一遍。",
             "同一个 S2 出现在多条核上，是 **不同 batch / 不同轮**。"]),
    ix.KIND_DENSE_INDEX: dict(
        en="Dense Index", cn="先分批再分列", low=lambda s, kw: "B 批次",
        tags=lambda s, kw: [("layout", "BSND"), ("", "非 causal"),
                            ("", "MHA"), ("dk/dv", "列私有"),
                            ("核数", "> S1 块数")],
        why=["低位换成 batch → 同一轮各核**分属不同 batch**，S1 撞不到一起；",
             "所以**核数可以超过 S1 块数**，代价是列私有要靠切片保证。"]),
    ix.KIND_CAUSAL_SWIZZLE: dict(
        en="Causal Swizzle", cn="因果折叠", low=lambda s, kw: "S2（fold 后）",
        tags=lambda s, kw: [("layout", "BSND"), ("", "causal（方形）"),
                            ("", "MHA"), ("buffer", "2 个 (parity)"),
                            ("可达性", "↪ 仅 Left-Up 内部委托")],
        why=["fold 把两个相邻 batch 的三角拼成一个 **m x (n+1) 的满矩形**，task id 在矩形里照排；",
             "奇数列用 parity-0、偶数列用 parity-1 buffer → 一条核在两个 batch 间来回切。",
             "矩形是满的 → **没有 idle、也不用打 mask**。"]),
    ix.KIND_LEFT_UP_CAUSAL: dict(
        en="Left-Up Causal", cn="左上对齐",
        low=lambda s, kw: "S2 列（同方形）" if s.M() <= s.N() else "S2（虚拟）",
        tags=lambda s, kw: [("layout", "BSND"),
                            ("", "causal（S1 = S2）" if s.M() <= s.N() else "causal（S1 > S2）"),
                            ("", "MHA"),
                            ("S1 = S2 时", "委托方形折叠" if s.M() <= s.N() else "用左上几何"),
                            ("buffer", "2 个 (parity)"),
                            ("可达性", "★ 偶 batch 且 S1 = S2")],
        why=lambda s, kw: (
            ["本例 S1 = S2（m <= n）→ **直接委托给方形折叠**，不启用左上几何；",
             "所以分派结果和 4 节完全一样：**虚拟宽 = n+1**、零 idle、不用打 mask。"]
            if s.M() <= s.N() else
            ["S1 比 S2 长时换一套几何：**虚拟高 = 2m-n+1**，多出来的行装配对 batch 的镜像格；",
             "整个虚拟矩形都派活 —— 零 idle，也不用打 mask（该分支生产选择器不会选，见 5b 页）。"])),
    ix.KIND_GQA_DENSE: dict(
        en="GQA Dense", cn="任务切片", low=lambda s, kw: "S2（切片）",
        tags=lambda s, kw: [("layout", "BSND"), ("", "causal（epilogue mask）"),
                            ("", "GQA"), ("dk/dv", "共享 workspace")],
        why=["一个 KV head 对应 g 个 Q head → 同一 KV 列的 g 份贡献**不保证同核**；",
             "（R 与 g 非整除或 gcd 修正时会分裂）→ 切片分核 + 共享 workspace 的轮序 atomic add。"]),
    ix.KIND_TND_DENSE: dict(
        en="TND Dense Swizzle", cn="逐批列私有", low=lambda s, kw: "本批 S2 列",
        tags=lambda s, kw: [("layout", "TND (变长)"), ("", "非 causal"),
                            ("", "MHA"), ("dk/dv", "列私有")],
        why=["每个 batch 有自己的 round 前缀，**批内仍按列私有**排；",
             "核数超过本批列数时那一条核空转 —— 变长 batch 的代价。"]),
    ix.KIND_TND_GQA_DENSE: dict(
        en="TND GQA Dense", cn="按面积展平", low=lambda s, kw: "展平索引",
        tags=lambda s, kw: [("layout", "TND (变长)"), ("", "causal（epilogue mask）"),
                            ("", "GQA"), ("dk/dv", "共享 workspace")],
        why=["按面积前缀把任务空间**展平后等分成 k 段**，每条核顺序扫自己那段；",
             "不追求列私有，只保证**同轮各核的 (B,N2,G,S1) 互不相同**。"]),
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
                    "    第几行 = (第几列-1 + r-1) % m + 1    # 列内 S1 每轮往下走一行",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="低位走列：同一轮里各核是同一个 batch 的不同列；一条核守死一条列，列内把 S1 走完。",
            ex_sub="把任务矩阵摊到 S1×S2 平面上：纵轴 S1、横轴 S2；颜色 = batch，同一个颜色的深浅 = 第几条 KV 列，格内是 core 与轮次",
            read=["一行三格深浅不同 = 同 batch 的三条 KV 列；**S1 不配色**，所以行内颜色一致。",
                  "2 条 core 各包 3 条列，9 轮把 18 个块铺满。"])
    if kind == ix.KIND_DENSE_INDEX:
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b}（core 数 > S1 块数）",
            pseudo=[f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                    "对每个 (round r, core j):",
                    "    task id = ((r-1) / m) * k + j        # 1 起算",
                    "    第几批 = task id % b，得 0 时取 b     # 低位先走 B（与上一页相反）",
                    "    第几列 = ceil(task id / b)",
                    "    第几行 = ((第几列-1) % m + (r-1) % m) % m + 1",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="低位走批：同一轮里各核分属不同 batch，多出来的核用 batch 维度消化 —— 所以核数可以超过 S1 块数。",
            ex_sub="同一个块集（2 batch x 2x2 块）换成本页规则，只用 2 轮就铺满",
            read=["4 条核各守一条 (B, S2) 列，每块只落在一条核上。",
                  "对比上一页：同轮各核从**同一个 batch 的不同列**变成**同一条列的不同 batch**。"])
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
            key="两个三角正好拼成一个 m 行 n+1 列的满矩形：没有 idle 槽位、也不用打 mask。"
                "（它只作 Left-Up 的内部委托，不单独被选中）",
            ex_sub="先看下面的虚拟矩形（两个三角拼成的满矩形），再对照上面两张真实的块图",
            read=["同一个格子在两张真实图上各出现一次（颜色不同 = batch 不同）。",
                  "**灰格 = causal 区外**（打 mask，不加）；一条 core 在 batch 间来回切 → 每核要**两个 buffer**。"])
    if kind == ix.KIND_LEFT_UP_CAUSAL:
        square = m <= n          # S1 = S2（或更短）时这条规则委托给方形折叠
        return dict(
            sub=f"输入：core 数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · batch {b} · causal，"
                + ("S1 = S2" if square else "S1 > S2"),
            pseudo=([f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                     f"如果 m <= n:  # 本例 {m} <= {n} 成立 → 走这一支",
                     f"    直接套用 Causal Swizzle（方形折叠，见 4 节）",
                     f"    虚拟宽 = n+1 = {n + 1} 列,  虚拟高 = m = {m} 行",
                     "    折回真实坐标、列内走完 S1 —— 与 4 节同一套公式",
                     f"否则 (S1 更长, 虚拟高 = 2m-n+1):  才启用左上几何（见 5b 页）"]
                    if square else
                    [f"core 数 k={k}, S1 块数 m={m}, S2 块数 n={n}, batch 数 b={b}",
                     f"如果 m <= n:  直接套用 Causal Swizzle",
                     f"否则 (S1 更长):  # 本例 {m} > {n}",
                     f"    虚拟高 = 2m-n+1 = {2 * m - n + 1}",
                     "    列号  = (r-1)/虚拟高 * active core 数 + (j-1)",
                     "    配对号 = 列号/n+1;  虚拟列 = 列号%n+1;  虚拟行 = (r-1)%虚拟高+1",
                     "    奇数 batch 可用行数 = m - 虚拟列 + 1",
                     "    如果 虚拟行 <= 可用行数: 奇数 batch, 行 = 虚拟列+虚拟行-1, 列 = 虚拟列",
                     "    否则:                  偶数 batch, 行 = m-(虚拟行-可用行数)+1, 列 = n-虚拟列+1"]),
            key=("S1 = S2 时它不做自己的几何：**直接委托给方形折叠**，结果与 4 节一致。"
                 "（选择器：偶 batch 且 S1 = S2 才选它）"
                 if square else
                 "折叠几何只覆盖 causal 区：虚拟矩形里都派活、零 idle，也不用 mask。"),
            ex_sub=("形状与 4 节相同（S1 = S2），因为这一支就是委托方形折叠 —— 对照两页可以确认结果一致"
                    if square else
                    f"虚拟高 = 2m-n+1 = {2 * m - n + 1} 行：多出来的行装配对 batch 的镜像格"),
            read=(["**同一个 (B, S1, S2) 集合**，与 4 节的例子逐格相同 —— 委托就是这条路。",
                   "区别只在调度器怎么选：S1 = S2 时它可能落到这条规则上，再走进方形折叠。"]
                  if square else
                  ["折叠矩形里没有 idle 槽、也不用 mask；多出来的行不是空转，装配对 batch 的镜像格。",
                   f"虚拟高 = 2m-n+1 = {2 * m - n + 1}：正好装下两个 batch 的 causal 区。"]))
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
                    "    第几行 = (轮内序号 + 起点偏移 - 1) % m",
                    "    若 t1*m < n: 还要一步 ID 重排修正（本例不触发）"],
            key="同一 KV 列的 g 份贡献**不保证同核**（R 与 g 非整除、或 gcd 修正时会分裂）"
                "→ 不依赖列私有，改用共享 workspace 的轮序 atomic add。",
            ex_sub="同一个 (S1,S2) 格上叠着两个 G 的任务，所以按 G 拆成两张图",
            read=["同一格上两个 G 的任务分两行写；颜色仍是 batch、深浅仍是 KV 列。",
                  "本例两条列恰好各自单核；**跨核时不保证列私有** → 共享 workspace 按轮序累加。"])
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
            read=["**灰格 = 本轮无列可派**（batch1 只有 2 列，第 4 轮只剩一条核有活）。",
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
                    "    用面积前缀查出它属于哪个 batch",
                    "    批内号 = 全局 task id - 该 batch 面积前缀 * (N2 数 * g)",
                    "    片号   = ceil(批内号 / (m*n*g));  N2 = 片号 - 1",
                    "    片内号 = 批内号 取模 (m*n*g)，得 0 时取满",
                    "    第几列 = ceil(片内号 / (m*g))",
                    "    第几组 = ceil( (片内号 取模 (m*g)) / m )",
                    "    第几行 = (片内号 取模 (m*g)) 取模 m，得 0 时取 m",
                    "    若 t1 < n: 还有一步 gcd 对齐修正（本例不触发）"],
            key="变长 GQA 无法逐 batch 对齐，直接把整个任务空间展平等分给各核，顺序扫过。",
            ex_sub="面积大的 batch 分到的格子多；每个 (S1,S2) 格上有两个 G 的任务，按 G 拆图",
            read=["四个小块合起来 = 12 个任务，2 条核 x 6 轮扫完，**零 idle**。",
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
        # 一个格子里放多个坐标时必须逐个括起来，否则连成一片读不出分组
        txt = "  ".join(f"(B={a} S2={c})" for a, c in cols) if cols else "（无）"
        rows.append((f"C{j}", txt))
    return ("core", "负责的 (B, S2) 列（按先后顺序）"), rows


def dense_choose_rows(kind, shape, mr):
    """Dense Swizzle 还是 Dense Index —— 两条稠密（非 causal）规则怎么选。

    区别只有一条：task id 的低位先走哪个轴。走列 → 同轮各核是同一个 batch 的不同列；
    走批 → 同轮各核是同一条列的不同 batch，于是核数能超过 S1 块数。
    """
    mine = "Dense Swizzle ★" if kind == ix.KIND_DENSE_SWIZZLE else "Dense Index ★"
    rows = [
        ("低位先走", "Swizzle：S2 列   ·   Index：B 批次"),
        ("同一轮各核落在", "Swizzle：同一个 batch 的不同列\nIndex：同一条列的不同 batch"),
        ("什么时候选它", "Swizzle：核数不多，一条核守死一条列\n"
                         "Index：核数超 S1 块数时用"),
        ("本页用", mine),
    ]
    return ("判据", "两条规则的区别"), rows


def applicability_rows(kind, shape, mr, kw=None):
    """「同一形状下其它规则能不能用」——条件列与判定谓词同源。

    条件列印规则的要求；不适用时只印**本例不满足的那一条**（含本例值），
    避免出现"条件成立却写用不上"这种自相矛盾的对比表。
    """
    kw = kw or {}
    if "cu_q" in kw:              # 变长 batch：S1/S2 块数逐批不同，取最大的那一批来对比
        m = max(batch_mn(shape, kw, b)[0] for b in range(shape.batch))
        n = max(batch_mn(shape, kw, b)[1] for b in range(shape.batch))
    else:
        m, n = shape.M(), shape.N()
    b, g, k = shape.Bh(), shape.groupNum, shape.coreNum
    causal = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    even = b % 2 == 0
    cands = [
        (ix.KIND_DENSE_SWIZZLE, "Dense Swizzle",
         [("非 causal", not causal, "本例是 causal"),
          ("MHA", g == 1, f"本例 g={g}"),
          ("k ≤ m", k <= m, f"本例 k={k} > m={m}")]),
        (ix.KIND_DENSE_INDEX, "Dense Index",
         [("非 causal", not causal, "本例是 causal"),
          ("MHA", g == 1, f"本例 g={g}"),
          ("k > m", k > m, f"本例 k={k} ≤ m={m}")]),
        (ix.KIND_CAUSAL_SWIZZLE, "Causal Swizzle",
         [("causal", causal, "本例非 causal"),
          ("MHA", g == 1, f"本例 g={g}"),
          ("batch 偶", even, "本例 batch 为奇")]),
        (ix.KIND_LEFT_UP_CAUSAL, "Left-Up Causal",
         [("causal", causal, "本例非 causal"),
          ("MHA", g == 1, f"本例 g={g}"),
          ("batch 偶", even, "本例 batch 为奇"),
          ("S1=S2", m == n, f"本例 {m} ≠ {n}")]),
        (ix.KIND_GQA_DENSE, "GQA Dense",
         [("g > 1", g > 1, f"本例 g={g}")]),
    ]
    rows = []
    for kk, cn, clauses in cands:
        fits = all(ok for _, ok, _ in clauses)
        cond = ("、".join(name for name, ok, _ in clauses if ok) if fits else
                next(ex for _, ok, ex in clauses if not ok))
        rows.append((cn, "★本页" if kk == kind else ("也能用" if fits else "用不上"),
                     cond))
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
    """虚拟矩形：格内写 core 与轮次，配色同样按 (batch, 虚拟列) 走。

    走哪套几何跟算法本身一致：**S1 = S2 时 Left-Up 也委托方形折叠**（虚拟宽 = n+1、
    虚拟高 = m），只有 S1 > S2 才用左上几何（虚拟高 = 2m-n+1）。
    """
    m, n = shape.M(), shape.N()
    fold_style = (kind == ix.KIND_CAUSAL_SWIZZLE
                  or (kind == ix.KIND_LEFT_UP_CAUSAL and m <= n))
    cells = {}
    for j in range(1, shape.coreNum + 1):
        for r in range(1, mr + 1):
            c = ix.decode(kind, shape, r, j, **kw)
            if c is None:
                continue
            label = f"C{j}\n第{r}轮"
            if fold_style:
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


def virtual_map(shape, mr, kw=None):
    """虚拟坐标 → 真实坐标：(虚拟列, 虚拟行) → (batch, s1, s2, core, round)。

    `virtual_cells()` 只画格子；这一份把"每条虚拟列由哪些真实格拼出来"算出来，
    页面要用它把"虚拟列"这个抽象概念落到具体坐标上。
    """
    kw = kw or {}
    m, n = shape.M(), shape.N()
    n_new = n + 1 if m == n else (n - m + 2) + (n + 1)
    out = {}
    for j in range(1, shape.coreNum + 1):
        for r in range(1, mr + 1):
            c = ix.decode(ix.KIND_CAUSAL_SWIZZLE, shape, r, j, **kw)
            if c is None:
                continue
            v = ix.Raw()
            ix.cal_dense_swizzle_index(shape.coreNum, m, n_new, shape.Bh() >> 1,
                                       j, r, v)
            if v.w:
                out[(v.s2 - 1, v.s1 - 1)] = (c.batch, c.s1, c.s2, j, r)
    return out, n_new, m


def virtual_column_rows(shape, mr):
    """每条虚拟列：由哪些真实格拼出来、跨几个 batch、要几个累加 buffer。"""
    vmap, n_new, m = virtual_map(shape, mr)
    rows = []
    b1, b2 = (0, 0)
    # 对照组：真实的一列（S2=1），只属于一个 batch
    real = sorted({(bb, s2) for (bb, s1, s2, j, r) in vmap.values()
                   if bb == 0 and s2 == 0})
    rows.append(("普通列（对照）", f"{m} 格全是 (B=1 S2=1)", "1", "1"))
    for vc in range(n_new):
        got = {}
        for (vs2, vs1), (bb, s1, s2, j, r) in vmap.items():
            if vs2 == vc:
                got[(bb, s2)] = got.get((bb, s2), 0) + 1
        parts = " + ".join(f"{cnt} 格 (B={bb + 1} S2={s2 + 1})"
                           for (bb, s2), cnt in sorted(got.items()))
        # 跨两个 batch 的虚拟列才需要两个 parity 累加槽；只落一个 batch 的仍只要一个
        bufs = len({bb for (bb, s2) in got})
        rows.append((f"虚拟列{vc + 1}", parts, str(len(got)), str(bufs)))
    return ("一条列", "由哪些格组成", "跨几个 batch", "要几个 buffer"), rows


def draw_virtual_page(prs, num):
    """折叠出来的坐标系：虚拟列 / 虚拟行是什么，和普通列差在哪。"""
    s = sd.blank_slide(prs)
    m = n = 3
    shape = ix.Shape(batch=2, qSeqLen=m * 128, kvSeqLen=n * 128, qHeadNum=1,
                     kvHeadNum=1, coreNum=2)
    mr = 6
    vmap, n_new, _ = virtual_map(shape, mr)
    ts = ix.tasks_of(ix.KIND_CAUSAL_SWIZZLE, shape, mr)

    sd.title(s, f"{num}a. 虚拟列与虚拟行：折叠出来的坐标系", y=0.62)
    sd.text(s, 0.73, 1.22,
            "折叠把两个 batch 的三角拼成一个满矩形；矩形里的行 / 列不属于任何单个 batch，所以叫虚拟行 / 虚拟列。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    # ---- 三个网格：两个真实三角 → 一个满矩形
    cell, gy = 0.60, 3.10
    for idx, b in enumerate(range(shape.batch)):
        cells = {}
        for (bb, s1, s2, j, r) in vmap.values():
            if bb == b:
                cells[(s1, s2)] = (f"S2={s2 + 1}", b, s2)
        gx = 0.73 + idx * 2.90
        sd.axis_grid(s, gx, gy, m, n, cells, f"① B={b + 1} 的三角（真实坐标）" if idx == 0
                     else f"② B={b + 1} 的三角（真实坐标）",
                     lane_set=LANE_SET, cell_in=cell, shade_count=n,
                     empty_text="mask")
    sd.arrow(s, 6.15, gy + 1.35, 6.60, gy + 1.35)
    fold = {}
    for (vs2, vs1), (bb, s1, s2, j, r) in vmap.items():
        # 格内写全"折回真实坐标"后的三个轴：虚拟行 → 真实 S1 会翻转，这件事要看得见
        fold[(vs1, vs2)] = (f"B={bb + 1}\nS1={s1 + 1}\nS2={s2 + 1}", bb, s2)
    sd.axis_grid(s, 6.70, gy, m, n_new, fold, "③ 拼成满矩形：4 条虚拟列",
                 lane_set=LANE_SET, cell_in=0.66, shade_count=n, head_size=9.5,
                 row_label="虚拟行{v}", col_label="虚拟列{v}", label_size=9.5)

    # ---- 每条虚拟列是怎么拼出来的
    head, rows = virtual_column_rows(shape, mr)
    sd.panel(s, 0.73, 6.40, "每条虚拟列由哪些格拼出来（对照一行普通列）", head, rows,
             col_w=(1.95, 3.45, 1.60, 2.60), row_h=0.46, size=12.0)

    # ---- 右栏：和普通列 / 行的区别
    sd.panel(s, 10.60, 2.60, "普通列 / 行 与 虚拟列 / 行 的区别", ("", "普通的列 / 行", "虚拟列 / 虚拟行"),
             [("坐标是", "真实坐标\n(B, S1, S2)", "折叠矩形里的\n虚拟坐标"),
              ("一条上面有几个 batch", "只有 1 个", "可能跨 2 个"),
              ("一条 core 守它时", "只往一个输出块累加", "可能同时往两个\nbatch 的输出块累加"),
              ("长度", "一个 batch 的\nS1 或 S2 块数", "矩形的高 / 宽")],
             col_w=(1.80, 1.70, 1.75), row_h=0.52, size=11.5)
    sd.panel(s, 10.60, 5.90, "虚拟行又是什么", ("虚拟行", "说明"),
             [("折叠矩形里的行", "不是某个 batch 的 S1 行"),
              ("左上对齐（S1 > S2）", "虚拟高 = 2m-n+1：多出来的\n行装配对 batch 的镜像格"),
              ("整个虚拟矩形", "都派活、零 idle；折叠只覆盖\ncausal 区，不用 mask")],
             col_w=(2.05, 3.20), row_h=0.52, size=11.5)
    sd.panel(s, 10.60, 8.72, "两条 causal 规则各折成什么", ("规则", "折叠出来的矩形"),
             [("Causal Swizzle（S1 = S2）", "虚拟宽 = n+1：两个三角正好\n凑满，没有 idle"),
              ("Left-Up Causal（S1 > S2）", "虚拟高 = 2m-n+1：多出来的\n行是镜像格，同样零 idle")],
             col_w=(2.35, 2.90), row_h=0.58, size=11.5)

    sd.note(s, 0.73, 10.32,
            "虚拟列是折叠的产物：核按虚拟列分派，同一列的格子可能落在两个 batch 上。",
            w=9.70, h=0.36)
    sd.text(s, 0.73, 11.08, "· 普通列只属于一个 batch；跨两个 batch 的虚拟列要**两个累加 buffer**（只跨一个的仍只要一个）。",
            w=9.70, h=0.32, size=15, color=sd.BODY_TEXT)
    sd.text(s, 0.73, 11.44, "· 折回真实坐标时**行列会翻转**（右上那片三角），所以格内写它最终落到哪一块。",
            w=9.70, h=0.32, size=15, color=sd.BODY_TEXT)
    return s


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
    rows = [("同一个 S2 在多条 core", "低位走 S2 列 → **跨轮、跨 batch** 会重复"),
            ("同一个 S1 在多条 core", "列内逐行走 S1 → 每条列都要走一遍 S1")]
    if gqa:
        rows += [("一条 KV 列的 g 份贡献", "不保证同核 → 共享 workspace"),
                 ("同一个 (S2,S1) 只出现一次", "双射：每个块只被派一次")]
    else:
        rows += [("同一个 (S2,S1) 只派一次", "**双射**：每个块只被派一次"),
                 ("空泡不是 mask", "空泡 = 没派活；mask = 派了不累加")]
    return rows


def repeat_panel(slide, x, y, shape, col_w=None, row_h=0.38):
    """同一个值为什么会重复出现 —— 放在哪一栏就按哪一栏的宽度分两列。"""
    rows = repeat_rows(shape)
    return sd.panel(slide, x, y, "同一个值为什么会重复出现", ("看到的现象", "为什么"), rows,
                    col_w=col_w or (2.25, 4.70), row_h=row_h, size=12.0)


# ---------------------------------------------------------------- 排版流

class Col:
    """一栏的排版游标：x 与宽度固定，y 往下走，bottom 是这一栏的底边。"""

    def __init__(self, x, w, y, bottom):
        self.x, self.w, self.y, self.bottom = x, w, y, bottom

    def room(self, h, gap):
        return self.y + gap + h <= self.bottom + 1e-6


def flow(cols, items, gap=0.38):
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
                  cell_w=1.05, cell_h=0.62, shade_count=None, label_size=11.0):
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
            sd._write_cell_lines(cell, [f"虚拟列{c}"], size=label_size,
                                 colors=[sd.TITLE_TEXT], margin=45720)
    for r in range(1, n_rows + 1):
        cell = tbl.cell(r, 0)
        sd._cell_border(cell)
        sd._fill_cell(cell, sd.ON_BLOCK)
        sd._write_cell_lines(cell, [f"虚拟行{r}"], size=label_size,
                                 colors=[sd.TITLE_TEXT], margin=45720)
        for c in range(1, n_cols + 1):
            cell = tbl.cell(r, c)
            sd._cell_border(cell)
            got = cells.get((r - 1, c - 1))
            if got is None:
                sd._fill_cell(cell, hole["fill"])
                sd._write_cell_lines(cell, ["用不到"], size=label_size - 0.5,
                                     colors=[hole["text"]], margin=45720)
            else:
                label, lane = got[0], got[1]
                shade = got[2] if len(got) > 2 else 0
                col = (shades[lane % 8][shade % shade_count] if shades
                       else colors[lane % 8])
                sd._fill_cell(cell, col["fill"])
                sd._write_cell_lines(cell, label.split(), size=label_size,
                                     colors=[col["text"]] * len(label.split()),
                                     margin=45720)
    sd.text(slide, x + 0.04, y - 0.46, "fold 后的虚拟矩形（行 = 虚拟 S1，列 = 虚拟 S2）",
            w=max((n_cols + 1) * cell_w, 4.20), h=0.30, size=13.0, bold=True)
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
                     "causal" if causal else "非 causal",
                     "GQA" if shape.groupNum > 1 else "MHA",
                     "是" if shape.groupNum == 1 else "否",
                     str(mr),
                     m["low"](shape, kw)))
    sd.spec_table(s, 0.73, 1.72,
                  ("规则", "layout", "causal", "MHA/GQA", "列私有", "总轮数", "低位先走哪个轴"),
                  rows,
                  col_w=(2.42, 1.20, 1.20, 1.40, 0.90, 0.90, 1.88),
                  row_h=(0.58,) + (0.62,) * 7)
    sd.note(s, 0.73, 7.12,
            "所有规则都是纯算术：(round, core) 一确定，结果就唯一 —— 这就是确定性的来源。",
            w=15.2, h=0.36)
    sd.text(s, 0.73, 7.52, "表中「causal」= 本页例子的形状；GQA / TND-GQA 的 causal 由 epilogue mask 处理。",
            w=9.90, h=0.28, size=13, color=sd.BODY_TEXT)
    sd.text(s, 0.73, 7.90, "怎么读后面的例子", w=13.0, h=0.34, size=18, bold=True)
    for i, line in enumerate([
            "· 第 1 页先认公用的轴遍历顺序 b → n2 → s2 → s1 → d，以及 dS 的一列怎么变成 dK/dV 的一行。",
            "· 算法页：伪代码讲逻辑 → 任务矩阵（行 = round，列 = core）→ 为什么这样分。",
            "· 例子页：网格纵轴 S1、横轴 S2，格内写「哪条 core / 第几轮」；灰格 = 这一轮这条 core 空闲。",
            "· 颜色只编码两个轴：颜色 = 哪个 batch，同一个颜色的深浅 = 第几条 KV 列（S2）；S1 不参与配色。"]):
        sd.text(s, 0.73, 8.42 + i * 0.42, line, w=9.90, h=0.36, size=15.0,
                color=sd.BODY_TEXT)
    sd.panel(s, 11.05, 1.72, "格子里写什么", ("记号", "含义"),
             [("B", "batch"), ("N2", "KV head"), ("G", "GQA 里的 Q head"),
              ("S1", "Q 方向第几块（128 行）"), ("S2", "KV 方向第几块（128 列）"),
              ("D", "head dim，tile 内不切分")], col_w=(1.05, 3.95), row_h=0.44,
             size=13.0)
    sd.panel(s, 11.05, 5.62, "每个例子都满足的三条不变量", ("不变量", "含义"),
             [("任务不重复", "每个块只被派给一个 (round, core)"),
              ("同一轮 S1 不撞", "各核这一轮写的输出块互不相同"),
              ("列私有", "swizzle 类：一条列只归一条 core")],
             col_w=(1.75, 3.25), row_h=0.52, size=12.5)
    sd.panel(s, 11.05, 8.44, "七种规则归成三条路线", ("路线", "用它的规则"),
             [("列私有", "1 Dense Swizzle、4 Left-Up、6 TND"),
              ("切片 + gcd 修正", "5 GQA Dense（核数不受 S1 块数限制）"),
              ("按面积展平", "7 TND GQA（变长 batch，不分列）")],
             col_w=(1.65, 3.35), row_h=0.52, size=12.5)
    return s


def draw_axis_page(prs):
    """轴遍历顺序 + dS 分块：先认顺序，再认分派，最后认"一列 dS 怎么变成一行 dK/dV"。"""
    s = sd.blank_slide(prs)
    sd.title(s, "1. 轴遍历顺序与 dS 分块", y=0.62)
    sd.text(s, 0.73, 1.22,
            "七种规则共用同一个铺 task id 的顺序：**外层慢、内层快**。先认这个顺序，后面的分派才看得懂。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    # 轴链 b -> n2 -> s2 -> s1 -> d
    chain = [("b", "最外层"), ("n2", "KV head"), ("s2", "一条 KV 列"),
             ("s1", "列内逐行走 S1"), ("d", "tile 内最内层")]
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

    # ① 顺序 → ② 分派：1 个 batch、9 个块、3 条 core（每条 core 独占一列、列内逐行走 S1）
    dm, dn, dk, dmr = 3, 3, 3, 3
    demo = ix.Shape(batch=1, qSeqLen=384, kvSeqLen=384, qHeadNum=1,
                    kvHeadNum=1, coreNum=dk)
    tdemo = ix.tasks_of(ix.KIND_DENSE_SWIZZLE, demo, dmr)
    cell, gy = 0.68, 3.30
    sd.text(s, 1.70, 2.84, "① task id 铺开的顺序", w=3.20, h=0.28, size=14.0, bold=True)
    order = {(r, c): (str(c * dm + r + 1), 0) for r in range(dm) for c in range(dn)}
    sd.axis_grid(s, 1.70, gy, dm, dn, order, lane_set="plain", cell_in=cell,
                 label_size=14.0)
    sd.axis_arrow(s, 1.24, gy, (dm + 1) * cell - 0.46, "down", "S1")
    sd.text(s, 5.90, 2.84, "② 分派：颜色 = core", w=3.20, h=0.28, size=14.0, bold=True)
    disp = {(c.s1, c.s2): (f"C{j}\n第{r}轮", j - 1) for (j, r), c in tdemo.items()}
    sd.axis_grid(s, 5.90, gy, dm, dn, disp, lane_set=LANE_SET, cell_in=cell,
                 label_size=11.0)

    # ③ dS 的一列 → dK/dV 的一行：列私有的理由
    hx, hy = 1.70, 6.72
    sd.text(s, hx, 6.26, "③ dS 的一列 → dK/dV 的一行（同一个 KV 块）",
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
            "  落在**相邻的 S2 列**（或相邻 batch）上。",
            "· 一条 core 在 m 轮内 task id 不变 → 它**守着同一条列**，",
            "  列内把 S1 走一遍，这才是“单核顺序累加”。",
            "· 同一个 S2 出现在多条 core 里，是**不同轮、不同 batch**；",
            "  同一条 core 内部它始终是同一列连续多轮。"]):
        sd.text(s, 10.60, 1.98 + i * 0.32, line, w=5.35, h=0.28, size=13.0,
                color=sd.BODY_TEXT)
    ry = repeat_panel(s, 10.60, 4.28, ix.Shape(batch=2, qSeqLen=384, kvSeqLen=384,
                                                qHeadNum=1, kvHeadNum=1, coreNum=2),
                      col_w=(2.25, 3.00)) + 0.40
    sd.panel(s, 10.60, ry, "task id 展开（1 个 batch，9 个块）",
             ("task id", "B", "N2", "S2", "S1", "core"),
             [(str(t), "1", "1", str((t - 1) // dm + 1), str((t - 1) % dm + 1),
               str((t - 1) % dk + 1)) for t in range(1, dm * dn + 1)],
             col_w=(1.15, 0.70, 0.85, 0.90, 0.90, 0.75), row_h=0.40, size=12.0)

    sd.note(s, 0.73, 10.32,
            "后面每种规则，只是把“低位先走哪个轴”换一下；换法不同，就得到不同的分派与不同的 idle 分布。",
            w=9.70, h=0.66)
    sd.text(s, 0.73, 11.08, "· ① 里的数字 = task id 顺序；② 颜色 = core，格内写第几轮算它。",
            w=9.70, h=0.32, size=16, color=sd.BODY_TEXT)
    sd.text(s, 0.73, 11.44, "· ③ 是“列私有”的理由：一个 KV 块的 dK/dV 由 **dS 的一整列**累加而来。",
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
            # 颜色 = batch，深浅 = 第几条 KV 列；S1 不参与配色
            cs.append({"lines": lines, "lane": c.batch, "shade": c.s2})
        rows.append((f"第 {r} 轮", cs))
    col_w = min(4.4, (9.95 - 0.73 - 1.05) / max(1, shape.coreNum))
    sd.task_matrix(s, 0.73, ty, [f"C{j}" for j in range(1, shape.coreNum + 1)], rows,
                   col_w=col_w, row_h=MATRIX_ROW_H, lane_set=LANE_SET,
                   shade_count=n_s2, cell_size=10.5)
    bottom = ty + (mr + 1) * MATRIX_ROW_H

    # 「为什么这样分」——直接放在矩阵下面，回答"为什么这么划"
    sd.text(s, 0.73, bottom + 0.30, "为什么这样分", w=4.0, h=0.30, size=15, bold=True)
    why_lines = meta["why"](shape, kw) if callable(meta["why"]) else meta["why"]
    for i, line in enumerate(why_lines):
        sd.text(s, 0.73, bottom + 0.66 + i * 0.30, line, w=9.60, h=0.28, size=13.0,
                color=sd.BODY_TEXT)
    why_bottom = bottom + 0.66 + len(why_lines) * 0.30

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
        return (sd.panel_height(len(rws), 0.40),
                lambda x, y: sd.panel(s, x, y, "这个例子的数字", ("项", "值"), rws,
                                      col_w=(w - 1.40, 1.40), row_h=0.40, size=12.5))

    def spec_percore(w):
        head, rws = lane_column_rows(kind, shape, mr, kw)
        return (sd.panel_height(len(rws), 0.40),
                lambda x, y: sd.panel(s, x, y, "每条 core 负责哪些列", head, rws,
                                      col_w=(0.95, w - 0.95), row_h=0.40, size=12.0))

    def spec_repeat(w):
        return (sd.panel_height(4, 0.38),
                lambda x, y: repeat_panel(s, x, y, shape, col_w=(2.25, w - 2.25), row_h=0.36))

    def spec_other(w):
        if kind in (ix.KIND_DENSE_SWIZZLE, ix.KIND_DENSE_INDEX):
            head, rws = dense_choose_rows(kind, shape, mr)
            title, col_w = "Dense Swizzle 还是 Dense Index？", (1.32, w - 1.32)
        elif "cu_q" in kw and shape.groupNum > 1:
            head, rws = tnd_compare_rows(shape, mr, kw)
            title, col_w = "换成按最长 batch 对齐（示意）", (1.55, 0.85, w - 2.40)
        else:
            head, rws = applicability_rows(kind, shape, mr, kw)
            title, col_w = "同一形状下其它规则能不能用", (1.30, 0.84, w - 2.14)
        return (sd.panel_height(len(rws), 0.46),
                lambda x, y: sd.panel(s, x, y, title, head, rws, col_w=col_w,
                                      row_h=0.52, size=11.5))

    flow({"L": Col(0.73, 9.60, why_bottom, 10.98),
          "R": Col(RIGHT_X, 4.70, yy, 10.98)},
         [("这个例子的数字", ["R", "L"], spec_numbers),
          ("其它规则", ["R", "L"], spec_other),
          ("每条 core 负责哪些列", ["L", "R"], spec_percore),
          ("同一个值为什么会重复", ["L", "R"], spec_repeat)], gap=0.32)
    sd.note(s, 0.73, 11.22, txt["key"], w=15.2, h=0.52)
    return s


def draw_leftup_big_page(prs, num):
    """更难的例子：非方形 causal（S1 4 块 · S2 3 块 · 3 条 core）。

    同一个 Left-Up 规则，换成 S2 ≠ S1 的形状：虚拟高 = 2m-n+1 = 6，
    每个核守一条虚拟列走满 6 行，零 idle。
    """
    m, n, k, b, mr = 4, 3, 3, 2, 6
    shape = ix.Shape(batch=b, qSeqLen=m * 128, kvSeqLen=n * 128, qHeadNum=1,
                     kvHeadNum=1, coreNum=k)
    ts = ix.tasks_of(ix.KIND_LEFT_UP_CAUSAL, shape, mr)
    r = ix.check(ix.KIND_LEFT_UP_CAUSAL, shape, mr)
    vm = 2 * m - n + 1
    n_max = n

    s = sd.blank_slide(prs)
    sd.title(s, f"{num}b. Left-Up Causal —— 非方形例子（S1 {m} 块 · S2 {n} 块）", y=0.62)
    sd.text(s, 0.73, 1.22,
            f"上一页 S1 = S2，走的是委托的方形折叠；这一页 S1 > S2，才是它自己的几何：虚拟高 = 2m-n+1 = {vm}。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    for i, line in enumerate(["⚠ 选择器不会走这一支：",
                              "S1 > S2 的 causal 用 dense + mask；",
                              "本页只解释该算法的几何。"]):
        sd.text(s, 10.60, 1.22 + i * 0.30, line, w=5.40, h=0.28, size=13.5,
                color=sd.EMPH_COLOR)
    # 左栏：两个 batch 的真实覆盖图（阶梯状 = causal 区）
    cell, gy = 0.64, 2.30               # 格子放大、字号收小：格内四周留够余量
    for bb in range(b):
        sd.axis_grid(s, LEFTX + bb * ((n + 2) * cell + 1.35), gy, m, n,
                     grid_cells(ts, bb), f"B={bb + 1}",
                     lane_set=LANE_SET, cell_in=cell, shade_count=n_max,
                     label_size=10.5, head_size=10.0, empty_text="mask")
    sd.axis_arrow(s, LEFTX - 0.68, gy, (m + 1) * cell - cell * 0.6, "down", "S1")
    # S2 箭头省掉：这一页副标题更长，S2 标签会压到副标题上；列头本身已写 S2=1..3
    # 左栏下方：折叠出来的虚拟矩形（行 = 虚拟 S1，列 = 虚拟 S2）
    left_bottom = _virtual_grid(s, LEFTX, 6.15, n, vm, virtual_cells(
        ix.KIND_LEFT_UP_CAUSAL, shape, mr, {}), lane_set=LANE_SET,
        cell_w=0.64, cell_h=0.58, shade_count=n_max, label_size=10.0)

    def spec_percore(w):
        head, rows = lane_column_rows(ix.KIND_LEFT_UP_CAUSAL, shape, mr, {})
        return (sd.panel_height(len(rows), 0.42),
                lambda x, y: sd.panel(s, x, y, "每条 core 负责哪些列", head, rows,
                                      col_w=(0.95, w - 0.95), row_h=0.42, size=12.0))

    props = [("任务不重复", "✓ 每个块只被派一次"),
             ("同一轮 S1 不撞", "✓ 各核的 S1 互不相同"),
             ("每条 core 列私有", "✓ 整列只归一条 core")]

    def spec_props(w):
        return (sd.panel_height(len(props), 0.44),
                lambda x, y: sd.panel(s, x, y, "这个例子为什么是确定的", ("性质", "本例情形"),
                                      props, col_w=(2.20, w - 2.20), row_h=0.44,
                                      size=12.0))

    def spec_numbers(w):
        rows = [("任务总数", r["valid"]), ("总槽位（core x round）", r["slots"]),
                ("idle 槽位", r["holes"]), ("虚拟高 = 2m-n+1", vm),
                ("每核负责的真实列数", 2)]
        return (sd.panel_height(len(rows), 0.42),
                lambda x, y: sd.panel(s, x, y, "这个例子的数字", ("项", "值"), rows,
                                      col_w=(w - 1.40, 1.40), row_h=0.42, size=12.0))

    flow({"L": Col(LEFTX, 6.95, left_bottom, 10.16),
          "R": Col(10.60, 5.25, 2.60, 11.72)},
         [("为什么确定", ["L", "R"], spec_props),
          ("每核列", ["L", "R"], spec_percore),
          ("代价数字", ["L", "R"], spec_numbers),
          ("重复解释", ["L", "R"], lambda w: (
              sd.panel_height(4, 0.38),
              lambda x, y: repeat_panel(s, x, y, shape, col_w=(2.25, w - 2.25), row_h=0.36)))])

    sd.note(s, 0.73, 10.42,
            f"形状一变，折叠几何跟着变：虚拟高从 m 变成 2m-n+1 = {vm}，但规则本身没变。",
            w=9.70, h=0.36)
    sd.text(s, 0.73, 11.08, "· 每个核守一条虚拟列，落到真实坐标上就是**两个 batch 各一条 S2 列**。",
            w=9.70, h=0.32, size=15, color=sd.BODY_TEXT)
    sd.text(s, 0.73, 11.44, f"· {k} 条核 x {mr} 轮 = {k * mr} 个槽位，正好铺满因果区的 {r['valid']} 个块。",
            w=9.70, h=0.32, size=15, color=sd.BODY_TEXT)
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

    # 覆盖图（S1 x S2）：纵轴 S1、横轴 S2，颜色 = batch，深浅 = 第几条 KV 列
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
                         lane_set=LANE_SET, cell_in=cell, shade_count=n_max,
                         empty_text="mask" if kind in (ix.KIND_CAUSAL_SWIZZLE,
                                                       ix.KIND_LEFT_UP_CAUSAL) else "空闲")
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
        left_bottom = _virtual_grid(s, LEFTX, left_bottom + 0.85, v_cols, v_rows,
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
                lambda x, y: repeat_panel(s, x, y, shape, col_w=(2.25, w - 2.25), row_h=0.36))

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
                    else:                  # 底色与覆盖图同一套：颜色 = batch，深浅 = 第几条 KV 列
                        col = shades[c.batch][c.s2 % n_max]
                        cells.append({"text": f"S2={c.s2 + 1}", "fill": col["fill"],
                                      "color": col["text"]})
                rows.append((f"C{j}", cells))
            sd.trace_table(s, x, y + 0.44, [str(rr) for rr in range(1, mr + 1)], rows,
                           total_w=w, first_col_w=1.05, row_h=0.32, size=10.0,
                           head=["轮 \\ 核"])
        return (0.44 + (shape.coreNum + 1) * 0.32, draw)

    def spec_other(w):
        if kind in (ix.KIND_DENSE_SWIZZLE, ix.KIND_DENSE_INDEX):
            head, rws = dense_choose_rows(kind, shape, mr)
            title, col_w = "Dense Swizzle 还是 Dense Index？", (1.32, w - 1.32)
        elif "cu_q" in kw and shape.groupNum > 1:
            head, rws = tnd_compare_rows(shape, mr, kw)
            title, col_w = "换成按最长 batch 对齐（示意）", (1.55, 0.85, w - 2.40)
        else:
            head, rws = applicability_rows(kind, shape, mr, kw)
            title, col_w = "同一形状下其它规则能不能用", (1.30, 0.84, w - 2.14)
        return (sd.panel_height(len(rws), 0.46),
                lambda x, y: sd.panel(s, x, y, title, head, rws, col_w=col_w,
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


# ------------------------------------------------------------------ 性能对比
# 口径：msprof device 侧 kernel 时间（Task Duration 最小值，warmup 5 + repeat 20），
# 不是 event record 端到端计时。数据见 perf_matrix.py：
#   本仓库 = det-cmp-v3-swizzle（合并 integration/FAG-V3-A5 cube Optimize 后）；
#   参考仓库 = opst（det 走 torch.use_deterministic_algorithms(True)）。
# 四页：9.1 确定性开销 / 9.2 det-vs-det / 9.3 nd-vs-nd / 9.4 全矩阵明细。
import math

import perf_matrix as pm


def _gm(xs):
    xs = [x for x in xs if x is not None and x > 0]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else float("nan")


def _ratio(num, den):
    return [a / b if (a and b) else None for a, b in zip(num, den)]


def _size_class(name):
    """按 case 名的语义分小 / 中 / 大（与测试矩阵命名一致）。"""
    if name.startswith("bsnd"):
        if "small" in name or "tiny" in name:
            return "小"
        if "mid" in name:
            return "中"
        return "大"          # long / large
    if "small" in name or "ragged" in name:
        return "小"
    if "eq" in name or "pack8" in name:
        return "中"
    return "大"              # large


SIZES = ("小", "中", "大")
# matplotlib 默认字体没有 CJK 字形：图内标题用 ASCII，页面表格/文字用中文
SZ_EN = {"小": "small", "中": "mid", "大": "large"}
GROUP_COLS = tuple(f"{lay} {sz}" for lay in ("BSND", "TND") for sz in SIZES)


def _group_idx(lay, sz):
    return [i for i, (n, l, _) in enumerate(pm.CASES)
            if l == lay and _size_class(n) == sz]


def _layout_idx(lay):
    return [i for i, c in enumerate(pm.CASES) if c[1] == lay]


def _group_vals(vals, lay, sz):
    return [vals[i] for i in _group_idx(lay, sz)]


def _rate(vals, th=0.8):
    xs = [v for v in vals if v is not None]
    return sum(1 for v in xs if v >= th) / len(xs) if xs else 0.0


def _extreme(vals, mode):
    xs = [v for v in vals if v is not None]
    if not xs:
        return float("nan")
    return min(xs) if mode == "min" else max(xs)


def _stat_rows(series_specs):
    """统计表行：每个 series 一行几何平均（表列 = 6 个 size 组）。"""
    rows = []
    for label, vals, _c in series_specs:
        rows.append((f"{label} 几何平均",
                     [_gm(_group_vals(vals, lay, sz))
                      for lay in ("BSND", "TND") for sz in SIZES],
                     "{:.2f}"))
    return rows


def draw_perf_ratio_page(prs, num, title, sub, size, series_specs, fig_note,
                         table_header, table_rows, read_rows, key,
                         split=0.8, ref=0.8):
    """一张比值型性能页：BSND/TND 两幅全宽子图（该 size 组的全部 case）+
    2 列统计表 + 结论。"""
    s = sd.blank_slide(prs)
    sd.title(s, f"{num}. {title}", y=0.62)
    sd.text(s, 0.73, 1.22, sub, w=15.2, h=0.30, size=13.0, color=sd.BODY_TEXT)
    panels = []
    for lay in ("BSND", "TND"):
        idx = _group_idx(lay, size)
        series = [(label, [vals[i] if vals[i] is not None else 0.0 for i in idx],
                   color) for label, vals, color in series_specs]
        panels.append(dict(
            title=f"{lay} {SZ_EN[size]} ({len(idx)})",
            groups=[pm.SHORT[i] for i in idx],
            series=series, ylabel="ratio", ref=ref,
            split=split if len(series) == 1 else None,
            bar_w=0.60 if len(series) == 1 else 0.40,
            xrot=90, show_values=False, legend=True,
            value_size=7.0, label_size=8.0))
    fig_bottom = sd.perf_figure(s, 0.73, 1.64, 15.2, 6.05, panels,
                                note=fig_note)
    ty = fig_bottom + 0.14
    tbl_bottom = sd.perf_table(s, 0.73, ty, ("BSND", "TND"),
                               [(r[0], r[1]) for r in table_rows],
                               header=f"{table_header} · {size}",
                               first_col_w=3.20, col_w=1.55,
                               size=11.5, row_h=0.42,
                               fmts=[r[2] for r in table_rows], best=None,
                               note=None)
    pnl_bottom = ty
    if read_rows:
        pnl_bottom = sd.panel(s, 7.55, ty, "怎么读", ("看什么", "结论"),
                              read_rows, col_w=(1.35, 6.10), row_h=0.50,
                              size=10.5)
    # 结论放在统计表与「怎么读」面板之下（取两者实际底边）
    sd.note(s, 0.73, min(max(tbl_bottom, pnl_bottom) + 0.12, 11.16), key,
            w=15.2, h=0.60, size=11.5)
    return s


def draw_perf_detail_page(prs):
    """9.4 全矩阵明细：BNSD/TND 各两张表（case × 四个核时值）。"""
    s = sd.blank_slide(prs)
    sd.title(s, "9.10. 全矩阵明细（核时 μs，min of 25）", y=0.62)
    sd.text(s, 0.73, 1.22,
            "36 case（BSND 21 + TND 15）× 本仓库 det/nd 与 opst det/nd · "
            "msprof device 侧 kernel 时间（Task Duration min）· "
            "空缺 = 参考实现无法运行",
            w=15.2, h=0.30, size=13.0, color=sd.BODY_TEXT)
    cols = ("ours det", "ours nd", "opst det", "opst nd")
    header = "核时 (μs)"

    def rows_for(indices):
        out = []
        for i in indices:
            name, _lay, label = pm.CASES[i]

            def f(v):
                return "—" if v is None else f"{v:.1f}"

            out.append((label,
                        [f(pm.OURS_DET[i]), f(pm.OURS_ND[i]),
                         f(pm.OPST_DET[i]), f(pm.OPST_ND[i])]))
        return out

    bsnd = _layout_idx("BSND")
    tnd = _layout_idx("TND")
    blocks = [
        (0.73, 1.72, bsnd[:11]), (8.05, 1.72, bsnd[11:]),
        (0.73, 6.48, tnd[:8]), (8.05, 6.48, tnd[8:]),
    ]
    for x, y, idxs in blocks:
        rows = rows_for(idxs)
        sd.perf_table(s, x, y, cols, rows, header=header,
                      first_col_w=3.05, col_w=0.98, size=10.0, row_h=0.335,
                      fmts=["{}"] * len(rows), best=None)
    sd.note(s, 0.73, 10.95,
            "表内加粗 = 该列（口径）的全局最小值（核时越小越好）；"
            "取值均为 msprof Task Duration 最小值，非 event record。",
            w=15.2, h=0.34)
    return s


def draw_perf_pages(prs):
    """性能对比 10 页：确定性开销 / det-vs-det / nd-vs-nd 各按 小/中/大 分页 +
    全矩阵明细页。每页一幅 BSND、一幅 TND（该 size 组的全部 case，短标签）。
    """
    od, ond = pm.OURS_DET, pm.OURS_ND
    pd, pnd = pm.OPST_DET, pm.OPST_ND
    pen_ours = _ratio(od, ond)
    pen_opst = _ratio(pd, pnd)
    det_ratio = _ratio(pd, od)          # opst-det / ours-det
    nd_ratio = _ratio(pnd, ond)         # opst-nd / ours-nd

    def gvals(vals, lay, sz):
        return _group_vals(vals, lay, sz)

    def gm_pair(vals, sz):
        return [_gm(gvals(vals, "BSND", sz)), _gm(gvals(vals, "TND", sz))]

    def rate_pair(vals, sz):
        return [_rate(gvals(vals, "BSND", sz), 0.8),
                _rate(gvals(vals, "TND", sz), 0.8)]

    def min_pair(vals, sz):
        return [_extreme(gvals(vals, "BSND", sz), "min"),
                _extreme(gvals(vals, "TND", sz), "min")]

    def max_pair(vals, sz):
        return [_extreme(gvals(vals, "BSND", sz), "max"),
                _extreme(gvals(vals, "TND", sz), "max")]

    f2, fp = "{:.2f}", "{:.0%}"

    # ---- 确定性开销（9.1-9.3，按 size 分页） ----
    for i, sz in enumerate(SIZES):
        num = f"9.{i+1}"
        draw_perf_ratio_page(
            prs, num, f"性能对比：确定性开销（{sz} shape）",
            f"倍率 = det 核时 / nd 核时（> 1 = det 更慢）· {sz} shape 组 · "
            "msprof kernel 时间（device 侧），非 event record",
            sz,
            [("ours det/nd", pen_ours, sd.PERF_SELF),
             ("opst det/nd", pen_opst, sd.PERF_REF)],
            "核时取自 msprof Task Duration 最小值；倍率 = det / nd；虚线 = 1.0（无开销）",
            "det/nd 开销 (×)",
            [("ours det/nd 几何平均", gm_pair(pen_ours, sz), f2),
             ("opst det/nd 几何平均", gm_pair(pen_opst, sz), f2),
             ("ours 最差组", max_pair(pen_ours, sz), f2)],
            [("倍率 > 1", "确定性有开销"),
             ("BSND / TND", f"{_gm(gvals(pen_ours, 'BSND', sz)):.2f}× / "
                            f"{_gm(gvals(pen_ours, 'TND', sz)):.2f}×")],
            f"结论：{sz} shape 上本仓库 det/nd = "
            f"{_gm(gvals(pen_ours, 'BSND', sz)):.2f}×（BSND）/ "
            f"{_gm(gvals(pen_ours, 'TND', sz)):.2f}×（TND）；opst 为 "
            f"{_gm(gvals(pen_opst, 'BSND', sz)):.2f}× / "
            f"{_gm(gvals(pen_opst, 'TND', sz)):.2f}×。",
            ref=1.0, split=1.0)

    # ---- det-vs-det（9.4-9.6） ----
    for i, sz in enumerate(SIZES):
        num = f"9.{i+4}"
        draw_perf_ratio_page(
            prs, num, f"性能对比：det-vs-det（{sz} shape）",
            f"比值 = opst-det / 本仓库-det（≥ 0.8 = 达标）· {sz} shape 组 · "
            "核时为 msprof kernel 时间（device 侧）",
            sz,
            [("opst-det / ours-det", det_ratio, sd.PERF_SELF)],
            "核时取自 msprof Task Duration 最小值；虚线 = 0.8 目标线；"
            "< 0.8 的柱标灰 = 本仓库用时超过 opst 的 1.25×",
            "det 对比 (×)",
            [("opst/ours 几何平均", gm_pair(det_ratio, sz), f2),
             ("达标 (≥0.8×)", rate_pair(det_ratio, sz), fp),
             ("最差（组内 min）", min_pair(det_ratio, sz), f2)],
            [("≥ 0.8", "达标（蓝柱）"),
             ("BSND / TND", f"{_gm(gvals(det_ratio, 'BSND', sz)):.2f}× / "
                            f"{_gm(gvals(det_ratio, 'TND', sz)):.2f}×"),
             ("达标率", f"{_rate(gvals(det_ratio, 'BSND', sz), 0.8):.0%} / "
                        f"{_rate(gvals(det_ratio, 'TND', sz), 0.8):.0%}")],
            f"结论：{sz} shape 的 det 比值 "
            f"{_gm(gvals(det_ratio, 'BSND', sz)):.2f}×（BSND）/ "
            f"{_gm(gvals(det_ratio, 'TND', sz)):.2f}×（TND）；"
            f"达标 {_rate(gvals(det_ratio, 'BSND', sz), 0.8):.0%} / "
            f"{_rate(gvals(det_ratio, 'TND', sz), 0.8):.0%}。")

    # ---- nd-vs-nd（9.7-9.9） ----
    for i, sz in enumerate(SIZES):
        num = f"9.{i+7}"
        draw_perf_ratio_page(
            prs, num, f"性能对比：nd-vs-nd（{sz} shape）",
            f"比值 = opst-nd / 本仓库-nd（≥ 0.8 = 达标）· {sz} shape 组 · "
            "核时为 msprof kernel 时间（device 侧）",
            sz,
            [("opst-nd / ours-nd", nd_ratio, sd.PERF_SELF)],
            "核时取自 msprof Task Duration 最小值；虚线 = 0.8 目标线；"
            "< 0.8 的柱标灰；nd 差距是既有主流水问题，与确定性重构无关",
            "nd 对比 (×)",
            [("opst/ours 几何平均", gm_pair(nd_ratio, sz), f2),
             ("达标 (≥0.8×)", rate_pair(nd_ratio, sz), fp),
             ("最差（组内 min）", min_pair(nd_ratio, sz), f2)],
            [("≥ 0.8", "达标（蓝柱）"),
             ("BSND / TND", f"{_gm(gvals(nd_ratio, 'BSND', sz)):.2f}× / "
                            f"{_gm(gvals(nd_ratio, 'TND', sz)):.2f}×"),
             ("达标率", f"{_rate(gvals(nd_ratio, 'BSND', sz), 0.8):.0%} / "
                        f"{_rate(gvals(nd_ratio, 'TND', sz), 0.8):.0%}")],
            f"结论：{sz} shape 的 nd 比值 "
            f"{_gm(gvals(nd_ratio, 'BSND', sz)):.2f}×（BSND）/ "
            f"{_gm(gvals(nd_ratio, 'TND', sz)):.2f}×（TND）；"
            "差距来自既有主流水，与确定性重构无关。")

    # ---- 9.10 明细 ----
    draw_perf_detail_page(prs)


def main(path):
    prs = sd.new_deck("4:3")
    draw_overview(prs)
    draw_axis_page(prs)
    for i, (name, kind, shape, mr, kw, causal) in enumerate(ix.cases(), start=2):
        if kind == ix.KIND_CAUSAL_SWIZZLE:      # 折叠前一页先把坐标系讲清楚
            draw_virtual_page(prs, i)
        draw_algo_page(prs, i, name, kind, shape, mr, kw, causal)
        draw_example_page(prs, i, name, kind, shape, mr, kw, causal)
        if kind == ix.KIND_LEFT_UP_CAUSAL:      # 再加一页更大的非方形例子
            draw_leftup_big_page(prs, i)
    draw_perf_pages(prs)                        # 可选：有 profiling 数据才画（多页）
    sd.save(prs, path)
    errors, warns = sd.check_layout(prs)
    cells = sd.check_cells(prs)
    gaps = sd.check_gaps(prs)
    print(f"wrote {path}  ({len(prs.slides._sldIdLst)} 页)")
    print(f"版心检查: {len(errors)} 越界 / {len(warns)} 重叠 / "
          f"{len(cells)} 格内问题 / {len(gaps)} 间距过近")
    for c in cells[:14]:
        print(f"  □ S{c[0]} {c[1]} r{c[2]}c{c[3]}: {c[7]} 文字 {c[4]} / 可用 {c[5]}"
              f" / 一侧 {c[6]}  「{c[8]}」")
    for g in gaps[:14]:
        print(f"  ⇔ S{g[0]} {g[1]} ↔ {g[2]}: {g[3]}间隙 {g[4]}")
    for e in errors[:10]:
        print("  !", e)
    for w in warns[:10]:
        print("  ~", w)
    return len(errors)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/v3-index-schedules.pptx"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sys.exit(1 if main(out) else 0)
