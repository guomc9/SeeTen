"""SeeTen —— 张量表格绘制库（python-pptx）。

把"分块 + 核 + 轮次"这类并行方案画成 PPT 页面：
原生 PPT 表格的每个单元格 = 一个分块，填充色编码语义，块号/坐标写进格子，
轴标签/核名/操作名用文本框，数据流用带箭头的直线连接线，逻辑用伪代码块先讲清。

实测参数见 ../references/style-spec.md，色板见 ../assets/*.json。

用法：
    from seeten_draw import *
    prs = new_deck("4:3")            # 画布比例先定，之后不改
    s = blank_slide(prs)
    title(s, "分块与轮次")
    block_grid(s, 1.0, 3.0, fills, labels)          # 块网格
    task_matrix(s, 0.73, 6.0, cores, rows)          # 轮 x 核
    save(prs, "out.pptx")
    print(check_layout(prs))         # 收尾必须 0 越界 0 重叠

    python seeten_draw.py examples/demo.pptx   # 生成通用演示 deck
"""

from __future__ import annotations

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# ---------------------------------------------------------------- 色板 / 常量

TITLE_TEXT = "1F2329"
BODY_TEXT = "333333"
STRONG_TEXT = "000000"
ON_BLOCK = "FFFFFF"
ZEBRA_FILL = "F7F8FA"     # 全白表格的隔行底色：白/灰相间，行与行更分明

GROUP0, GROUP1, GROUP2 = "3370FF", "82A7FC", "E1EAFF"   # 分组色 0/1/2
A_LIGHT, A_DARK = "AD82F7", "6425D0"                    # 操作数 A（浅/深）
B_LIGHT, B_DARK = "F98E8B", "D83931"                    # 操作数 B（浅/深）
ACC_BLUE = "3370FF"                                     # 累加器 / 工作区
VECTOR_ORANGE = "FFBA6B"
# 旧名字保留成别名，避免调用方改代码
Q_LIGHT, Q_DARK = A_LIGHT, A_DARK
DS_LIGHT, DS_DARK = B_LIGHT, B_DARK
L0C_BLUE = ACC_BLUE
TINT_RED = "FDE2E2"

BORDER = "DDDEDF"
CONNECTOR = "2B2F36"

LATIN = "Times New Roman"
CJK = "Noto Sans SC"
BODY_STACK = "Helvetica Neue, Helvetica, Segoe UI, Arial, freesans, sans-serif"

CELL_W = 612885          # EMU，0.670 in
CELL_H = 603250          # EMU，0.660 in
MARGIN = 101600          # EMU，8 pt

SLIDE_W, SLIDE_H = 15240000, 11430000   # 1200 × 900 pt，= 画布预设 "4:3"

# 画布预设：比例选定后就不再改；所有文字和表格必须落在版心内（check_layout 强制）
CANVAS_PRESETS = {
    "4:3":   (15240000, 11430000),   # 16.67 x 12.5 in = 1200 x 900 pt（默认）
    "16:9":  (12192000, 6858000),    # 13.33 x 7.5 in
    "16:10": (14630400, 9144000),    # 16 x 10 in
}
CONTENT_MARGIN = 0.60            # 英寸：四边留白，越过即为排版错误

LAYOUT_ISSUES: list = []         # check_layout() 收集的问题


def _geom(shp):
    return (Emu(shp.left).inches, Emu(shp.top).inches,
            Emu(shp.width).inches, Emu(shp.height).inches)


def est_box(shp):
    """shape 的外框（英寸）。文字按内容宽度估算，表格/图形用自身几何。"""
    l, t, w, h = _geom(shp)
    if not shp.has_text_frame:
        return (l, t, w, h)
    xs = [e[0] for e in _text_extents(shp)]
    if not xs:
        return (l, t, w, h)
    right = max(e[0] + e[2] for e in _text_extents(shp))
    return (min(xs), t, max(0.05, right - min(xs)), h)


def _text_extents(shp):
    """逐段落估算实际文字占位 (x, y, w, h)：按字号和对齐算，不靠注册表。

    python-pptx 每次遍历都会重建 shape 代理，所以只能现算。
    换行后的行数先算完，再按 anchor 定位 —— 否则自动换行的文本会被少算高度。
    """
    tf = shp.text_frame
    l, t, w, h = _geom(shp)
    wrap = tf.word_wrap is True
    ml = Emu(tf.margin_left).inches if tf.margin_left is not None else 0.1
    mr = Emu(tf.margin_right).inches if tf.margin_right is not None else 0.1
    avail = max(0.3, w - ml - mr)
    items = []
    for p in tf.paragraphs:
        body = "".join(r.text for r in p.runs)
        size = max((r.font.size.pt for r in p.runs if r.font.size is not None),
                   default=18.0)
        mono = any((r.font.name or "").lower() in
                   ("consolas", "courier new", "monospace") for r in p.runs)
        line_h = max(size * 1.30 / 72.0, 0.16)
        ew = est_text_width(body, size, mono=mono) if body.strip() else 0.0
        if wrap and body.strip():
            # 自动换行的文本框：宽度不可能超出可用宽度，行数按估算宽度折算
            line_h *= max(1, int(ew / avail) + (1 if ew % avail else 0))
            ew = min(ew, avail)
        items.append((ew, line_h, p.alignment))
    total = sum(it[1] for it in items)
    anchor = tf.vertical_anchor
    if anchor == MSO_ANCHOR.MIDDLE:
        y = t + (h - total) / 2.0
    elif anchor == MSO_ANCHOR.BOTTOM:
        y = t + h - total
    else:
        y = t
    out = []
    for ew, line_h, al in items:
        if al == PP_ALIGN.CENTER:
            x0 = l + (w - ew) / 2.0
        elif al == PP_ALIGN.RIGHT:
            x0 = l + w - ew
        else:
            x0 = l
        out.append((x0, y, ew, line_h))
        y += line_h
    return out


# ---------------------------------------------------------------- 基础工具

def new_deck(preset: str = "4:3") -> Presentation:
    """按预设比例建空白 deck（白底）。比例一旦确定就不要中途改。"""
    prs = Presentation()
    w, h = CANVAS_PRESETS[preset]
    prs.slide_width, prs.slide_height = Emu(w), Emu(h)
    prs._seeten_preset = preset
    return prs


def content_box(prs):
    """版心 (left, top, right, bottom)，单位英寸。"""
    return (CONTENT_MARGIN, CONTENT_MARGIN,
            Emu(prs.slide_width).inches - CONTENT_MARGIN,
            Emu(prs.slide_height).inches - CONTENT_MARGIN)


# 文本宽度估算（em 系数）：只用于"会不会溢出"的守门，不当作排版器
def est_text_width(body: str, size_pt: float, mono: bool = False) -> float:
    if mono:
        return len(body) * 0.60 * size_pt / 72.0
    em = 0.0
    for ch in body:
        if ord(ch) > 0x2E7F:
            em += 1.0                      # 全角/CJK
        elif ch == " ":
            em += 0.28
        elif ch.isdigit():
            em += 0.50
        elif ch in "MW":
            em += 0.92                     # TNR 最宽的大写
        elif ch.isupper():
            em += 0.70                     # TNR 大写均值（原 0.62 明显低估，
                                           # 导致 MHA/GQA 这类表头被算窄而裁字）
        elif ch.islower():
            em += 0.48
        elif ch == "/":
            em += 0.28
        else:
            em += 0.34
    return em * size_pt / 72.0


def blank_slide(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr.lstrip("#").upper())


def _set_cjk_font(run, typeface: str) -> None:
    """补 a:ea / a:cs，保证中文字形也用指定字体（顺序 latin → ea → cs）。"""
    rPr = run._r.get_or_add_rPr()
    latin = rPr.find(qn("a:latin"))
    pos = (list(rPr).index(latin) + 1) if latin is not None else len(rPr)
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = etree.Element(qn(tag))
            rPr.insert(pos, el)
            pos += 1
        el.set("typeface", typeface)


def _style_run(run, size=None, bold=None, color=None, font=None, cjk_font=None) -> None:
    f = run.font
    if font:
        f.name = font
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if color:
        f.color.rgb = _rgb(color)
    if cjk_font:
        _set_cjk_font(run, cjk_font)


def _split_scripts(text: str):
    """把文本切成 (片段, 是否 CJK) 序列 —— 中英混排要分 run 设字体。"""
    out, buf, cur_cjk = [], "", None
    for ch in text:
        is_cjk = ord(ch) > 0x2E7F
        if cur_cjk is None or is_cjk == cur_cjk:
            buf += ch
            cur_cjk = is_cjk
        else:
            out.append((buf, cur_cjk))
            buf, cur_cjk = ch, is_cjk
    if buf:
        out.append((buf, cur_cjk))
    return out


EMPH_COLOR = "D83931"      # 行内强调（`==…==`）默认用的颜色


