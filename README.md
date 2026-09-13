# SeeTen — Tensor Table Drawing

**English** | [中文](README.zh-CN.md)

Turn the logic of "tiles + cores + rounds" parallel schemes into presentation pages.
The core idea: **use native PPT tables as a tensor canvas** — one cell is one tile, the fill
color encodes semantics, and the cell text states exactly which index of which axis it is.
Pseudocode blocks explain the logic; arrowed connectors draw the dataflow.

It is also a **measured style spec**: canvas size, palette, fonts and geometry all have exact
values, so pages come out visually consistent instead of one-off.

```
SeeTen/
  package.json / bin/ / lib/    # npm CLI `seeten` — installs this skill and its Python deps
                                #   (zero npm dependencies: Node built-ins only)
  SKILL.md                      # Skill entry: when to use, hard rules, how to use
  references/
    style-spec.md               # Measured style spec: canvas / palette / fonts / geometry / table archetypes
    diagram-recipes.md          # Recipes for each diagram type + pre-flight checklist
  scripts/
    seeten_draw.py              # python-pptx generation library (the core)
    verify_demo.py              # Read the deck back and self-check (table style / borders / fonts)
    render_deck.ps1             # Export pptx to PNG so pages can be reviewed visually
  assets/
    palette.json                # Measured palette and geometry constants (raw EMU)
    color-sets.json             # Lane color presets + pseudocode block colors
  examples/demo.pptx            # Generic demo (2 pages)
  cases/                        # Case studies: real scheme pages drawn with these rules
```

---

## 1. Install (one command)

```bash
npx github:guomc9/SeeTen init
```

That single command:

- installs the skill into your agent CLI's skill directory (auto-detects `.claude/`,
  `AGENTS.md`, `CLAUDE.md`, `KIMI.md`);
- provisions `python-pptx` — reuses your system Python if it already has it, otherwise creates
  an isolated venv at `~/.seeten/venv` (your system environment is never modified);
- generates a demo deck and runs the layout self-check, so problems surface immediately;
- reports whether PNG export (WPS / LibreOffice) is available for visual review.

You need **Node 18+** and **Python 3.8+** on the machine; everything else is handled for you.
No npm account or publish step is involved — `npx github:` installs straight from the repository.

| Command | What it does |
|---|---|
| `seeten init [--global] [--no-demo]` | install the skill + provision Python deps + smoke test |
| `seeten draw <script.py> [out.pptx]` | run your drawing script in the provisioned environment |
| `seeten draw --demo [out.pptx]` | generate the generic demo deck |
| `seeten render <file.pptx>` | export PNGs so you can review the layout visually |
| `seeten doctor` | report what is installed and what is missing |

`seeten draw` puts the skill's `scripts/` on `PYTHONPATH`, so your script only needs
`from seeten_draw import *`.

## 2. Manual installation (per-CLI details)

The CLI above is the recommended path. This section is what it automates — useful if you
would rather wire things up by hand, or need the details for an unusual CLI.

This skill is **just a directory**. It is not tied to any CLI: any agent that can read files
and run Python can use it. "Installing" therefore means *pointing the agent at `SKILL.md`*
and letting it execute the scripts under `scripts/`.

To do it by hand you also need the Python side:

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install python-pptx
# macOS / Linux
.venv/bin/python -m pip install python-pptx
```

### 2.0 If you installed with the CLI, you can stop here

### 2.1 Claude Code (native skill mechanism)

Claude Code auto-discovers `<project>/.claude/skills/<name>/SKILL.md` and
`~/.claude/skills/<name>/SKILL.md`. **The directory name must match `name` in `SKILL.md`
and may only contain lowercase letters, digits and hyphens**, so install it as `seeten-draw`:

```bash
# Project-level (travels with the repo)
mkdir -p .claude/skills
cp -r /path/to/SeeTen .claude/skills/seeten-draw

# Personal-level (available in every project)
# Windows
xcopy /E /I SeeTen "%USERPROFILE%\.claude\skills\seeten-draw"
# macOS / Linux
cp -r SeeTen ~/.claude/skills/seeten-draw
```

After that, just describe what you want ("draw me a tile-schedule page for ...") and it will be
matched automatically, or invoke it explicitly with `/seeten-draw`.

> Keeping the directory named `SeeTen` is fine too — it simply won't be auto-discovered, but you
> can always tell the agent to read `SeeTen/SKILL.md` directly. The effect is the same.

### 2.2 Codex / OpenCode and other CLIs driven by `AGENTS.md`

These CLIs read an instruction file at the repository root. Add a pointer to `AGENTS.md`:

```markdown
## Drawing conventions (SeeTen)

