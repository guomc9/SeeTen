# Case study: schedule pages for deterministic gradient accumulation

**English** | [中文](README.zh-CN.md)

A **real scheme page** case study drawn with the SeeTen conventions: the "deterministic gradient
accumulation" scheme of an Ascend FA backward kernel. In the backward pass, the gradient of one
dK/dV tile is accumulated from several tiles along the S1 axis, and those tiles are spread across
cores to be computed in parallel. A non-deterministic implementation lets every core do an
atomic add into shared memory as soon as it finishes — who adds first is decided by the hardware
scheduler, and floating-point addition is not associative, so results can differ between runs.

This scheme takes the **schedule-first** route: assign tasks up front so that one core owns a
single KV column for several consecutive rounds and walks through S1 inside it. dK/dV are then
accumulated by a single core in program order, which makes the result deterministic by
construction.

## What this case demonstrates

| General technique | How it shows up here |
|---|---|
| Table as a tensor canvas | Tile grid: cells are tiles, color is ownership, cell text is the tile id |
| Task matrix (rounds × cores) | Rows are rounds, columns are C1..Ck, cells read `S1=2  S2=3` |
| Coverage grid on the (S1, S2) plane | Position is the coordinate, cell text is the round, color is the core; a `plain` column-private grid shows traversal order when nothing is being encoded |
| Pseudocode first | Every page leads with pseudocode written with concrete names, then the example |
| Two-level color | Hue = which batch, shade of the same hue = which KV column (S2); S1 does not drive color |
| Transposed trace table | Rows are cores, columns are rounds, cell = the column that core holds that round — reads "why the same S2 shows up on several cores" straight off the page |
| Concept page for an abstraction | The fold's "virtual column" gets its own page: two real triangles -> one rectangle, a table of which real cells each virtual column is made of, and a plain-vs-virtual comparison |
| Rule-selection table | Dense Swizzle vs Dense Index compared by which axis the low task-id digit walks, and when to pick each |
| Fill whitespace with real tables | Comparison table (which rule applies to this shape), cost numbers, per-core column list; placed by priority into whichever column has room |
| Ownership labels hug their table | `B=1`, `N2=1`, `G=1` span only their own grid and sit right on top of it |

## Files

| File | Purpose |
|---|---|
| `index_schedules.py` | Python implementations of the seven task-index algorithms + three invariant checks |
| `draw_case.py` | Draws the case pages using `scripts/seeten_draw.py` |
| `out/v4-index-schedules.pptx` | The generated pages (18: overview + axis walkthrough + virtual-column page + 7 methods x 2 + a harder non-square causal example) |

```bash
python index_schedules.py          # check the seven algorithms first (expect zero conflicts)
python draw_case.py out/v4-index-schedules.pptx   # generate the pages
```

## The seven index algorithms

Each takes "which round + which core" and returns "which tile that core computes this round"
(batch / head / group / S1 / S2). They are pure scalar integer arithmetic — the result for a
given (round, core) is always the same, which is exactly where determinism comes from.

| # | Algorithm | In one sentence | Example size | Result |
|---|---|---|---|---|
| 1 | Column-private swizzle | Low digit is the KV column: one core owns a column for m rounds and walks S1 inside it | k=2, 3×3 tiles, 2 batches | 9 rounds, filled; 3 columns per core |
| 2 | Batch-first splitting | Low digit is the batch: cores land on different batches in the same round, so core count may exceed the S1 tile count | k=4, 2×2 tiles, 2 batches | filled in 2 rounds |
| 3 | Causal folding | Two adjacent batches are folded into one full rectangle; the two triangles fit exactly | k=2, 3×3 tiles, 2 batches | 12 tasks, zero idle slots |
| 4 | Left-up causal folding | Its own geometry when S1 is longer than S2; virtual height = 2m-n+1 | k=2, 3×2 tiles, 2 batches | 10 tasks, 4 need masking |
| 5 | GQA slicing | One core owns R consecutive task ids; a gcd correction keeps same-round keys distinct | k=2, 2×2 tiles, group 2 | 4 rounds, 8 tasks |
| 6 | Ragged column-private | Per-batch round prefix; column-private inside a batch; batches may need different round counts | k=2, unequal lengths | 12 tasks + 2 idle |
| 7 | Ragged flattening | Flatten by area prefix, split into k slices, scan each in order | k=2, group 2 | 12 tasks, zero idle |

## The three invariants checked

`check()` in `index_schedules.py` verifies, for every example:

1. **No duplicate tasks** — the same (batch, head, group, S1, S2) is never produced by two
   (round, core) pairs;
2. **No S1 collision within a round** — no two cores write the same output tile in the same
   round, which is what allows the cross-core atomic add to be ordered;
3. **Column-private** (swizzle-style algorithms) — a core owns one column across consecutive
   rounds and walks through S1 inside it without repetition.

All seven pass at the sizes above (0 duplicates, 0 conflicts). The GQA-style variants (5 and 7)
are deliberately *not* column-private: they rely on flattened slicing plus distinct same-round
keys instead. That is a design choice, not a defect.

## Known pitfalls

- For algorithm 4 (left-up causal folding), the `m > n` branch is **never selected by the
  current selector** — it is only chosen when S1 and S2 are the same length, and that path
  delegates to algorithm 3. The page says so explicitly; don't mistake it for a live code path.
- Shortcuts such as "skip the reduction when only one tile contributes" **do not exist** in the
  reference implementation (it always goes seed → reduce → single atomic add). Don't copy an
  imagined optimization into a diagram.