def _rich_segments(body: str, bold, color):
    """把 `**粗**` / `==强调==` 解析成 (文本, 是否粗, 颜色) 片段，其余原样。

    页面上不会出现星号或等号 —— 它们是**输入**的标记，不是要渲染的内容。
    """
    out, buf, i = [], "", 0
    while i < len(body):
        if body.startswith("**", i):
            j = body.find("**", i + 2)
            if j > 0:
                if buf:
                    out.append((buf, bold, color)); buf = ""
                out.append((body[i + 2:j], True, color))
                i = j + 2
                continue
        if body.startswith("==", i):
            j = body.find("==", i + 2)
            if j > 0:
                if buf:
                    out.append((buf, bold, color)); buf = ""
                out.append((body[i + 2:j], True, EMPH_COLOR))
                i = j + 2
                continue
        buf += body[i]
        i += 1
    if buf:
        out.append((buf, bold, color))
    return out


def text(slide, x, y, body: str, w=4.0, h=0.42, size=20.0, bold=False,
         color=TITLE_TEXT, font=LATIN, cjk_font=CJK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.MIDDLE, mixed_scripts=True, wrap=False, mono=False):
    """通用标签文本框（无填充、无边框），坐标单位英寸。

    建好后把估算外框记在 shape 上，check_layout() 用它判断有没有越界。
    body 里可以写 `**重点**`（加粗）和 `==要点==`（换成强调色）做行内强调 ——
    字面上的星号/等号不会渲染出来。
    """
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    plain = body.replace("**", "").replace("==", "")       # 估宽按去掉标记的文本算
    for seg, seg_bold, seg_color in _rich_segments(body, bold, color):
        for piece, is_cjk in (_split_scripts(seg) if (mixed_scripts and font == LATIN
                                                       and cjk_font) else [(seg, False)]):
            run = p.add_run()
            run.text = piece
            _style_run(run, size=size, bold=seg_bold, color=seg_color,
                       font=(cjk_font if (is_cjk and cjk_font) else font),
                       cjk_font=cjk_font)
    lines = plain.split("\n")
    est_w = max(est_text_width(ln, size, mono=mono) for ln in lines)
    if wrap:
        est_w = min(est_w, w)
    est_x = x
    if align == PP_ALIGN.CENTER:
        est_x = x + (w - est_w) / 2.0
    elif align == PP_ALIGN.RIGHT:
        est_x = x + w - est_w
    return box


def title(slide, body: str, x=0.73, y=0.62, size=30.0, w=13.5):
    """页面主题标题：30 pt bold，中英分 run。

    框高收到 0.55，文字居中后顶端落在 y≈0.62，正好压住版心上边线。
    """
    return text(slide, x, y, body, w=w, h=0.55, size=size, bold=True, color=TITLE_TEXT)


def note(slide, x, y, body: str, w=12.0, h=0.42, size=18.0):
    """图注长句：TNR 18 bold #F98E8B。默认换行，避免长句横穿到隔壁栏。"""
    return text(slide, x, y, body, w=w, h=h, size=size, bold=True, color=DS_LIGHT,
                wrap=True)


def arrow(slide, x1, y1, x2, y2, color=CONNECTOR, width_pt=1.0):
    """带三角箭头的直线连接线。"""
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = _rgb(color)
    conn.line.width = Pt(width_pt)
    ln = conn.line._get_or_add_ln()
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
    return conn


# ---------------------------------------------------------------- 表格底座

def _plain_table(slide, x, y, rows, cols, cell_w=CELL_W, cell_h=CELL_H):
    """建一张"无表样式"表格并返回 pptx table 对象。"""
    total_w = Emu(cell_w) * cols
    total_h = Emu(cell_h) * rows
    gf = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), total_w, total_h)
    tbl = gf.table
    # 去掉 tableStyleId 与首行/镶边标志，表格才是"无表样式"的干净底
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow", "firstCol", "lastRow", "lastCol", "bandCol"):
        if attr in tblPr.attrib:
            del tblPr.attrib[attr]
    for child in list(tblPr):
        if child.tag == qn("a:tableStyleId"):
            tblPr.remove(child)
    for i in range(cols):
        tbl.columns[i].width = Emu(cell_w)
    for i in range(rows):
        tbl.rows[i].height = Emu(cell_h)
    return tbl


def _cell_border(cell, color=BORDER, width_pt=1.0) -> None:
    """四边 1 pt #DDDEDF（python-pptx 不暴露边框，写 XML）。"""
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("lnL", "lnR", "lnT", "lnB"):
        for el in tcPr.findall(qn("a:" + tag)):
            tcPr.remove(el)
    for tag in ("lnB", "lnT", "lnR", "lnL"):          # 倒序 insert → 最终 lnL,lnR,lnT,lnB
        ln = etree.Element(qn("a:" + tag))
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        ln.set("cap", "flat")
        ln.set("w", str(int(width_pt * 12700)))
        fill = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(fill, qn("a:srgbClr"))
        clr.set("val", color.upper())
        dash = etree.SubElement(ln, qn("a:prstDash"))
        dash.set("val", "solid")
        etree.SubElement(ln, qn("a:round"))
        tcPr.insert(0, ln)


def table_extent(tbl):
    """表格的真实外框：列宽之和 x 行高之和（graphicFrame 的 ext 不一定同步）。"""
    w = sum(Emu(c.width).inches for c in tbl.columns)
    h = sum(Emu(r.height).inches for r in tbl.rows)
    return w, h


def fit_table(tbl):
    """把 graphicFrame 的 ext 改成真实外框，避免表框和内容对不上。"""
    w, h = table_extent(tbl)
    gf = tbl._graphic_frame
    gf.width = Inches(w)
    gf.height = Inches(h)
    return tbl


def _fill_cell(cell, fill: str | None) -> None:
    if fill:
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(fill)
    else:
        cell.fill.background()


def text_on(fill: str) -> str:
    """按底色亮度选文字色：浅底配深字、深底配白字，避免"浅底压白字"看不清。"""
    f = (fill or "").lstrip("#")
    if len(f) != 6:
        return ON_BLOCK
    r, g, b = (int(f[i:i + 2], 16) for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return TITLE_TEXT if lum > 150 else ON_BLOCK


def _write_cell(cell, body: str, size=17.5, bold=True, color=ON_BLOCK,
                font=LATIN, cjk_font=CJK, margin=None) -> None:
    margin = MARGIN if margin is None else margin
    tf = cell.text_frame
    tf.word_wrap = False
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Emu(int(margin))
    cell.margin_right = Emu(int(margin))   # 左右对称：文字离右边线同样留白
    cell.margin_top = Emu(int(margin))
    cell.margin_bottom = Emu(int(margin))
    lines = body.split("\n")            # 允许格内两行（"S1=2" / "S2=3"）
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        for seg, is_cjk in _split_scripts(ln):
            run = p.add_run()
            run.text = seg
            _style_run(run, size=size, bold=bold, color=color,
                       font=(cjk_font if is_cjk else font), cjk_font=cjk_font)


# ---------------------------------------------------------------- 六种表式

def block_grid(slide, x, y, fills, labels=None, cell_w=CELL_W, cell_h=CELL_H,
               label_size=17.5, label_color=None, border=True):
    """块网格（张量画布）。fills/labels 均为 rows×cols 的二维序列，None = 留白。"""
    rows, cols = len(fills), len(fills[0])
    tbl = _plain_table(slide, x, y, rows, cols, cell_w, cell_h)
    for r in range(rows):
        for c in range(cols):
            cell = tbl.cell(r, c)
            _fill_cell(cell, fills[r][c])
            if border:
                _cell_border(cell)
            lab = labels[r][c] if labels else None
            if lab:
                # 没显式指定就用"按底色自动选"的文字色
                col = label_color or text_on(fills[r][c])
                _write_cell(cell, lab, size=label_size, color=col)
    return fit_table(tbl)


def tensor_block(slide, x, y, label, color, cols=6, rows=2,
                 cell_w=CELL_W, cell_h=CELL_H, label_top_only=False):
    """单个张量分块补丁（默认 2 列×2 行，每格都写块号）。"""
    fills = [[color] * cols for _ in range(rows)]
    labels = None
    if label:
        labels = [[label] * cols for _ in range(rows)]
        if label_top_only and rows > 1:
            labels = [labels[0]] + [[""] * cols for _ in range(rows - 1)]
    return block_grid(slide, x, y, fills, labels, cell_w, cell_h)


def spec_table(slide, x, y, header, rows, col_w=(1.30, 1.26, 1.33, 5.09),
               row_h=(0.80, 0.878, 0.556, 0.556, 0.556, 0.556), zebra=True):
    """张量参数表：张量 | 形状 | 案例 shape | 说明。zebra 规则同 panel。"""
    tbl = _plain_table(slide, x, y, len(rows) + 1, len(header),
                       cell_w=col_w[0], cell_h=int(row_h[0] * 914400))
    for i, w in enumerate(col_w):
        tbl.columns[i].width = Inches(w)
    for i, h in enumerate(row_h[: len(rows) + 1]):
        tbl.rows[i].height = Inches(h)
    for c, head in enumerate(header):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _write_cell(cell, head, size=15.5, bold=False,
                    color=(STRONG_TEXT if c == 0 else TITLE_TEXT), cjk_font=CJK)
    for r, row in enumerate(rows, start=1):
        band = ZEBRA_FILL if (zebra and r % 2 == 1) else None
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            if band:
                _fill_cell(cell, band)
            _write_cell(cell, val, size=15.5, bold=False, color=TITLE_TEXT)
    return tbl


def round_table(slide, x, y, header=("核/轮", "C0", "C1", "C2", "C3"),
                rows=(("T0", "B0", "B1", "B2", "B3"), ("T1", "B4", "B5", "", "")),
                col_w=1.29, row_h=(0.881, 0.597, 0.597)):
    """核/轮分配表。"""
    tbl = _plain_table(slide, x, y, len(rows) + 1, len(header),
                       cell_w=int(col_w * 914400), cell_h=int(row_h[0] * 914400))
    for i in range(len(header)):
        tbl.columns[i].width = Inches(col_w)
    for i, h in enumerate(row_h):
        tbl.rows[i].height = Inches(h)
    for c, head in enumerate(header):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK if c else None)
        _write_cell(cell, head, size=17.5, bold=False, color=TITLE_TEXT,
                    cjk_font=CJK)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            _write_cell(cell, val, size=17.5, bold=False, color=TITLE_TEXT)
    return tbl


