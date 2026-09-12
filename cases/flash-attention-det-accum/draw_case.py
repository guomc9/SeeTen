"""画出本案例的完整页面：总览 + 7 种索引算法 x（算法页 + 例子页）。

    python draw_case.py out/v4-index-schedules.pptx

页面结构遵循 SKILL.md 的硬规则：标题 + 子标题 → 伪代码块 → 任务矩阵（轮 x 核）
→ 空白处补辅助表 → 表格外的短注；收尾跑 check_layout。
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
MATRIX_ROW_H = 0.50
LEFTX, COL_LIMIT = 2.10, 9.05
RIGHT_X = 11.30

AXIS_PANEL = ["B  = 第几批", "N2 = 第几个 KV 头", "G  = GQA 组里第几个 Q 头",
              "S1 = Q 方向第几块（每块 128 行）",
              "S2 = KV 方向第几块（每块 128 列）",
              "D  = 头维，整块不切分"]


# ---------------------------------------------------------------- 每页文字

def page_text(name, kind, shape, mr, kw):
    m, n, b, g, k = shape.M(), shape.N(), shape.Bh(), shape.groupNum, shape.coreNum

    def rag():
        return ([kw["cu_q"][0]] + [kw["cu_q"][i] - kw["cu_q"][i - 1]
                                   for i in range(1, shape.batch)],
                [kw["cu_k"][0]] + [kw["cu_k"][i] - kw["cu_k"][i - 1]
                                   for i in range(1, shape.batch)])

    if kind == ix.KIND_DENSE_SWIZZLE:
        return dict(
            title="列私有 swizzle：一条核包下一条 KV 列",
            sub=f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 批次 {b}",
            pseudo=[f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}, 批数 b={b}",
                    "对每个 (轮 r, 核 j):",
                    "    任务号 = ((r-1) / m) * k + (j-1)     # 每 m 轮换一次任务号",
                    "    第几列 = 任务号 % n + 1               # 低位先走 S2 列轴",
                    "    第几批 = 任务号 / n + 1               # 列走完才换批",
                    "    第几行 = (第几列-1 + r-1) % m + 1     # 同一列内 S1 每轮转一格",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="一条核在 m 轮里始终守着同一条 S2 列，只把 S1 转一圈 —— dK/dV 因此是单核顺序累加。",
            ex_sub="把上面的任务矩阵摊到 S1×S2 平面上：纵轴 S1、横轴 S2，颜色是核，格内是第几轮",
            read=["看每一列的颜色：整列同色，就是“列私有”。",
                  "两条核各包 3 条列，9 轮正好把 18 个块铺满。"])
    if kind == ix.KIND_DENSE_INDEX:
        return dict(
            title="批优先旋转：核数多于 S1 块数时用",
            sub=f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 批次 {b}",
            pseudo=[f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}, 批数 b={b}",
                    "对每个 (轮 r, 核 j):",
                    "    任务号 = ((r-1) / m) * k + j          # 1 起算",
                    "    第几批 = 任务号 % b，得 0 时取 b       # 低位先走 B 轴（与上一页相反）",
                    "    第几列 = ceil(任务号 / b)",
                    "    第几行 = ((第几列 % m) + (r % m) - 1) % m",
                    "    输出: B, N2, G, S1=第几行, S2=第几列"],
            key="低位改成批号后，同一轮里各核落在不同批上，S1 撞不到一起 —— 所以核数可以超过 S1 块数。",
            ex_sub="同一个块集（2 批 x 2x2 块）换成本页规则，只用 2 轮就铺满",
            read=[f"{k} 条核各守一条列，每列恰好 2 个块。",
                  "对比上一页：核数 4 > S1 块数 2，列优先的规则在这里不能用。"])
    if kind == ix.KIND_CAUSAL_SWIZZLE:
        return dict(
            title="因果折叠：两个批拼成一个满矩形",
            sub=f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 批次 {b}（因果）",
            pseudo=[f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}, 批数 b={b}",
                    "第 1 步：把相邻两个批拼成一个虚拟矩形",
                    f"    虚拟宽 = n+1 = {n + 1} 列,  虚拟高 = m = {m} 行,  虚拟批数 = b/2",
                    "第 2 步：在虚拟矩形里按“列私有”规则取任务（同第一页）",
                    "第 3 步：把虚拟坐标折回真实坐标",
                    "    如果 虚拟行 >= 虚拟列+1:  # 右上三角",
                    "        批 = 2*虚拟批; 行 = m+1-虚拟行; 列 = 2n-m-虚拟列+2",
                    "    否则: 批 = 2*虚拟批-1     # 左下三角，行列照抄"],
            key="两个三角正好拼成一个 m 行 n+1 列的满矩形：没有空泡、也不用打 mask。",
            ex_sub="先看中间的虚拟矩形（两个三角拼成的满矩形），再对照左右两张真实的块图",
            read=["同一个格子在两张真实图上各出现一次，颜色说明同一条核在两边交替干活。",
                  "一条核在两个批之间来回切，所以每核要两个累加缓冲（parity 0/1）。"])
    if kind == ix.KIND_LEFT_UP_CAUSAL:
        return dict(
            title="左上对齐因果：S1 比 S2 长时的几何",
            sub=f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 批次 {b}（因果，S1 更长）",
            pseudo=[f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}, 批数 b={b}",
                    "如果 m <= n:  直接套用上一页的因果折叠",
                    "否则 (S1 更长):",
                    f"    虚拟高 = 2m-n+1 = {2 * m - n + 1}",
                    "    列号  = (r-1)/虚拟高 * 可用核数 + (j-1)",
                    "    配对号 = 列号/n+1;  虚拟列 = 列号%n+1;  虚拟行 = (r-1)%虚拟高+1",
                    "    奇数批可用行数 = m - 虚拟列 + 1",
                    "    如果 虚拟行 <= 可用行数: 奇数批, 行 = 虚拟列+虚拟行-1, 列 = 虚拟列",
                    "    否则:                  偶数批, 行 = m-(虚拟行-可用行数)+1, 列 = n-虚拟列+1"],
            key="虚拟矩形比真实因果区大，多出来的轮次要靠 mask 打掉（这些块贡献精确 0）。",
            ex_sub=f"虚拟高 {2 * m - n + 1} 行里，每列只有 {m} 行有活；灰格是凑不满的部分",
            read=["红色格 = 本轮该核没任务（空泡）；灰格 = 落在因果区外、要靠 mask 的块。",
                  "注：选择器目前只在 S1 与 S2 等长时选左上折叠。"])
    if kind == ix.KIND_GQA_DENSE:
        return dict(
            title="GQA：把任务切成连续段分给各核",
            sub=f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 批次 {b} · GQA 组 {g}",
            pseudo=[f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}, 批数 b={b}, 组数 g={g}",
                    f"每条核要跑几轮: R = max(ceil(b*n*g/k), ceil(n/m), g) = {mr // m}",
                    "对每个 (轮 r, 核 j):",
                    "    任务号 = (j-1)*R + ceil(r/m)      # 核 j 独占 R 个连续任务号",
                    "    批 = ceil( (任务号%(b*g) 或取满) / g )",
                    "    第几列 = ceil(任务号 / (b*g))",
                    "    第几组 = 任务号 % g，得 0 时取 g",
                    "    起点偏移 = ceil( (第几列 % (t1*m) 或取满) / t1 ),  t1 = R/gcd(b*g, R)",
                    "    第几行 = (轮内序号 + 起点偏移 - 1) % m"],
            key="一条 KV 列可能横跨两条核，没法私有化 —— 改用共享 workspace 的轮序原子加，"
                "确定性靠“同轮各核的 (B,N2,G,S1) 互不相同”。",
            ex_sub="同一个 (S1,S2) 格上叠着两个组的任务，所以按组拆成两张图",
            read=["颜色 = 哪条核；两张图合起来看，8 个任务各归各的核。",
                  "组 1 和组 2 交替落位，避免同轮抢同一个 S1。"])
    if kind == ix.KIND_TND_DENSE:
        q, kk = rag()
        return dict(
            title="变长 batch（MHA）：逐批列私有",
            sub=("输入：核数 " + str(k) + " · 各批 S1 块数 "
                 + str([(x + 127) // 128 for x in q]) + " · 各批 S2 块数 "
                 + str([(x + 127) // 128 for x in kk]) + "（长度不等）"),
            pseudo=[f"核数 k={k}, 批数 b={shape.batch}, 各批长度不同",
                    "先算每个批要跑几轮，存成前缀表（轮数可以逐批不同）:",
                    "    每批轮数 = ceil(该批列数 * 头数 / k) * 该批 S1 块数",
                    f"    例子: 批1 要 {kw['prefix'][1] - kw['prefix'][0]} 轮, "
                    f"批2 要 {kw['prefix'][2] - kw['prefix'][1]} 轮 → 前缀 {kw['prefix']}",
                    "对每个 (轮 r, 核 j):",
                    "    在轮前缀表里查 r 落到哪个批, 批内轮号 = r - 该批前缀",
                    "    任务号 = (批内轮号 / 该批S1块数) * k + (j-1)",
                    "    第几列 = 任务号 % 该批S2块数",
                    "    第几行 = (第几列 + 批内轮号) % 该批S1块数",
                    "    任务号超出该批列数 → 本核本轮空闲"],
            key="每个批按自己的长度排轮次，短批不拖累长批；核数超过本批列数时会有空泡。",
            ex_sub="两批的网格大小不同：批1 是 3x2 块，批2 是 2x3 块",
            read=["灰格 = 本轮该核没有可派的列（批1 只有 2 列，第 4 轮只剩一条核有活）。",
                  "对比算法页的对照表：按最长批对齐要多花好几轮。"])
    if kind == ix.KIND_TND_GQA_DENSE:
        q, kk = rag()
        return dict(
            title="变长 batch（GQA）：按面积展平后再切段",
            sub=("输入：核数 " + str(k) + " · 各批 S1 块数 "
                 + str([(x + 127) // 128 for x in q]) + " · 各批 S2 块数 "
                 + str([(x + 127) // 128 for x in kk]) + f" · GQA 组 {g}"),
            pseudo=[f"核数 k={k}, 批数 b={shape.batch}, 组数 g={g}, 各批长度不同",
                    "先算每批的任务面积并累加:",
                    "    面积 = 该批 S1 块数 * S2 块数;  面积前缀 = 逐批累加",
                    f"    例子: 面积前缀 {kw['area_prefix']}",
                    f"总轮数 = max(ceil(总面积*头数*组/核数), 最大S1块数*组, 最大S2块数) = {mr}",
                    "对每个 (轮 r, 核 j):",
                    "    全局任务号 = (j-1) * 总轮数 + r      # 每条核独占一段，顺序扫",
                    "    用面积前缀查出它属于哪个批;  批内号 = 全局任务号 - 该批面积前缀*头数",
                    "    第几组 = 批内号 换算;  第几行 = 批内号 % m;  第几列 = ceil(批内号 / (m*g))"],
            key="变长 GQA 无法逐批对齐，直接把整个任务空间展平等分给各核，顺序扫过。",
            ex_sub="面积大的批分到的格子多；每个 (S1,S2) 格上有两个组的任务，按组拆图",
            read=["四个小块合起来 = 12 个任务，正好被 2 条核 x 6 轮扫完，零空泡。",
                  "批2 只有 1x2 块，所以它那两张图更矮。"])
    raise KeyError(name)


# ---------------------------------------------------------------- 辅助表

def numbers_rows(kind, shape, mr, kw):
    r = ix.check(kind, shape, mr, **kw)
    rows = [("任务总数", r["valid"]), ("总槽位（核 x 轮）", r["slots"]),
            ("空泡 / 无任务", r["holes"])]
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
    return ("核", "负责的 (B, S2) 列（按先后顺序）"), rows


def applicability_rows(kind, shape, mr):
    """同一形状下，别的规则能不能用（由各规则的前提条件推出，不写死）。"""
    m, n, b, g, k = shape.M(), shape.N(), shape.Bh(), shape.groupNum, shape.coreNum
    causal = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    cands = [
        (ix.KIND_DENSE_SWIZZLE, "列私有 swizzle",
         (not causal) and g == 1 and k <= m, f"核数 {k} ≤ S1 块数 {m}"),
        (ix.KIND_DENSE_INDEX, "批优先旋转",
         (not causal) and g == 1 and k > m, f"核数 {k} > S1 块数 {m} 时才需要"),
        (ix.KIND_CAUSAL_SWIZZLE, "因果折叠", causal, "因果形状才用"),
        (ix.KIND_LEFT_UP_CAUSAL, "左上因果折叠",
         causal and b % 2 == 0 and m == n, f"批次 {b} 为偶且 S1 与 S2 等长"),
        (ix.KIND_GQA_DENSE, "GQA 切片", g > 1, f"组数 {g} > 1 才用"),
    ]
    rows = []
    for kk, cn, fits, why in cands:
        if kk == kind:
            rows.append((cn, "★ 本页用它", why))
        elif fits:
            rows.append((cn, "也能用", why))
        else:
            rows.append((cn, "用不上", why))
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
        ("本页规则（逐批）", mr, "每批按自己的长度排，短批不拖累长批"),
        ("按最长批对齐（示意）", padded, "所有批按最长的排，短批大量空转")]


# ---------------------------------------------------------------- 覆盖图

def grid_cells(ts, batch, head=None):
    out = {}
    for (j, r), c in ts.items():
        if c is None or c.batch != batch:
            continue
        if head is not None and (c.n2, c.g) != head:
            continue
        out[(c.s1, c.s2)] = (f"第{r}轮", j - 1)
    return out


def virtual_cells(kind, shape, mr, kw):
    """因果折叠：虚拟矩形里每格派给哪条核、第几轮。"""
    m, n = shape.M(), shape.N()
    cells = {}
    for j in range(1, shape.coreNum + 1):
        for r in range(1, mr + 1):
            c = ix.decode(kind, shape, r, j, **kw)
            if c is None:
                continue
            if kind == ix.KIND_CAUSAL_SWIZZLE:
                n_new = n + 1 if m == n else (n - m + 2) + (n + 1)
                v = ix.Raw()
                ix.cal_dense_swizzle_index(shape.coreNum, m, n_new, shape.Bh() >> 1,
                                           j, r, v)
                if v.w:
                    cells[(v.s1 - 1, v.s2 - 1)] = (f"C{j} 第{r}轮", j - 1)
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
                cells[(vs1 - 1, vs2 - 1)] = (f"C{j} 第{r}轮", j - 1)
    return cells


def batch_mn(shape, kw, b):
    if "cu_q" in kw:
        lens = kw["cu_q"][b] - (0 if b == 0 else kw["cu_q"][b - 1])
        klen = kw["cu_k"][b] - (0 if b == 0 else kw["cu_k"][b - 1])
        return (lens + 127) // 128, (klen + 127) // 128
    return shape.M(), shape.N()


# ---------------------------------------------------------------- 页面

def draw_overview(prs):
    s = sd.blank_slide(prs)
    sd.title(s, "确定性梯度累加的 7 种任务索引", y=0.62)
    sd.text(s, 0.73, 1.22,
            "同一个问题：给定 (轮, 核)，这一轮这条核该算哪一块？七种规则给出七种分派方式。",
            w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    rows = []
    for name, kind, shape, mr, kw, causal in ix.cases():
        rows.append((ix.KIND_CN[kind],
                     f"k={shape.coreNum} m={shape.M()} n={shape.N()} b={shape.Bh()}"
                     + (f" g={shape.groupNum}" if shape.groupNum > 1 else ""),
                     "是" if shape.groupNum == 1 else "否",
                     str(mr)))
    sd.spec_table(s, 0.73, 1.72, ("规则", "本文例子", "列私有", "总轮数"), rows,
                  col_w=(4.20, 5.20, 2.20, 2.30), row_h=(0.55,) + (0.60,) * 7)
    sd.note(s, 0.73, 7.10, "所有规则都是纯算术：(轮, 核) 一确定，结果就唯一 —— 这就是确定性的来源。",
            w=15.2, h=0.36)
    sd.text(s, 0.73, 7.85, "怎么读后面的例子", w=13.0, h=0.34, size=18, bold=True)
    for i, line in enumerate([
            "· 算法页：先看伪代码讲清逻辑，再看任务矩阵（纵轴是轮，横轴是核）。",
            "· 例子页：网格的纵轴是 S1、横轴是 S2；格子颜色是核，格内文字是第几轮。",
            "· 灰格 = 本轮没有任务（空泡），或者要交给 mask 处理的块。",
            "· 每个方法后面都附一张对照表：同一形状下别的规则能不能用。"]):
        sd.text(s, 0.73, 8.35 + i * 0.42, line, w=13.0, h=0.36, size=16,
                color=sd.BODY_TEXT)
    sd.panel(s, 11.30, 7.85, "格子里写什么", ("记号", "含义"),
             [("B", "第几批"), ("N2", "第几个 KV 头"), ("G", "GQA 组里第几个 Q 头"),
              ("S1", "Q 方向第几块（128 行）"), ("S2", "KV 方向第几块（128 列）"),
              ("D", "头维，整块不切分")], col_w=(1.10, 3.55), row_h=0.42, size=13.0)
    return s


def draw_algo_page(prs, name, kind, shape, mr, kw, causal):
    meta = page_text(name, kind, shape, mr, kw)
    s = sd.blank_slide(prs)
    sd.title(s, meta["title"], y=0.62)
    sd.text(s, 0.73, 1.22, meta["sub"], w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    blk = sd.pseudocode_block(s, 0.73, 1.68, 9.6, meta["pseudo"])
    ty = 1.68 + sd.est_box(blk)[3] + 0.32

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
            cs.append({"lines": lines, "lane": j - 1})
        rows.append((f"第 {r} 轮", cs))
    col_w = min(4.4, (9.95 - 0.73 - 1.05) / max(1, shape.coreNum))
    sd.task_matrix(s, 0.73, ty, [f"C{j}" for j in range(1, shape.coreNum + 1)], rows,
                   col_w=col_w, row_h=MATRIX_ROW_H, lane_set=LANE_SET)
    matrix_bottom = ty + (mr + 1) * MATRIX_ROW_H

    # 左栏空白处补「每核负责的列」
    y_left = matrix_bottom + 0.45
    if y_left + 0.36 + 3 * 0.42 < 10.9 and mr <= 6:
        sd.panel(s, 0.73, y_left, "每个核负责哪些列", *lane_column_rows(kind, shape, mr, kw),
                 col_w=(0.95, 8.75), row_h=0.42, size=12.5)

    # 右栏：轴说明 + 代价数字 + 对照表
    yy = 1.68
    sd.text(s, RIGHT_X, yy, "格子里写什么", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate(AXIS_PANEL):
        sd.text(s, RIGHT_X, yy + 0.36 + i * 0.28, line, w=4.7, h=0.26, size=13,
                color=sd.BODY_TEXT)
    yy = yy + 0.36 + len(AXIS_PANEL) * 0.28 + 0.30
    yy = sd.panel(s, RIGHT_X, yy, "这个例子的数字", ("项", "值"),
                  numbers_rows(kind, shape, mr, kw), col_w=(3.20, 1.45), row_h=0.44,
                  size=13.0) + 0.30
    if shape.groupNum > 1 and "cu_q" in kw:
        sd.panel(s, RIGHT_X, yy, "换成按最长批对齐（示意）",
                 *tnd_compare_rows(shape, mr, kw), col_w=(1.60, 0.95, 2.10),
                 row_h=0.46, size=12.0)
    else:
        sd.panel(s, RIGHT_X, yy, "同一形状下其它规则能不能用",
                 *applicability_rows(kind, shape, mr), col_w=(1.40, 0.95, 2.30),
                 row_h=0.46, size=12.0)
    sd.note(s, 0.73, 11.20, meta["key"], w=9.70, h=0.52)
    return s


def draw_example_page(prs, name, kind, shape, mr, kw, causal):
    meta = page_text(name, kind, shape, mr, kw)
    s = sd.blank_slide(prs)
    sd.title(s, "例子：" + meta["title"], y=0.62)
    sd.text(s, 0.73, 1.22, meta["ex_sub"], w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)

    ts = ix.tasks_of(kind, shape, mr, **kw)
    n_max = max(batch_mn(shape, kw, b)[1] for b in range(shape.batch))
    cell = max(CELL_IN, min(0.95, 2.80 / (n_max + 1)))

    # ---- 左栏：真实网格流式排布 ----
    gx, gy, first, row_h = LEFTX, 3.05, True, 0.0
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
                         lane_set=LANE_SET, cell_in=cell)
            if first:
                sd.axis_arrow(s, gx - 0.68, gy, (m + 1) * cell - cell * 0.6, "down", "S1")
                sd.axis_arrow(s, gx, gy - 0.72, (n + 1) * cell - cell * 0.6, "right", "S2")
                first = False
            row_h = max(row_h, (m + 1) * cell)
            gx += gw + 1.35
    left_bottom = gy + row_h

    # ---- 图例：紧跟真实网格 ----
    ly = min(left_bottom + 0.35, 9.40)
    sd.text(s, LEFTX, ly, "颜色 = 核", w=1.6, h=0.30, size=14, bold=True)
    for i in range(shape.coreNum):
        col = sd.lane_colors(LANE_SET, shape.coreNum)[i]
        sd.block_grid(s, LEFTX + 1.10 + i * 0.86, ly - 0.05, [[col["fill"]]],
                      [[f"C{i + 1}"]], cell_w=0.72 * 914400, cell_h=0.40 * 914400,
                      label_size=13.0)
    sd.text(s, LEFTX + 1.10 + shape.coreNum * 0.86 + 0.30, ly,
            "格内文字 = 第几轮", w=5.6, h=0.30, size=14, color=sd.BODY_TEXT)
    left_bottom = ly + 0.45

    # ---- 因果页的虚拟矩形：宽的放左栏、窄的放右栏（否则左栏底部会不够高）----
    causal_kind = kind in (ix.KIND_CAUSAL_SWIZZLE, ix.KIND_LEFT_UP_CAUSAL)
    m0, n0 = shape.M(), shape.N()
    v_cols = n0 if m0 > n0 else n0 + 1
    v_rows = (2 * m0 - n0 + 1) if m0 > n0 else m0
    wide = (v_cols + 1) * 1.05 > 4.70
    v_cells = virtual_cells(kind, shape, mr, kw) if causal_kind else None

    if causal_kind and wide:
        # 虚拟矩形的标题画在表格上方 0.40，这里要额外让出这段高度
        left_bottom = _virtual_grid(s, LEFTX, left_bottom + 0.55, v_cols, v_rows,
                                    v_cells, lane_set=LANE_SET) + 0.35

    # ---- 右栏 ----
    r = ix.check(kind, shape, mr, **kw)
    priv = ("— 不适用" if shape.groupNum > 1
            else ("✓ 整列只归一条核" if r["column_private"] else "✗ 有重复"))
    props = ("这个例子为什么是确定的", ("性质", "本例情形"),
             [("任务不重复", "✓ 每个块只被派一次" if not r["dup"] else "✗ 有重复"),
              ("同一轮 S1 不撞", "✓ 各核的 S1 互不相同" if not r["dq_conflict"]
               else "✗ 有冲突"),
              ("每条核列私有", priv)])

    ry = 3.05
    if causal_kind and not wide:
        ry = _virtual_grid(s, 10.60, ry, v_cols, v_rows, v_cells,
                           lane_set=LANE_SET) + 0.45
    ry = sd.panel(s, 10.60, ry, "每个核负责哪些列",
                  *lane_column_rows(kind, shape, mr, kw),
                  col_w=(0.95, 4.30), row_h=0.44, size=12.5) + 0.45
    ry = sd.panel(s, 10.60, ry, "这个例子的数字", ("项", "值"),
                  numbers_rows(kind, shape, mr, kw), col_w=(3.20, 1.45), row_h=0.44,
                  size=13.0) + 0.45
    # "为什么确定"：优先补左栏空白；左栏放不下或虚拟矩形占了左栏就改放右栏；
    # 两边都放不下就干脆不放 —— 宁可少一张表，也不要压到底部注记
    props_h = 0.36 + 4 * 0.44
    if (not (causal_kind and wide)) and left_bottom + props_h <= 10.05:
        sd.panel(s, LEFTX, left_bottom, *props, col_w=(2.20, 2.45), row_h=0.44,
                 size=12.0)
    elif ry + props_h <= 11.85:
        sd.panel(s, 10.60, ry, *props, col_w=(2.20, 2.45), row_h=0.44, size=12.0)

    sd.note(s, 0.73, 10.15, meta["key"], w=9.70, h=0.52)
    for i, line in enumerate(meta["read"]):
        sd.text(s, 0.73, 10.82 + i * 0.42, "· " + line, w=9.70, h=0.36, size=16,
                color=sd.BODY_TEXT)
    return s


def _virtual_grid(slide, x, y, n_cols, n_rows, cells, lane_set=LANE_SET,
                  cell_w=1.05, cell_h=0.62):
    """虚拟矩形：行=虚拟S1、列=虚拟S2，格内写派给哪条核、第几轮。"""
    tbl = sd._plain_table(slide, x, y, n_rows + 1, n_cols + 1,
                          cell_w=int(cell_w * 914400), cell_h=int(cell_h * 914400))
    for i in range(n_cols + 1):
        tbl.columns[i].width = sd.Inches(cell_w)
    for i in range(n_rows + 1):
        tbl.rows[i].height = sd.Inches(cell_h)
    colors = sd.lane_colors(lane_set, 8)
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
                label, lane = got
                col = colors[lane % len(colors)]
                sd._fill_cell(cell, col["fill"])
                sd._write_cell_lines(cell, label.split(), size=11.0,
                                     colors=[col["text"]] * len(label.split()))
    sd.text(slide, x + 0.04, y - 0.40, "拼接后的虚拟矩形（行=虚拟S1，列=虚拟S2）",
            w=(n_cols + 1) * cell_w, h=0.30, size=14.0, bold=True)
    sd.arrow(slide, x + 0.10, y - 0.08, x + 0.10, y, width_pt=0.75, color=sd.BORDER)
    return y + (n_rows + 1) * cell_h          # 返回底边 y（含表头行）


def main(path):
    prs = sd.new_deck("4:3")
    draw_overview(prs)
    for name, kind, shape, mr, kw, causal in ix.cases():
        draw_algo_page(prs, name, kind, shape, mr, kw, causal)
        draw_example_page(prs, name, kind, shape, mr, kw, causal)
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