Before drawing tensor / tiling / scheduling diagrams or presentation pages, read
`SeeTen/SKILL.md` and follow its hard rules. Take style parameters only from
`SeeTen/assets/*.json` and `SeeTen/references/style-spec.md`.
Generate pages with `SeeTen/scripts/seeten_draw.py` (requires python-pptx).
```

### 2.3 Kimi Code and other CLIs

Same pattern: point that CLI's project instruction file at the snippet above.
Instruction file names differ between tools (`AGENTS.md`, `KIMI.md`, `CLAUDE.md`, ...), so check
your CLI's docs or `--help` first. If it has no instruction-file mechanism at all, just say in
the conversation:

```
Read SeeTen/SKILL.md and draw a page for xxx following its conventions.
```

**Universal fallback**: any agent CLI can use this skill in full by putting the contents of
`SKILL.md` into context and allowing it to call `scripts/seeten_draw.py`.

### 2.4 Using it directly (no agent)

```bash
python scripts/seeten_draw.py examples/demo.pptx   # build the demo deck
python scripts/verify_demo.py examples/demo.pptx   # read it back and self-check
```

## 3. Quick start

```python
import sys; sys.path.insert(0, "SeeTen/scripts")
from seeten_draw import *

prs = new_deck("4:3")            # pick the canvas ratio first, never change it later
s = blank_slide(prs)
title(s, "Tiles and rounds")
text(s, 0.73, 1.22, "input: 2 cores, 3x3 tiles", size=16, w=13)

block_grid(s, 1.0, 3.0, fills, labels)                 # tile grid
task_matrix(s, 0.73, 6.0, ["C1", "C2"], rows)          # task matrix: rounds x cores
pseudocode_block(s, 0.73, 1.7, 9.6, ["for each (round r, core j):", "    ..."])
note(s, 0.73, 10.4, "The order is fixed, so the result is fixed.")

save(prs, "out.pptx")
print(check_layout(prs))         # must end with 0 out-of-bounds and 0 overlaps
```

Main API:

| Building block | Purpose |
|---|---|
| `new_deck(preset)` / `blank_slide` / `save` | Canvas (`4:3` / `16:9` / `16:10`) |
| `title` / `text` / `subtitle` / `note` | Titles, body text, captions (CJK/Latin runs get separate fonts automatically) |
| `block_grid` / `tensor_block` | Tile grid / single tile |
| `spec_table` / `round_table` / `accum_table` / `gantt_table` | Table archetypes |
| `task_matrix` | Task matrix (**rows = rounds, columns = cores**) |
| `trace_table` | Transposed view (**rows = cores, columns = rounds**): which column each core holds |
| `axis_grid` | (S1, S2) coverage grid with axis headers |
| `pseudocode_block` | Pseudocode block |
| `panel` / `panel_height` | Small captioned table (fills whitespace: comparison / numbers / intermediate form) and its height, to decide where it fits before drawing it |
| `arrow` / `axis_arrow` | Connectors / axis arrows |
| `lane_colors` / `text_on` | Lane color presets / pick text color from fill luminance |
| `check_layout` | Hard bounds check (text by real extent, tables by real width/height) |

## 4. Render and review (strongly recommended)

Numeric checks (`check_layout`) only prove "nothing is out of bounds and nothing overlaps".
**Whether the layout actually looks good requires looking at it:**

```powershell
# Needs WPS Office installed (uses its COM interface)
powershell -File scripts\render_deck.ps1 examples\demo.pptx
# Or, with LibreOffice
soffice --headless --convert-to png --outdir <dir> examples\demo.pptx
```

The PNGs land in `_render\` next to the pptx. Look through them page by page before adjusting.

## 5. Hard rules (read before you draw)

The full list is in `SKILL.md`. The ones that bite most often:

1. **Pick the canvas ratio first; nothing may cross the content box.** Keep 0.6 in on all four
   sides, run `check_layout` at the end — 0 out-of-bounds and 0 overlaps or it is not done.
2. **No large empty areas.** Fill them with comparison tables, cost numbers, or an intermediate
   form of the data — never with filler prose.
3. **Every page needs a title**; if there is a subtitle, put it below the title at a smaller size.
4. **A table's ownership label must hug its own table** (span only that table's width, plus a
   short tick line pinning it down).
5. **Explain the logic, don't cite code.** Put a pseudocode block before each example; no file
   names or line numbers on the page.
6. **Cell values must name the axis index** (`S1=2 S2=3`), not bare comma-separated numbers.
7. **Task matrices put rounds on rows and cores on columns.**
8. **Never use white text on a light fill** — let `text_on(fill)` choose the text color.

## 6. Cases

`cases/flash-attention-det-accum/` — a real scheme (deterministic gradient accumulation for an
Ascend FA backward kernel) drawn as schedule pages: Python implementations of seven task-index
algorithms, invariant checks, the drawing script, and the output pages. It demonstrates the
whole convention on a "rounds x cores x tiles" problem.

## 7. License

Internal material; no open-source license attached. Please check with the author before use.