def accum_table(slide, x, y, header, rows, col_w=1.29,
                row_h=(0.881, 0.597, 0.597, 0.597, 0.597, 0.597, 0.597)):
    """累加块表：索引列跨行合并且续行留空（rows 里用 None 表示续行）。"""
    tbl = _plain_table(slide, x, y, len(rows) + 1, len(header),
                       cell_w=int(col_w * 914400), cell_h=int(row_h[0] * 914400))
    for i in range(len(header)):
        tbl.columns[i].width = Inches(col_w)
    for i, h in enumerate(row_h[: len(rows) + 1]):
        tbl.rows[i].height = Inches(h)
    for c, head in enumerate(header):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK if c else None)
        _write_cell(cell, head, size=17.5, bold=False, color=TITLE_TEXT, cjk_font=CJK)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            _write_cell(cell, val or "", size=17.5, bold=False, color=TITLE_TEXT)
    return tbl


def gantt_table(slide, x, y, col_w, rows, row_h=(0.5, 0.5, 0.597, 0.597),
                highlights=None):
    """流水重叠甘特表。highlights = {(row, col)} 刷 #FDE2E2。"""
    highlights = highlights or set()
    cols = len(col_w)
    tbl = _plain_table(slide, x, y, len(rows), cols,
                       cell_w=int(col_w[0] * 914400), cell_h=int(row_h[0] * 914400))
    for i, w in enumerate(col_w):
        tbl.columns[i].width = Inches(w)
    for i, h in enumerate(row_h[: len(rows)]):
        tbl.rows[i].height = Inches(h)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            if (r, c) in highlights:
                _fill_cell(cell, TINT_RED)
            _write_cell(cell, val or "", size=13.3, bold=(c == 0), color=TITLE_TEXT,
                        font=CJK, cjk_font=CJK)
    return tbl


def fit_all_tables(prs: Presentation) -> int:
    n = 0
    for slide in prs.slides:
        for shp in slide.shapes:
            if getattr(shp, "has_table", False) and shp.has_table:
                fit_table(shp.table)
                n += 1
    return n


def save(prs: Presentation, path: str) -> str:
    fit_all_tables(prs)          # 统一把表框对齐到真实列宽/行高
    prs.save(path)
    return path


# ------------------------------------------------------- 调度图专用构件
# 规则：轮数是纵轴、核数是横轴；格内写清楚是哪个轴的哪个索引；
#      解释文字一律放表格外面，不挤占表格排布。

import json as _json
import os as _os
import re as _re

_ASSETS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "assets")

_CODE = {"bg": "F5F5F5", "border": "D6D6D6", "text": "333333",
         "keyword": "0086B3", "comment": "969896", "font": "Consolas"}
_HOLE = {"fill": "F2F3F5", "text": "1F2329"}
_LANE_SETS = {}


def _load_color_sets():
    global _LANE_SETS, _CODE, _HOLE
    if _LANE_SETS:
        return
    try:
        with open(_os.path.join(_ASSETS, "color-sets.json"), encoding="utf-8") as f:
            data = _json.load(f)
        _LANE_SETS = data.get("lane_sets", {})
        _CODE.update(data.get("pseudocode", {}))
        _HOLE.update(data.get("hole", {}))
    except OSError:
        _LANE_SETS = {"cool": {"colors": [{"fill": "4E7CF0", "text": "FFFFFF"}]}}


def lane_colors(set_name: str, n: int):
    """lane 配色预设 → n 个 {fill, text}（不够就循环）。"""
    _load_color_sets()
    base = _LANE_SETS.get(set_name, _LANE_SETS.get("cool"))
    cols = (base or {}).get("colors") or [{"fill": "4E7CF0", "text": "FFFFFF"}]
    return [cols[i % len(cols)] for i in range(n)]


def hole_color():
    _load_color_sets()
    return dict(_HOLE)


