#!/usr/bin/env python3
"""复杂表格 → PNG 图片渲染器（算子详设文档用图）。

Markdown 原生表格不支持合并单元格 / 多级表头 / 跨行跨列。本脚本把一张
JSON 规格的表格直出为 PNG，插入 .md 即可（不需要 pptx / LibreOffice）。

用法：
    python table_image.py spec.json [out.png]

spec 格式（字段均可选，给默认值）：
{
  "title":  "表标题（可空）",
  "col_w":  [1.6, 2.4, 4.0],            # 列宽（英寸）
  "header": [[{"t": "分支", "span": {"r": 2}},
              {"t": "条件", "span": {"r": 2}},
              {"t": "分支动作", "span": {"c": 2}}],
             [{"t": "动作 1"}, {"t": "动作 2"}]],
  "rows":   [[{"t": "分支①", "span": {"r": 2}}, {"t": "首块 && 尾块"},
              {"t": "Mul + Cast"}, {"t": "直写 dQGm"}],
             [{"t": "首块 && 未算完"}, {"t": "DataCopy"},
              {"t": "写 dQWorkSpaceGm"}]],
  "zebra":  true,                        # 隔行浅色（默认 true）
  "size":   11.0,                        # 正文字号（默认 11）
  "out":    "branch.png"                 # 也可由命令行第二参数覆盖
}

单元格字段：t = 文本（\n 手动换行；过长自动按列宽折行）；
span = {"r": n} 跨 n 行 / {"c": n} 跨 n 列；
fill = "RRGGBB" 自定义底色；color = "RRGGBB" 自定义字色；bold = true。

字体回退链：--font 指定 > ~/.seeten/fonts/NotoSansCJKsc-Regular.otf
（首次自动下载）> 系统 CJK 字体 > DejaVu Sans（无 CJK，会告警）。
"""
import json
import math
import os
import sys
import urllib.request

FONT_CACHE = os.path.expanduser("~/.seeten/fonts/NotoSansCJKsc-Regular.otf")
FONT_HEITI = os.path.expanduser("~/.seeten/fonts/HeiTi.ttf")
FONT_URL = ("https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/"
            "SimplifiedChinese/NotoSansCJKsc-Regular.otf")

HEAD_FILL = "DCE6F7"
ZEBRA_FILL = "F5F8FD"
BORDER = "9AA5B5"
TEXT = "1F2329"
TITLE_TEXT = "1F2329"


def find_font(arg=None):
    import matplotlib.font_manager as fm
    if arg:
        return fm.FontProperties(fname=arg)
    if os.path.exists(FONT_CACHE):
        return fm.FontProperties(fname=FONT_CACHE)
    if os.path.exists(FONT_HEITI):
        return fm.FontProperties(fname=FONT_HEITI)
    try:
        os.makedirs(os.path.dirname(FONT_CACHE), exist_ok=True)
        print(f"[table_image] downloading CJK font -> {FONT_CACHE}",
              file=sys.stderr)
        urllib.request.urlretrieve(FONT_URL, FONT_CACHE)
        return fm.FontProperties(fname=FONT_CACHE)
    except Exception as e:
        print(f"[table_image] WARN: CJK font download failed ({e}); "
              f"falling back to DejaVu (CJK will be missing!)", file=sys.stderr)
    for f in fm.fontManager.ttflist:
        if any(k in f.name for k in ("SC", "CJK", "Han", "WenQuan", "Noto Sans S")):
            return fm.FontProperties(fname=f.fname)
    return fm.FontProperties(family="DejaVu Sans")


def char_units(ch):
    """CJK 计 2 单位，其余计 1 —— 折行与行高估算用。"""
    o = ord(ch)
    return 2 if (0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x30FF or
                 0xFF00 <= o <= 0xFFEF) else 1


def wrap_text(text, max_units):
    """按列宽（换算成字符单位）折行；尊重已有 \n。

    折行点优先取空格 / 标点之后，避免在英文标识符中间断开
    （如 dQWorkSpaceGm 不应断成 dQWorkSpa ceGm）。
    """
    out = []
    for seg in text.split("\n"):
        line, units = [], 0
        for ch in seg:
            u = char_units(ch)
            if units + u > max_units and line:
                # 找最近的安全断点（空格或 -/_().,;:/ 之后）
                joined = "".join(line)
                cut = -1
                for i in range(len(joined) - 1, max(0, len(joined) - 12), -1):
                    if joined[i] in " \t" or joined[i] in "-_().,;:/+":
                        cut = i + 1
                        break
                if 0 < cut < len(joined):
                    out.append(joined[:cut])
                    rest = joined[cut:]
                    line, units = [rest], sum(char_units(c) for c in rest)
                else:
                    out.append(joined)
                    line, units = [], 0
            line.append(ch)
            units += u
        out.append("".join(line))
    return out or [""]


