"""Read back a generated deck and assert it matches the measured style."""
import sys
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu

path = sys.argv[1]
prs = Presentation(path)
print("slide size(in):", round(Emu(prs.slide_width).inches, 3), "x",
      round(Emu(prs.slide_height).inches, 3))

checks = {"borders": 0, "no_style_id": 0, "tables": 0, "cells_filled": 0}
samples = []
for si, slide in enumerate(prs.slides, 1):
    for shp in slide.shapes:
        if not getattr(shp, "has_table", False) or not shp.has_table:
            continue
        tbl = shp.table
        checks["tables"] += 1
        tblPr = tbl._tbl.tblPr
        if tblPr.find(qn("a:tableStyleId")) is None and len(tblPr) <= 1:
            checks["no_style_id"] += 1
            samples.append(f"  slide{si} tblPr children = {[c.tag.split('}')[1] for c in tblPr]}")
        for r, row in enumerate(tbl.rows):
            for c, cell in enumerate(row.cells):
                tcPr = cell._tc.find(qn("a:tcPr"))
                if tcPr is not None and tcPr.find(qn("a:lnL")) is not None:
                    checks["borders"] += 1
                if tcPr is not None and tcPr.find(qn("a:solidFill")) is not None:
                    checks["cells_filled"] += 1
                if r < 2 and c < 2 and si <= 2:
                    fill = tcPr.find(qn("a:solidFill")) if tcPr is not None else None
                    hexv = None
                    if fill is not None:
                        clr = fill.find(qn("a:srgbClr"))
                        hexv = clr.get("val") if clr is not None else None
                    runs = [r_ for p in cell.text_frame.paragraphs for r_ in p.runs]
                    info = [(r_.text, r_.font.name, r_.font.size.pt if r_.font.size else None,
                             r_.font.bold,
                             str(r_.font.color.rgb) if r_.font.color and r_.font.color.type is not None else None)
                            for r_ in runs]
                    samples.append(f"  slide{si} cell({r},{c}) fill={hexv} {info}")

print("counts:", checks)
print("column width slide1 table0:", [round(Emu(c.width).inches, 3) for c in
                                      list(prs.slides[0].shapes)[2].table.columns] if len(list(prs.slides[0].shapes)) > 2 else "n/a")
for s in samples[:24]:
    print(s)