def lane_shades(set_name: str, lane: int, n: int, lo=0.30, hi=0.62):
    """同一个核的 n 个任务用**同一种颜色的深浅**区分（颜色 = 哪条 lane，颜色深浅 = 第几个任务）。

    只靠只用颜色区分 lane 时，同一条 lane 的多个任务长得一样，看不出先后；
    叠一层明度梯度后，既能认出是哪个核，也能看出它在轮次上的推进。
    """
    import colorsys
    _load_color_sets()
    base = lane_colors(set_name, lane + 1)[lane]["fill"].lstrip("#")
    r, g, b = (int(base[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    out = []
    for i in range(max(1, n)):
        t = (i / (n - 1)) if n > 1 else 0.5
        rr, gg, bb = colorsys.hls_to_rgb(h, lo + (hi - lo) * t, s)
        fill = "%02X%02X%02X" % (round(rr * 255), round(gg * 255), round(bb * 255))
        out.append({"fill": fill, "text": text_on(fill)})
    return out


def tag_row(slide, x, y, tags, size=13.0, pad=0.16, gap=0.14, h=0.34,
            bg="EEF2FF", border="C9D6F5"):
    """一行标签芯片（如 layout / causal / MHA），用来标清这条规则适用的场景。

    tags: [(标签, 值), ...]；标签为空串时只画值（如 `("", "MHA")`）。返回右端 x。
    """
    from pptx.enum.shapes import MSO_SHAPE
    cur = x
    for label, value in tags:
        body = f"{label} {value}" if label else str(value)
        # 估宽之外再留 0.10 in 安全边距：芯片内边距吃掉两头后仍不贴边，
        # 否则部分渲染器会把 "MHA" 这种短词也挤成换行
        w = est_text_width(body, size) + pad * 2 + 0.10
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(cur),
                                     Inches(y), Inches(w), Inches(h))
        box.adjustments[0] = 0.25
        box.fill.solid()
        box.fill.fore_color.rgb = _rgb(bg)
        box.line.color.rgb = _rgb(border)
        box.line.width = Pt(0.75)
        try:
            box.shadow.inherit = False
        except Exception:
            pass
        tf = box.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(pad)
        tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = body
        _style_run(run, size=size, bold=False, color=TITLE_TEXT, font=LATIN,
                   cjk_font=CJK)
        cur += w + gap
    return cur


def _write_cell_lines(cell, lines, size=11.0, colors=None, font=LATIN,
                      cjk_font=CJK, line_gap=0.9, margin=None):
    """单元格多行文本：每行一个段落，可逐行指定颜色。

    行内也能用 `**粗**` / `==强调==`（见 `_rich_segments`），字面标记不会画出来。
    """
    tf = cell.text_frame
    tf.word_wrap = False
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    margin = MARGIN if margin is None else margin
    cell.margin_left = Emu(int(margin))
    cell.margin_right = Emu(int(margin))   # 左右对称：文字离右边线同样留白
    cell.margin_top = Emu(40640)           # 3.2 pt，给两行留出呼吸
    cell.margin_bottom = Emu(40640)
    for i, body in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        p.line_spacing = line_gap
        col = (colors[i] if colors else None) or ON_BLOCK
        for seg, seg_bold, seg_color in _rich_segments(body, False, col):
            for piece, is_cjk in _split_scripts(seg):
                run = p.add_run()
                run.text = piece
                _style_run(run, size=size, bold=seg_bold, color=seg_color,
                           font=(cjk_font if is_cjk else font), cjk_font=cjk_font)


def task_matrix(slide, x, y, core_labels, rows, col_w=4.2, row_h=0.52,
                first_col_w=1.15, lane_set="cool", cell_size=11.0,
                shade_count=None):
    """任务矩阵：**行 = 轮次，列 = 核**。

    rows: [(轮标签, [cell, ...]), ...]；cell 为 None 表示空洞，或
          {"lines": [...], "lane": 0, "shade": 0}
    格内写的是"哪个轴的哪个索引"，不是裸数字。
    shade_count 给了就按"同同色深浅"上色：颜色 = 哪条 lane，颜色深浅 = 第几个任务。
    """
    colors = lane_colors(lane_set, len(core_labels))
    shades = ([lane_shades(lane_set, i, shade_count) for i in range(len(core_labels))]
              if shade_count else None)
    cols = len(core_labels) + 1
    tbl = _plain_table(slide, x, y, len(rows) + 1, cols,
                       cell_w=int(col_w * 914400), cell_h=int(row_h * 914400))
    tbl.columns[0].width = Inches(first_col_w)
    for i in range(1, cols):
        tbl.columns[i].width = Inches(col_w)
    for i in range(len(rows) + 1):
        tbl.rows[i].height = Inches(row_h)
    head = ["轮 \\ 核"] + list(core_labels)
    for c, h in enumerate(head):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK if c else None)
        _write_cell_lines(cell, [h], size=13.0, colors=[TITLE_TEXT])
    for ri, (rlabel, cells) in enumerate(rows, start=1):
        head_cell = tbl.cell(ri, 0)
        _cell_border(head_cell)
        _write_cell_lines(head_cell, [rlabel], size=13.0, colors=[TITLE_TEXT])
        for ci, cdata in enumerate(cells, start=1):
            cell = tbl.cell(ri, ci)
            _cell_border(cell)
            if cdata is None:
                _fill_cell(cell, _HOLE["fill"])
                _write_cell_lines(cell, ["空闲"], size=11.0, colors=[_HOLE["text"]])
            else:
                lane = cdata["lane"]
                if shades:
                    col = shades[lane % len(shades)][cdata.get("shade", 0) % shade_count]
                else:
                    col = colors[lane % len(colors)]
                _fill_cell(cell, col["fill"])
                _write_cell_lines(cell, cdata["lines"], size=cell_size,
                                  colors=[col["text"]] * len(cdata["lines"]))
    return fit_table(tbl)


def trace_table(slide, x, y, col_labels, rows, total_w=6.90, first_col_w=1.20,
                row_h=0.40, size=11.0, head=None, empty="空闲", zebra=True):
    """轮次轨迹表：**行 = 核，列 = 轮次**，格内写这条核这一轮拿到的列（或批）。

    它是任务矩阵的转置视角 —— 任务矩阵回答"这一轮各核在做什么"，
    这张表回答"一条核连着几轮守着同一列"。cells 里 None 表示这一轮空闲。
    隔行底色只铺在普通格上；自带底色的格（dict / 空闲）覆盖它。
    返回底边 y。
    """
    n = len(col_labels)
    cw = max(0.30, (total_w - first_col_w) / max(1, n))
    tbl = _plain_table(slide, x, y, len(rows) + 1, n + 1,
                       cell_w=int(cw * 914400), cell_h=int(row_h * 914400))
    tbl.columns[0].width = Inches(first_col_w)
    for i in range(1, n + 1):
        tbl.columns[i].width = Inches(cw)
    for i in range(len(rows) + 1):
        tbl.rows[i].height = Inches(row_h)
    head = head or []
    for c in range(n + 1):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK)
        body = head[c] if c < len(head) else col_labels[c - 1]
        _write_cell_lines(cell, [str(body)], size=size, colors=[TITLE_TEXT])
    hole = hole_color()
    for r, (rlabel, cells) in enumerate(rows, start=1):
        band = ZEBRA_FILL if (zebra and r % 2 == 1) else None
        cell = tbl.cell(r, 0)
        _cell_border(cell)
        if band:
            _fill_cell(cell, band)
        _write_cell_lines(cell, [str(rlabel)], size=size, colors=[TITLE_TEXT])
        for c in range(n):
            cell = tbl.cell(r, c + 1)
            _cell_border(cell)
            val = cells[c] if c < len(cells) else None
            if isinstance(val, dict):                  # 自带底色的格子
                _fill_cell(cell, val.get("fill"))
                _write_cell_lines(cell, [str(val["text"])], size=size,
                                  colors=[val.get("color", ON_BLOCK)])
            elif val is None:
                _fill_cell(cell, hole["fill"])
                _write_cell_lines(cell, [empty], size=size * 0.85,
                                  colors=[hole["text"]])
            else:
                if band:
                    _fill_cell(cell, band)
                _write_cell_lines(cell, [str(val)], size=size, colors=[TITLE_TEXT])
    return fit_table(tbl), y + (len(rows) + 1) * row_h


def pseudocode_block(slide, x, y, w, lines, size=12.5, pad=0.18, line_h=0.235,
                     title=None):
    """伪代码块：浅灰底 + 等宽字 + 注释灰 + 关键字蓝（配色见 assets/color-sets.json）。

    lines 里用 "#" 分隔注释；"//" 亦可。
    """
    _load_color_sets()
    h = pad * 2 + line_h * (len(lines) + (1 if title else 0))
    from pptx.enum.shapes import MSO_SHAPE
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                                 Inches(w), Inches(h))
    box.adjustments[0] = 0.04
    box.fill.solid()
    box.fill.fore_color.rgb = _rgb(_CODE["bg"])
    box.line.color.rgb = _rgb(_CODE["border"])
    box.line.width = Pt(0.75)
    try:
        box.shadow.inherit = False
    except Exception:
        pass
    tf = box.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(pad)
    tf.margin_top = tf.margin_bottom = Inches(pad * 0.5)
    kw_re = _re.compile(r"(如果|否则|对每个|返回|输入|输出|结束|if|else|for|return|while)")
    items = ([("code", title)] if title else []) + [("code", ln) for ln in lines]
    for i, (_, raw) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = line_h / (size / 72.0) / 1.2
        code, sep, comment = raw.partition("#")
        for piece in kw_re.split(code):
            if not piece:
                continue
            run = p.add_run()
            run.text = piece
            _style_run(run, size=size, bold=(kw_re.fullmatch(piece) is not None),
                       color=(_CODE["keyword"] if kw_re.fullmatch(piece) else _CODE["text"]),
                       font=_CODE["font"])
            _set_cjk_font(run, CJK)
        if sep:
            run = p.add_run()
            run.text = "  " + sep + comment
            _style_run(run, size=size, color=_CODE["comment"], font=_CODE["font"])
            _set_cjk_font(run, CJK)
    return box


def axis_arrow(slide, x, y, length, direction, label, label_off=0.16,
               size=14.0, label_bold=True):
    """轴箭头：一条带箭头短线 + 轴名，用来标出网格的哪个方向是哪个轴。"""
    d = direction.lower()
    if d in ("down", "up"):
        y2 = y + (length if d == "down" else -length)
        arrow(slide, x, y, x, y2)
        text(slide, x - 0.83, (y + y2) / 2.0 - 0.15, label, w=0.78, h=0.30,
             size=size, bold=label_bold, color=TITLE_TEXT, align=PP_ALIGN.RIGHT)
    else:
        x2 = x + (length if d == "right" else -length)
        arrow(slide, x, y, x2, y)
        text(slide, min(x, x2), y - label_off - 0.18, label, w=1.6, h=0.30,
             size=size, bold=label_bold, color=TITLE_TEXT, align=PP_ALIGN.LEFT)


def check_cells(prs: Presentation, pad=0.06, min_spaces=1.0):
    """逐格检查：格内文字（1）不顶出格子、（2）与左右格线至少留 `min_spaces` 个空格。

    表格的格不换行，超了会横穿到隔壁列；即使没超，文字贴边也会显得挤。
    返回 [(页, 表, 行, 列, 文字宽, 可用宽, 一侧间距, 问题, 文字), ...]；
    问题 = "顶格"（文字超出可用宽）或 "贴边"（一侧间距 < 1 个空格）。
    收尾除了 check_layout 还要跑这个 —— 版心检查看不出来"文字压过格线"。
    """
    out = []
    for i, slide in enumerate(prs.slides, 1):
        for shp in slide.shapes:
            if not (getattr(shp, "has_table", False) and shp.has_table):
                continue
            tbl = shp.table
            widths = [Emu(c.width).inches for c in tbl.columns]
            heights = [Emu(r.height).inches for r in tbl.rows]
            for r, row in enumerate(tbl.rows):
                for c, cell in enumerate(row.cells):
                    lines = ["".join(run.text for run in p.runs)
                             for p in cell.text_frame.paragraphs]
                    sizes = [max((run.font.size.pt for run in p.runs
                                  if run.font.size is not None), default=12.0)
                             for p in cell.text_frame.paragraphs]
                    ml = Emu(cell.margin_left).inches
                    mr = Emu(cell.margin_right).inches
                    avail_w = max(0.05, widths[c] - ml - mr)
                    avail_h = max(0.05, heights[r] - 0.09)
                    wide = [est_text_width(ln, sz) for ln, sz in zip(lines, sizes)]
                    tw = max(wide) if wide else 0.0
                    sz = max(sizes) if sizes else 12.0
                    tall = sum(max(s * 1.30 / 72.0, 0.12) for s in sizes)
                    # 文字水平居中：一侧间距 = 格内边距 + 剩余空间的一半
                    slack = avail_w - tw
                    gap = min(ml, mr) + (slack / 2.0 if slack > 0 else 0.0)
                    need = max(0.04, 0.30 * sz / 72.0) * min_spaces
                    label = max(lines, key=len)[:22] if lines else ""
                    if tw > avail_w + pad:
                        out.append((i, shp.name, r, c, round(tw, 2),
                                    round(avail_w, 2), round(gap, 3), "顶格", label))
                    elif tall > avail_h + pad:
                        out.append((i, shp.name, r, c, round(tw, 2),
                                    round(avail_h, 2), round(gap, 3), "顶格", label))
                    elif lines and lines[0].strip() and gap < need:
                        out.append((i, shp.name, r, c, round(tw, 2),
                                    round(avail_w, 2), round(gap, 3), "贴边", label))
    return out