def layout(spec, font, size):
    """把 header+rows 铺到网格（处理跨行跨列），返回单元格几何与行列尺寸。"""
    col_w = spec.get("col_w") or [1.6] * max(
        len(spec.get("header", [[]])[0]), len(spec.get("rows", [[]])[0]))
    header = spec.get("header", [])
    body = spec.get("rows", [])
    n_cols = len(col_w)
    grid_rows = len(header) + len(body)

    # 占用矩阵：先放跨区，再逐格落位
    occ = [[None] * n_cols for _ in range(grid_rows)]
    cell_specs = []

    def place(r, c, spec_cell, is_head):
        while c < n_cols and occ[r][c] is not None:
            c += 1
        span = spec_cell.get("span", {})
        rs, cs = span.get("r", 1), span.get("c", 1)
        for dr in range(rs):
            for dc in range(cs):
                if r + dr < grid_rows and c + dc < n_cols:
                    occ[r + dr][c + dc] = (r, c)
        cell_specs.append(dict(r=r, c=c, rs=rs, cs=cs, head=is_head,
                               **{k: v for k, v in spec_cell.items() if k != "span"}))
        return c + cs

    for r, row in enumerate(header):
        c = 0
        for cell in row:
            c = place(r, c, cell, True)
    for r, row in enumerate(body):
        c = 0
        for cell in row:
            c = place(len(header) + r, c, cell, False)

    # 行高：每个单元格按列宽折行后取最大行数
    unit_w = size * 0.0105                        # 每字符单位 ≈ 英寸
    line_h = size * 0.0165 + 0.06                 # 行高（英寸）+ 内边距
    row_h = [0.0] * grid_rows
    cell_lines = {}
    for cs in cell_specs:
        w_in = sum(col_w[cs["c"]:cs["c"] + cs["cs"]]) - 0.16
        max_units = max(2, int(w_in / unit_w))
        lines = wrap_text(str(cs["t"]), max_units)
        cell_lines[(cs["r"], cs["c"])] = lines
        need = len(lines) * line_h + 0.10
        share = need / cs["rs"]
        for dr in range(cs["rs"]):
            row_h[cs["r"] + dr] = max(row_h[cs["r"] + dr], share)
    row_h = [max(h, line_h + 0.12) for h in row_h]
    return col_w, header, cell_specs, cell_lines, row_h


def render(spec, out_path, font_arg=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    size = float(spec.get("size", 11.0))
    font = find_font(font_arg)
    col_w, header, cell_specs, cell_lines, row_h = layout(spec, font, size)
    total_w = sum(col_w) + 0.30
    title_h = 0.42 if spec.get("title") else 0.0
    total_h = sum(row_h) + title_h + 0.24

    fig, ax = plt.subplots(figsize=(total_w, total_h), dpi=200)
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, total_h)
    ax.axis("off")
    x0, y_top = 0.15, total_h - 0.12

    if spec.get("title"):
        ax.text(x0, y_top - 0.08, str(spec["title"]), fontproperties=font,
                fontsize=size + 1.5, color="#" + TITLE_TEXT,
                ha="left", va="top", fontweight="bold")
    y0 = y_top - title_h

    n_head = len(header)
    ys = [y0]
    for h in row_h:
        ys.append(ys[-1] - h)
    xs = [x0]
    for w in col_w:
        xs.append(xs[-1] + w)

    # 单元格（跨区合并绘制）
    for cs in cell_specs:
        cx0 = xs[cs["c"]]
        cx1 = xs[cs["c"] + cs["cs"]]
        cy1 = ys[cs["r"]]
        cy0 = ys[cs["r"] + cs["rs"]]
        if cs.get("fill"):
            fill = "#" + cs["fill"].lstrip("#")
        elif cs["head"]:
            fill = "#" + HEAD_FILL
        elif spec.get("zebra", True) and (cs["r"] - n_head) % 2 == 0:
            fill = "#" + ZEBRA_FILL
        else:
            fill = "#FFFFFF"
        ax.add_patch(Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0,
                               facecolor=fill, edgecolor="#" + BORDER,
                               linewidth=0.8, zorder=2))
        lines = cell_lines[(cs["r"], cs["c"])]
        color = "#" + cs.get("color", TEXT).lstrip("#")
        bold = cs.get("bold") or cs["head"]
        lh = (cy1 - cy0) / (len(lines) + 0.4)
        for i, ln in enumerate(lines):
            ax.text(cx0 + 0.08, cy1 - lh * (i + 0.72), ln,
                    fontproperties=font, fontsize=size, color=color,
                    ha="left", va="center",
                    fontweight="bold" if bold else "normal", zorder=3)

    fig.savefig(out_path, dpi=200, bbox_inches="tight",
                facecolor="white", pad_inches=0.02)
    plt.close(fig)
    return out_path


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    out = (sys.argv[2] if len(sys.argv) > 2 else spec.get("out") or
           os.path.splitext(sys.argv[1])[0] + ".png")
    font_arg = spec.get("font")
    render(spec, out, font_arg)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
