"""用 SeeTen 生成库画本案例的页面。

    python draw_case.py out/case.pptx

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
MATRIX_ROW_H = 0.50


def _cells(ts, shape, row_key="S1"):
    """把 (轮, 核) 任务表转成 task_matrix 用的行。"""
    rounds = max(r for (_, r) in ts)
    rows = []
    for r in range(1, rounds + 1):
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
    return rows


def draw_algo_page(prs, title, subtitle, pseudo, shape, kind, max_round, kw):
    s = sd.blank_slide(prs)
    sd.title(s, title, y=0.62)
    sd.text(s, 0.73, 1.22, subtitle, w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    blk = sd.pseudocode_block(s, 0.73, 1.68, 9.6, pseudo)
    ty = 1.68 + sd.est_box(blk)[3] + 0.32
    ts = ix.tasks_of(kind, shape, max_round, **kw)
    rows = _cells(ts, shape)
    col_w = min(4.4, (9.95 - 0.73 - 1.05) / max(1, shape.coreNum))
    sd.task_matrix(s, 0.73, ty, [f"C{j}" for j in range(1, shape.coreNum + 1)],
                   rows, col_w=col_w, row_h=MATRIX_ROW_H, lane_set=LANE_SET)
    # 右栏：轴说明 + 代价数字（把空白填满）
    sd.text(s, 11.30, 1.68, "格子里写什么", w=4.7, h=0.30, size=15, bold=True)
    for i, line in enumerate(["B  = 第几批", "N2 = 第几个 KV 头", "G  = 组里第几个 Q 头",
                              "S1 = Q 方向第几块（每块 128 行）",
                              "S2 = KV 方向第几块（每块 128 列）",
                              "D  = 头维，整块不切分"]):
        sd.text(s, 11.30, 2.04 + i * 0.28, line, w=4.7, h=0.26, size=13,
                color=sd.BODY_TEXT)
    r = ix.check(kind, shape, max_round, **kw)
    sd.panel(s, 11.30, 4.00, "这个例子的数字", ("项", "值"),
             (("任务总数", r["valid"]), ("总槽位（核 x 轮）", r["slots"]),
              ("空泡 / 无任务", r["holes"]),
              ("每核独占的列数", sum(len(v) for v in r["cols_per_lane"].values())
               // max(1, shape.coreNum))),
             col_w=(3.20, 1.45), row_h=0.44, size=13.0)
    prop = [("任务不重复", "✓ 每个块只被派一次" if not r["dup"] else "✗ 有重复"),
            ("同一轮 S1 不撞", "✓ 各核的 S1 互不相同" if not r["dq_conflict"] else "✗ 有冲突"),
            ("每条核列私有", "✓ 整列只归一条核" if r["column_private"] else "— 不适用")]
    sd.panel(s, 11.30, 6.90, "这个例子为什么是确定的", ("性质", "本例情形"), prop,
             col_w=(2.20, 2.45), row_h=0.46, size=12.0)
    sd.note(s, 0.73, 10.35, "顺序固定 —— 这就是确定性的来源。", w=15.2, h=0.36)
    return s


def draw_grid_page(prs, title, subtitle, shape, kind, max_round, kw, head=None):
    s = sd.blank_slide(prs)
    sd.title(s, title, y=0.62)
    sd.text(s, 0.73, 1.22, subtitle, w=15.2, h=0.30, size=16, color=sd.BODY_TEXT)
    ts = ix.tasks_of(kind, shape, max_round, **kw)
    gx, gy, cell = 2.10, 3.05, 0.80
    for b in range(shape.batch):
        cells = {}
        for (j, r), c in ts.items():
            if c is None or c.batch != b:
                continue
            cells[(c.s1, c.s2)] = (f"第{r}轮", j - 1)
        m, n = shape.M(), shape.N()
        sd.axis_grid(s, gx, gy, m, n, cells, caption=f"B={b + 1}", lane_set=LANE_SET,
                     cell_in=cell)
        gx += (n + 1) * cell + 1.6
    n = shape.N()
    sd.axis_arrow(s, 1.42, gy, (shape.M() + 1) * cell - cell * 0.6, "down", "S1")
    sd.axis_arrow(s, 2.10, gy - 0.72, (n + 1) * cell - cell * 0.6, "right", "S2")
    sd.text(s, 2.10, gy + (shape.M() + 1) * cell + 0.30,
            "格内 = 第几轮执行，颜色 = 哪个核，灰格 = 本轮该核空闲",
            w=7.6, h=0.30, size=14, color=sd.BODY_TEXT)
    r = ix.check(kind, shape, max_round, **kw)
    rows = []
    for j in sorted(r["cols_per_lane"]):
        cols = r["cols_per_lane"][j]
        rows.append((f"C{j}", "  ".join(f"B={a} S2={b}" for a, b in cols) or "（无）"))
    sd.panel(s, 10.60, 3.05, "每个核负责哪些列", ("核", "负责的 (B, S2) 列"),
             rows, col_w=(0.95, 4.30), row_h=0.44, size=12.5)
    sd.note(s, 0.73, 10.35, "一条核在 m 轮里守着同一条列 —— dK/dV 因此是单核顺序累加。",
            w=15.2, h=0.36)
    return s


def main(path):
    prs = sd.new_deck("4:3")
    shape = ix.Shape(batch=2, qSeqLen=384, kvSeqLen=384, qHeadNum=1, kvHeadNum=1,
                     coreNum=2)
    draw_algo_page(
        prs, "列私有 swizzle：一条核包下一条 KV 列",
        "输入：核数 2 · S1 分 3 块 · S2 分 3 块 · 批次 2",
        ["核数 k=2, S1 块数 m=3, S2 块数 n=3, 批数 b=2",
         "对每个 (轮 r, 核 j):",
         "    任务号 = ((r-1) / m) * k + (j-1)     # 每 m 轮换一次任务号",
         "    第几列 = 任务号 % n + 1               # 低位先走 S2 列轴",
         "    第几批 = 任务号 / n + 1               # 列走完才换批",
         "    第几行 = (第几列-1 + r-1) % m + 1     # 同一列内 S1 每轮转一格",
         "    输出: B, N2, G, S1=第几行, S2=第几列"],
        shape, ix.KIND_DENSE_SWIZZLE, 9, {})
    draw_grid_page(
        prs, "例子：列私有 swizzle",
        "把任务矩阵摊到 S1×S2 平面上：纵轴 S1、横轴 S2，颜色是核，格内是第几轮",
        shape, ix.KIND_DENSE_SWIZZLE, 9, {})
    sd.save(prs, path)
    errors, warns = sd.check_layout(prs)
    print(f"wrote {path}")
    print(f"版心检查: {len(errors)} 越界 / {len(warns)} 重叠")
    for e in errors[:8]:
        print("  !", e)
    for w in warns[:8]:
        print("  ~", w)
    return len(errors)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/case.pptx"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sys.exit(1 if main(out) else 0)