def check_gaps(prs: Presentation, min_gap=0.15):
    """检查相邻元素（表格 / 文字块）之间的间距，太挤会显得拥挤。

    水平范围交叠的元素对看垂直间隙，垂直范围交叠的看水平间隙。返回
    [(页, 元素A, 元素B, 方向, 间隙), ...]；性能图网格线（perf-grid）不参与。
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    out = []
    for i, slide in enumerate(prs.slides, 1):
        boxes = []
        for shp in slide.shapes:
            if shp.name.startswith("perf-grid") or shp.name.startswith("Connector"):
                continue
            if getattr(shp, "has_table", False) and shp.has_table:
                tw, th = table_extent(shp.table)
                boxes.append((shp.name, shp.left / 914400, shp.top / 914400,
                              tw, th, "table"))
                continue
            if shp.shape_type == MSO_SHAPE_TYPE.PICTURE:
                l, t, w, h = _geom(shp)
                boxes.append((shp.name, l, t, w, h, "figure"))
                continue
            ext = _text_extents(shp) if shp.has_text_frame else []
            if ext and shp.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
                x0 = min(e[0] for e in ext)
                y0 = min(e[1] for e in ext)
                x1 = max(e[0] + e[2] for e in ext)
                y1 = max(e[1] + e[3] for e in ext)
                boxes.append((shp.name, x0, y0, x1 - x0, y1 - y0, "text"))
            else:
                l, t, w, h = _geom(shp)
                boxes.append((shp.name, l, t, w, h, "shape"))
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                n1, x1, y1, w1, h1, k1 = boxes[a]
                n2, x2, y2, w2, h2, k2 = boxes[b]
                # 只关心"表格/图片"参与的对：文字行的固定行距不算挤
                if k1 not in ("table", "figure") and k2 not in ("table", "figure"):
                    continue
                if x1 < x2 + w2 and x2 < x1 + w1:          # 水平交叠 → 垂直间隙
                    gap = max(y2 - (y1 + h1), y1 - (y2 + h2))
                    if 0 <= gap < min_gap:
                        out.append((i, n1, n2, "垂直", round(gap, 3)))
                elif y1 < y2 + h2 and y2 < y1 + h1:        # 垂直交叠 → 水平间隙
                    gap = max(x2 - (x1 + w1), x1 - (x2 + w2))
                    if 0 <= gap < min_gap:
                        out.append((i, n1, n2, "水平", round(gap, 3)))
    return out


def _norm_cell(s: str) -> str:
    return " ".join(str(s).split())


def read_task_matrices(prs: Presentation):
    """回读全部「轮 \\ 核」任务矩阵。

    返回 {slide_index(1-based): [[cell_text, ...], ...]}（换行折成空格）。
    用于把页面矩阵与算法函数输出逐格对照 —— case 的 `check_case.py` 就是这么验的。
    """
    out = {}
    for i, slide in enumerate(prs.slides, 1):
        for shp in slide.shapes:
            if not (getattr(shp, "has_table", False) and shp.has_table):
                continue
            tbl = shp.table
            if _norm_cell(tbl.cell(0, 0).text).replace(" ", "") != "轮\\核":
                continue
            out[i] = [[_norm_cell(tbl.cell(r, c).text)
                       for c in range(len(tbl.columns))]
                      for r in range(len(tbl.rows))]
    return out


def check_task_matrices(prs: Presentation, expected) -> list:
    """把 expected（{slide: [[cell, ...], ...]}）与页面任务矩阵逐格比对。

    空串 / None 的期望格表示允许为空（idle 槽）。返回
    [(slide, row, col, expected, got), ...]，空列表 = 全部一致。
    """
    actual = read_task_matrices(prs)
    out = []
    for sl, exp in expected.items():
        got = actual.get(sl)
        if got is None:
            out.append((sl, -1, -1, "<matrix not found>", ""))
            continue
        for r, erow in enumerate(exp):
            for c, e in enumerate(erow):
                if e is None or str(e) == "":
                    continue
                if r >= len(got) or c >= len(got[r]):
                    out.append((sl, r, c, _norm_cell(e), "<missing>"))
                    continue
                if _norm_cell(e) != got[r][c]:
                    out.append((sl, r, c, _norm_cell(e), got[r][c]))
    return out


def check_layout(prs: Presentation, slide_index=None):
    """排版硬检查：任何文字/表格越过版心都算错误。

    返回 (errors, warnings)。errors 必须修掉；warnings 是"贴着边"的提醒。
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    errors, warnings = [], []
    cl, ct, cr, cb = content_box(prs)
    for i, slide in enumerate(prs.slides, 1):
        if slide_index and i != slide_index:
            continue
        boxes = []
        for shp in slide.shapes:
            l, t, w, h = _geom(shp)
            if getattr(shp, "has_table", False) and shp.has_table:
                tw, th = table_extent(shp.table)      # 按真实列宽/行高算
                w, h = tw, th
            ext = _text_extents(shp) if shp.has_text_frame else []
            # 无填充的纯文本框：按文字实际占位判；有填充的图形/表格：按自身框判
            bare_tb = (shp.shape_type == MSO_SHAPE_TYPE.TEXT_BOX)
            if ext:
                x0 = min(e[0] for e in ext)
                x1 = max(e[0] + e[2] for e in ext)
                y0 = min(e[1] for e in ext)
                y1 = max(e[1] + e[3] for e in ext)
                if x0 < cl - 0.02 or x1 > cr + 0.02 or y0 < ct - 0.02 or y1 > cb + 0.02:
                    errors.append(
                        f"S{i} 文字越出版心: {shp.name} "
                        f"文字=({x0:.2f},{y0:.2f})~({x1:.2f},{y1:.2f}) "
                        f"版心=({cl},{ct})~({cr:.2f},{cb:.2f})  "
                        f"「{shp.text_frame.text[:22]}」")
                if bare_tb:
                    boxes.append((shp.name, x0, y0, x1 - x0, y1 - y0))
                    continue                     # 纯文本框按文字占位判，不按声明框
                boxes.append((shp.name, l, t, w, h))
            else:
                boxes.append((shp.name, l, t, w, h))
            if l < cl - 0.02 or t < ct - 0.02 or l + w > cr + 0.02 or t + h > cb + 0.02:
                errors.append(f"S{i} 图形越出版心: {shp.name} ({l:.2f},{t:.2f}) "
                              f"{w:.2f}x{h:.2f}  版心=({cl},{ct})-({cr:.2f},{cb:.2f})")
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                n1, x1, y1, w1, h1 = boxes[a]
                n2, x2, y2, w2, h2 = boxes[b]
                if n1.startswith("perf-grid") or n2.startswith("perf-grid"):
                    continue               # 性能图网格线穿过柱子是设计，不算重叠
                if x1 < x2 + w2 - 0.02 and x2 < x1 + w1 - 0.02 and \
                   y1 < y2 + h2 - 0.02 and y2 < y1 + h1 - 0.02:
                    warnings.append(f"S{i} 元素重叠: {n1} 与 {n2}")
    return errors, warnings


# ---------------------------------------------------------------- 通用小构件

def panel_height(n_rows, row_h=0.42, gap=0.44):
    """panel() 画完会占多高（含表外标题那一行）。

    排版前先算高度、再决定这块放哪一栏 —— 否则只能"画完发现放不下"。
    """
    return gap + (n_rows + 1) * row_h


def panel(slide, x, y, head, header, rows, col_w, row_h=0.42, size=13.0, w=None,
          gap=0.44, zebra=True):
    """带表外标题的小表（标题不占表格空间）。返回底边 y。

    gap：标题与表格之间的间距 —— 表块和文字不要贴太近，留够呼吸。
    zebra：全白表格隔行铺 `ZEBRA_FILL`，白/灰相间让行更分明。
    格内文本用 `\\n` 分行（较长的一句拆两行，比把表拉宽更省地方）。
    """
    text(slide, x, y, head, w=(w or sum(col_w) + 0.4), h=0.30, size=15.0, bold=True)
    tbl = _plain_table(slide, x, y + gap, len(rows) + 1, len(header),
                       cell_w=int(col_w[0] * 914400), cell_h=int(row_h * 914400))
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = Inches(cw)
    for i in range(len(rows) + 1):
        tbl.rows[i].height = Inches(row_h)
    for c, h_ in enumerate(header):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK)
        _write_cell_lines(cell, [h_], size=size, colors=[TITLE_TEXT])
    for r, row in enumerate(rows, start=1):
        band = ZEBRA_FILL if (zebra and r % 2 == 1) else None
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            if band:
                _fill_cell(cell, band)
            lines = str(val).split("\n")
            _write_cell_lines(cell, lines, size=size,
                              colors=[TITLE_TEXT] * len(lines))
    return y + gap + (len(rows) + 1) * row_h


def axis_grid(slide, x, y, n_rows, n_cols, cells, caption=None, lane_set="cool",
              cell_in=0.62, row_label="S1", col_label="S2",
              empty_text="空闲", label_size=13.0, shade_count=None,
              head_size=12.0, cell_margin=None):
    """带轴头的覆盖图：列头 `S2=1..n`、行头 `S1=1..m`、格内是内容 + lane 配色。

    cells: {(r-1, c-1): (文本, lane 序号[, shade 序号])}；缺的格子填 hole 灰。
    caption 只占本表宽度并紧贴其上，避免归属歧义。
    row_label / col_label 里写 `{v}` 就按它排版（如 `虚拟行{v}`），
    否则默认按 `标签=序号` 写；轴头文字比格内文字小一号时用 head_size。
    """
    def _axis_label(label, v):
        return label.format(v=v) if "{v}" in label else f"{label}={v}"
    cm = cell_margin if cell_margin is not None else min(MARGIN, cell_in * 0.08)
    tbl = _plain_table(slide, x, y, n_rows + 1, n_cols + 1,
                       cell_w=int(cell_in * 914400), cell_h=int(cell_in * 914400))
    for i in range(n_cols + 1):
        tbl.columns[i].width = Inches(cell_in)
    for i in range(n_rows + 1):
        tbl.rows[i].height = Inches(cell_in)
    colors = lane_colors(lane_set, 8)
    shade_cache = {}

    def _color(lane, shade):
        if shade_count is None:
            return colors[lane % len(colors)]
        if lane not in shade_cache:
            shade_cache[lane] = lane_shades(lane_set, lane, shade_count)
        return shade_cache[lane][shade % shade_count]
    hole = hole_color()
    for c in range(n_cols + 1):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        if c:
            _fill_cell(cell, ON_BLOCK)
            _write_cell_lines(cell, [_axis_label(col_label, c)], size=head_size,
                              colors=[TITLE_TEXT], margin=cm)
    for r in range(1, n_rows + 1):
        cell = tbl.cell(r, 0)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK)
        _write_cell_lines(cell, [_axis_label(row_label, r)], size=head_size,
                          colors=[TITLE_TEXT], margin=cm)
        for c in range(1, n_cols + 1):
            cell = tbl.cell(r, c)
            _cell_border(cell)
            got = cells.get((r - 1, c - 1))
            if got is None:
                _fill_cell(cell, hole["fill"])
                _write_cell_lines(cell, [empty_text], size=11.0, colors=[hole["text"]],
                                  margin=cm)
            else:
                label, lane = got[0], got[1]
                shade = got[2] if len(got) > 2 else 0
                col = _color(lane, shade)
                _fill_cell(cell, col["fill"])
                lines = str(label).split("\n")          # 允许格内两行
                _write_cell_lines(cell, lines, size=label_size,
                                  colors=[col["text"]] * len(lines), margin=cm)
    if caption:
        text(slide, x + 0.04, y - 0.46, caption, w=(n_cols + 1) * cell_in, h=0.30,
             size=14.0, bold=True, color=TITLE_TEXT)
    return tbl


# ---------------------------------------------------------------- 性能对比（可选）

# 色系取自 DeepSeek-V3 benchmark 图（deepseek-ai/DeepSeek-V3 figures/benchmark.png）：
# 本仓库主版本 = 宝蓝 + 白色宽斜纹（该图 DeepSeek-V3 的条形），次版本 = 浅蓝；
# 参考仓库 = 两档灰；其它对比方 = 棕褐 / 米色。性能图只在有 profiling 数据时才画。
PERF_SELF = "4D6BFE"
PERF_SELF_ALT = "AAC1FF"
PERF_REF = "BDBDBD"
PERF_REF_ALT = "D4D4D4"
PERF_ACCENT = "E8D2A0"
PERF_ACCENT_ALT = "F5EBD2"
PERF_GRID = "E3E3E3"
PERF_AXIS = "1A1A1A"
PERF_SUB = "6B6F76"
PERF_HILITE = "EEF2FF"


def _darken(hexv: str, factor: float = 0.80) -> str:
    r, g, b = (int(hexv[i:i + 2], 16) for i in (0, 2, 4))
    return f"{int(r * factor):02X}{int(g * factor):02X}{int(b * factor):02X}"


def _nice_max(v: float) -> float:
    import math
    if v <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * base >= v - 1e-9:
            return m * base
    return 10 * base


def _bar_shape(slide, x, y, w, h, color, hatch=False, outline=True):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.dml import MSO_PATTERN
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                 Inches(w), Inches(h))
    if hatch:
        shp.fill.patterned()
        shp.fill.pattern = MSO_PATTERN.WIDE_UPWARD_DIAGONAL
        shp.fill.fore_color.rgb = _rgb("FFFFFF")
        shp.fill.back_color.rgb = _rgb(color)
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(color)
    if outline:
        shp.line.color.rgb = _rgb(_darken(color))
        shp.line.width = Pt(0.75)
    else:
        shp.line.fill.background()
    try:
        shp.shadow.inherit = False
    except Exception:
        pass
    return shp


def perf_table(slide, x, y, cols, series, header="核时 (μs)", first_col_w=1.35,
               col_w=0.95, size=11.5, row_h=0.38, best="min", fmt="{:.1f}",
               fmts=None, best_rows=None, best_groups=None, highlight=(),
               note=None):
    """性能对比表：核时 / 吞吐的横向对比（可选，有 profiling 数据才画）。

    cols      : 列标签（shape / 配置）
    series    : [(名称, [值, ...]), ...]
    best      : 每列加粗最优值 —— 核时越小越好用 "min"，吞吐越大越好用 "max"；
                明细表不需要加粗时传 best=None"
    fmts      : 逐行格式（缺省全部用 fmt）；比值行可单独用 "{:.2f}"
    best_rows : 参与"最优加粗"的行号（缺省全部；比值行语义不一可只留原始数据行）
    highlight : 行号集合，浅蓝底标出本仓库版本
    note      : 口径备注。核时表必须注明是 **profiling 核时**、不是 event record
    """
    if note is None:
        note = "profiling 核时（device 侧 kernel 时间），非 event record 端到端计时"
    n = len(series)
    tbl = _plain_table(slide, x, y, n + 1, len(cols) + 1,
                       cell_w=int(first_col_w * 914400), cell_h=int(row_h * 914400))
    tbl.columns[0].width = Inches(first_col_w)
    for i in range(1, len(cols) + 1):
        tbl.columns[i].width = Inches(col_w)
    for i in range(n + 1):
        tbl.rows[i].height = Inches(row_h)
    for c, h_ in enumerate((header,) + tuple(cols)):
        cell = tbl.cell(0, c)
        _cell_border(cell)
        _fill_cell(cell, ON_BLOCK)
        _write_cell(cell, str(h_), size=size, bold=False, color=TITLE_TEXT,
                    cjk_font=CJK)
    fmts = fmts or [fmt] * n
    if best_groups is None:
        best_groups = ([] if best is None else
                       [list(range(n)) if best_rows is None
                        else list(best_rows)])
    row_group = {ri: gi for gi, grp in enumerate(best_groups) for ri in grp}
    picks = ([] if best is None else
             [[min(series[ri][1][ci] for ri in grp) if best == "min"
               else max(series[ri][1][ci] for ri in grp)
               for ci in range(len(cols))] for grp in best_groups])
    for si, s in enumerate(series):
        label, vals = s[0], s[1]
        r = si + 1
        band = (PERF_HILITE if si in highlight
                else (ZEBRA_FILL if r % 2 == 1 else None))
        lcell = tbl.cell(r, 0)
        _cell_border(lcell)
        if band:
            _fill_cell(lcell, band)
        lcolor = TITLE_TEXT
        if len(s) > 2 and s[2]:
            lcolor = _darken(s[2], 0.85)
        _write_cell(lcell, str(label), size=size, bold=False, color=lcolor,
                    cjk_font=CJK)
        for ci, v in enumerate(vals):
            cell = tbl.cell(r, ci + 1)
            _cell_border(cell)
            if band:
                _fill_cell(cell, band)
            gi = row_group.get(si)
            is_best = (gi is not None and
                       abs(float(v) - float(picks[gi][ci])) < 1e-9)
            _write_cell(cell, fmts[si].format(v), size=size, bold=is_best,
                        color=STRONG_TEXT if is_best else TITLE_TEXT)
    fit_table(tbl)
    bottom = y + (n + 1) * row_h
    if note:
        text(slide, x, bottom + 0.16, note,
             w=first_col_w + col_w * len(cols) + 0.30, h=0.26, size=10.5,
             color=PERF_SUB)
        bottom += 0.44
    return bottom


def perf_bars(slide, x, y, w, groups, series, chart_h=3.30, ylabel=None,
              value_fmt="{:.2f}", ymax=None, legend=True, hatch_first=True,
              value_size=9.0, label_size=11.0, grid_lines=4, bar_gap=0.18,
              best_series=0, note=None):
    """性能柱状图：吞吐 / 带宽对比（可选，有 profiling 数据才画）。

    groups : 组标签（shape / 配置），横轴
    series : [(名称, [每组一个值][, 颜色]), ...]；值用吞吐 / 带宽等"越大越好"的指标
    hatch_first : 第一条系列用宝蓝 + 白色宽斜纹（DeepSeek-V3 图的主系列样式）
    note   : 图下口径备注（数据来源、规范化方式等）；返回底边 y
    """
    n_g, n_s = len(groups), len(series)
    colors = []
    for si, s in enumerate(series):
        if len(s) > 2:
            colors.append(s[2])
        else:
            colors.append((PERF_SELF, PERF_SELF_ALT, PERF_REF,
                           PERF_REF_ALT)[si % 4])
    vals = [[float(s[1][gi]) for gi in range(n_g)] for s in series]
    vmax = ymax or _nice_max(max(max(v) for v in vals) * 1.12)

    cur_y = y
    if legend:
        cur = x
        for si, s in enumerate(series):
            chip = _bar_shape(slide, cur, cur_y + 0.03, 0.17, 0.17, colors[si],
                              hatch=(hatch_first and si == best_series), outline=True)
            text(slide, cur + 0.21, cur_y, str(s[0]), w=w - (cur - x) - 0.21,
                 h=0.26, size=11.0, bold=False, color=TITLE_TEXT)
            cur += 0.21 + est_text_width(str(s[0]), 11.0) + 0.30
        cur_y += 0.34
    if ylabel:
        text(slide, x, cur_y, ylabel, w=w, h=0.26, size=10.5, color=PERF_SUB)
    ct = cur_y + (0.30 if ylabel else 0.06)      # 图区顶
    cb = y + chart_h - 0.42                      # 基线
    x0 = x + 0.46                                # 左侧刻度文字宽
    pw = w - 0.46

    for i in range(grid_lines + 1):
        gv = vmax * i / grid_lines
        gy = cb - (cb - ct) * i / grid_lines
        if i:
            line = slide.shapes.add_connector(
                1, Inches(x0), Inches(gy), Inches(x0 + pw), Inches(gy))
            line.line.color.rgb = _rgb(PERF_GRID)
            line.line.width = Pt(0.75)
            from pptx.enum.dml import MSO_LINE_DASH_STYLE
            line.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            # 网格线穿过柱子是图表本意，命名以便 check_layout 不算重叠
            try:
                line.name = "perf-grid"
            except Exception:
                line._element.xpath('.//*[local-name()="cNvPr"]')[0].set(
                    "name", "perf-grid")
        fmt = f"{gv:g}"
        text(slide, x, gy - 0.11, fmt, w=0.42, h=0.22, size=9.5, color=PERF_SUB,
             align=PP_ALIGN.RIGHT)
    base = slide.shapes.add_connector(
        1, Inches(x0), Inches(cb), Inches(x0 + pw), Inches(cb))
    base.line.color.rgb = _rgb(PERF_AXIS)
    base.line.width = Pt(1.0)

    slot = pw / n_g
    bw = slot * (1 - bar_gap) / n_s
    for gi, g in enumerate(groups):
        gx = x0 + gi * slot + slot * bar_gap / 2
        for si in range(n_s):
            v = vals[si][gi]
            bh = (cb - ct) * v / vmax
            bx = gx + si * bw
            _bar_shape(slide, bx, cb - bh, bw * 0.88, bh, colors[si],
                       hatch=(hatch_first and si == best_series), outline=True)
            main = si == best_series
            text(slide, bx - 0.08, cb - bh - (0.24 if main else 0.21),
                 value_fmt.format(v), w=bw * 0.88 + 0.16, h=0.22,
                 size=value_size + (1.5 if main else 0.0), bold=main,
                 color=STRONG_TEXT if main else PERF_SUB, align=PP_ALIGN.CENTER)
        text(slide, x0 + gi * slot, cb + 0.07, str(g), w=slot, h=0.26,
             size=label_size, bold=True, color=TITLE_TEXT, align=PP_ALIGN.CENTER)
    bottom = y + chart_h
    if note:
        text(slide, x, cb + 0.40, note, w=w, h=0.26, size=10.5, color=PERF_SUB)
        bottom += 0.30
    return bottom


def perf_figure(slide, x, y, w, h, panels, dpi=200, note=None, font=None,
                ncols=None):
    """用 matplotlib 渲染性能对比图（推荐），以 PNG 贴进页面。

    panels : [dict(title=..., groups=[...], series=[(标签, [值, ...][, 颜色]) ...],
                   ylabel=..., value_fmt="{:.2f}", best=0, ref=None,
                   split=None, split_lo=None, bar_w=None), ...]
             —— 每个 dict 一个子图；best = 用斜纹加粗强调的系列号；
             ref = 参考虚线值（如 1.0）；split = 按阈值逐柱上色（≥split 主色、
             否则 split_lo，默认灰）—— 用于"比值 < 1 标灰"这类好坏分侧；
             bar_w = 单柱占组槽的宽度比例（缺省 0.80/系列数；单系列图建议 0.4–0.5，
             柱子细一点更透气）；
             xrot = 横轴标签旋转角度（case 多时用 45–90，缺省 0）；
             show_values = 是否在每根柱顶标数值（缺省 True；柱子太密时设 False，
             数值交给图下的小表）；value_size = 柱顶数值字号（缺省 7.5）。
    font   : matplotlib 字体族。缺省 DejaVu Sans —— 没有 CJK 字体时请把图内文字写成
             英文，中文说明留在页面文字 / 表格里。
    ncols  : 子图列数（缺省 = len(panels)，即单行）；>1 时按网格排布，行数
             = ceil(len(panels)/ncols)。panel 里可加 legend=False 关闭该子图图例。
    返回底边 y（含 note）。依赖 matplotlib（可选依赖；缺了请退回 perf_bars）。
    """
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [font] if font else ["DejaVu Sans"],
        "axes.edgecolor": "#E3E3E3",
        "text.color": "#" + PERF_AXIS, "axes.labelcolor": "#" + PERF_SUB,
    })
    ncols = ncols or len(panels)
    nrows = -(-len(panels) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(w, h), dpi=dpi)
    axes = list(axes.flatten()) if hasattr(axes, "flatten") else [axes]
    for ax in axes[len(panels):]:
        ax.axis("off")
    for ax, p in zip(axes, panels):
        groups, series = p["groups"], p["series"]
        n_g, n_s = len(groups), len(series)
        width = p.get("bar_w") or (0.80 / n_s)
        best = p.get("best", 0)
        xv = list(range(n_g))
        vmax = 0.0
        split = p.get("split")
        for si, s in enumerate(series):
            label, vals = s[0], s[1]
            color = s[2] if len(s) > 2 else (
                PERF_SELF, PERF_SELF_ALT, PERF_REF, PERF_REF_ALT)[si % 4]
            off = (si - (n_s - 1) / 2.0) * width
            vmax = max(vmax, max(vals))

            # split 模式下图例挂在"代表色"的柱子上（优先高侧蓝柱）
            label_gi = 0
            if split is not None:
                label_gi = next((i for i, v in enumerate(vals) if v >= split), 0)

            def draw_bar(gi_, v):
                # split 不为空时按阈值逐柱上色：>= split 用主色（斜纹），
                # 否则用 split_lo（默认灰）—— 一眼看出"好/差"两侧
                hi = (split is None) or (v >= split)
                col = color if hi else p.get("split_lo", PERF_REF)
                hatched = (si == best) and hi
                b = ax.bar([xv[gi_] + off], [v], width * 0.92,
                           color="#" + col, zorder=3,
                           edgecolor=("white" if hatched else "#" + _darken(col)),
                           linewidth=(0.0 if hatched else 0.7),
                           hatch=("///" if hatched else None),
                           label=label if gi_ == label_gi else None)[0]
                if p.get("show_values", True):
                    ax.text(b.get_x() + b.get_width() / 2.0, v,
                            p.get("value_fmt", "{:.2f}").format(v),
                            ha="center", va="bottom", zorder=4,
                            fontsize=p.get("value_size", 7.5),
                            fontweight=("bold" if hatched else "normal"),
                            color=("#1A1A1A" if hatched else "#" + PERF_SUB))

            if split is None:
                bars = ax.bar(
                    [v + off for v in xv], vals, width * 0.92, label=label,
                    color=("#" + color), zorder=3,
                    edgecolor=("white" if (si == best) else "#" + _darken(color)),
                    linewidth=(0.0 if si == best else 0.7),
                    hatch=("///" if si == best else None))
                if p.get("show_values", True):
                    for b, v in zip(bars, vals):
                        ax.text(b.get_x() + b.get_width() / 2.0, v,
                                p.get("value_fmt", "{:.2f}").format(v),
                                ha="center", va="bottom", zorder=4,
                                fontsize=p.get("value_size", 7.5),
                                fontweight=("bold" if si == best else "normal"),
                                color=("#1A1A1A" if si == best else "#" + PERF_SUB))
            else:
                for gi_, v in enumerate(vals):
                    draw_bar(gi_, v)
        if p.get("ref") is not None:
            ax.axhline(p["ref"], ls=(0, (4, 3)), lw=0.9, color="#" + PERF_AXIS, zorder=2)
        ax.set_xticks(xv)
        xrot = p.get("xrot", 0)
        ax.set_xticklabels(
            groups, fontsize=p.get("label_size", 8.8), fontweight="bold",
            rotation=xrot, ha=("right" if xrot else "center"),
            rotation_mode=("anchor" if xrot else None))
        ax.set_ylabel(p.get("ylabel", ""), fontsize=8.8)
        ax.set_title(p.get("title", ""), fontsize=10.0, fontweight="bold", pad=8)
        ax.set_ylim(0, p.get("ymax") or vmax * 1.18)
        ax.grid(axis="y", ls="--", lw=0.8, color="#E3E3E3")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#" + PERF_AXIS)
        ax.tick_params(axis="both", labelsize=8.0, colors="#" + PERF_SUB,
                       length=3, width=0.7)
        if p.get("legend", True):
            ax.legend(frameon=False, fontsize=8.5, ncol=min(3, n_s),
                      loc="upper left")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    slide.shapes.add_picture(buf, Inches(x), Inches(y), width=Inches(w))
    bottom = y + h
    if note:
        text(slide, x, bottom + 0.12, note, w=w, h=0.26, size=10.5, color=PERF_SUB)
        bottom += 0.40
    return bottom


# ---------------------------------------------------------------- 演示

def demo_schedule(m=3, n=3, k=2):
    """一种最简单的分派：把 m*n 个块按「核优先」铺开，末轮可能有余不下的格子。

    返回 (rows, cells)：rows 给 task_matrix 用；cells 给 axis_grid 用。
    """
    rows, grid = [], {}
    for r in range(1, -(-m * n // k) + 1):
        row_cells = []
        for j in range(1, k + 1):
            idx = (r - 1) * k + (j - 1)
            if idx >= m * n:
                row_cells.append(None)
                continue
            s1, s2 = idx // n + 1, idx % n + 1
            row_cells.append({"lines": [f"S1={s1}  S2={s2}", f"任务号={idx + 1}"],
                              "lane": j - 1})
            grid[(s1 - 1, s2 - 1)] = (f"第{r}轮", j - 1)
        rows.append((f"第 {r} 轮", row_cells))
    return rows, grid


def demo(path="demo.pptx"):
    m, n, k = 3, 3, 2
    prs = new_deck()

    # ---- 页 1：张量分块 + 核/轮分配 + 累加关系 ----
    s = blank_slide(prs)
    title(s, "张量分块与核/轮分配")
    text(s, 0.73, 1.22, f"输入：核数 {k} · S1 分 {m} 块 · S2 分 {n} 块 · 共 {m * n} 个分块",
         w=13.0, h=0.30, size=16, color=BODY_TEXT)
    spec_table(s, 0.73, 1.72, ("参数", "取值", "说明", "备注"),
               (("核数 k", str(k), "并行计算的核数量", "lane 数"),
                ("S1 块数 m", str(m), "第 1 个方向切成几块", "每块 128 行"),
                ("S2 块数 n", str(n), "第 2 个方向切成几块", "每块 128 列"),
                ("分块总数", str(m * n), "m x n", "每个块一项任务"),
                ("轮数", str(-(-m * n // k)), "ceil(m*n / k)", "末轮可能有余")),
               col_w=(1.60, 1.20, 4.10, 3.08))
    round_table(s, 0.73, 5.90, ("核/轮", "C1", "C2"),
                (("第 1 轮", "S1=1 S2=1", "S1=2 S2=1"),
                 ("第 2 轮", "S1=3 S2=1", "S1=1 S2=2"),
                 ("第 3 轮", "S1=2 S2=2", "S1=3 S2=2"),
                 ("第 4 轮", "S1=1 S2=3", "S1=2 S2=3"),
                 ("第 5 轮", "S1=3 S2=3", "—")),
                row_h=(0.60, 0.50, 0.50, 0.50, 0.50, 0.50))
    # 块网格：每格 = 一个分块，用分组色区分
    fills, labels = [], []
    for r in range(m):
        row_f, row_l = [], []
        for c in range(n):
            row_f.append([GROUP0, GROUP1, GROUP2][(r + c) % 3])
            row_l.append(f"B{r * n + c}")
        fills.append(row_f)
        labels.append(row_l)
    text(s, 5.60, 5.72, "分块网格（颜色 = 分组）", w=4.0, h=0.30, size=15, bold=True)
    block_grid(s, 5.60, 6.15, fills, labels)
    panel(s, 5.60, 8.55, "每个核负责哪些块", ("核", "负责的 (S1, S2)"),
          (("C1", "S1=1 S2=1 -> S1=3 S2=1 -> S1=2 S2=2 -> S1=1 S2=3 -> S1=3 S2=3"),
           ("C2", "S1=2 S2=1 -> S1=1 S2=2 -> S1=3 S2=2 -> S1=2 S2=3")),
          col_w=(0.90, 7.10), row_h=0.44, size=12.5)
    note(s, 0.73, 10.40, "分块分给核以后，每个核按自己的顺序累加 —— 顺序固定，结果就固定。",
         w=9.70, h=0.36)

    # ---- 页 2：任务矩阵（轮 x 核）+ 覆盖图 ----
    s = blank_slide(prs)
    title(s, "任务矩阵与覆盖图")
    text(s, 0.73, 1.22, "任务矩阵：纵轴是轮、横轴是核；覆盖图把同样的信息摊到 (S1, S2) 平面上",
         w=15.0, h=0.30, size=16, color=BODY_TEXT)
    blk = pseudocode_block(s, 0.73, 1.62, 9.6, [
        f"核数 k={k}, S1 块数 m={m}, S2 块数 n={n}",
        "对每个 (轮 r, 核 j):",
        "    任务号 = (r-1) * k + (j-1)      # 核优先，一条接一条铺",
        "    第几块 = 任务号 + 1",
        "    S1 = (第几块-1) / n + 1         # 先走 S2 再换 S1",
        "    S2 = (第几块-1) % n + 1",
        "    任务号 >= m*n 时本核本轮空闲",
    ])
    rows, cells = demo_schedule(m, n, k)
    sd_ty = 1.62 + est_box(blk)[3] + 0.32
    task_matrix(s, 0.73, sd_ty, [f"C{j}" for j in range(1, k + 1)], rows,
                col_w=4.2, row_h=0.52, lane_set="cool")
    panel(s, 0.73, sd_ty + (len(rows) + 1) * 0.52 + 0.42, "这个例子的数字", ("项", "值"),
          (("分块总数", m * n), ("轮数", len(rows)), ("核数", k),
           ("空位（末轮余下）", len(rows) * k - m * n)),
          col_w=(3.20, 1.45), row_h=0.44, size=13.0)
    note(s, 0.73, 10.35, "一条核在一轮里只算一个分块；核数除不尽时末轮有空位（灰格）。", w=9.7)
    # 覆盖图：(S1, S2) 平面，格内是第几轮、颜色是哪个核
    axis_grid(s, 11.20, 3.20, m, n, cells, caption="全部分块", lane_set="cool",
              cell_in=0.80)
    axis_arrow(s, 10.85, 3.20, (m + 1) * 0.80 - 0.48, "down", "S1")
    axis_arrow(s, 11.20, 2.42, (n + 1) * 0.80 - 0.48, "right", "S2")
    text(s, 11.20, 3.20 + (m + 1) * 0.80 + 0.18,
         "格内 = 第几轮执行，颜色 = 哪个核", w=4.6, h=0.30, size=13, color=BODY_TEXT)

    save(prs, path)
    errors, warns = check_layout(prs)
    print(f"wrote {path}")
    print(f"版心检查: {len(errors)} 越界 / {len(warns)} 重叠")
    for e in errors[:8]:
        print("  !", e)
    for w in warns[:8]:
        print("  ~", w)


if __name__ == "__main__":
    import sys
    demo(sys.argv[1] if len(sys.argv) > 1 else "demo.pptx")
