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
| Performance comparison pages (optional) | Three pages — determinism penalty (det/nd), det-vs-det, nd-vs-nd — each with a wide matplotlib figure (all 8 shapes) in the DeepSeek palette, a matching kernel-time (msprof, not event record) table and reading notes |

## Files

| File | Purpose |
|---|---|
| `index_schedules.py` | Python implementations of the seven task-index algorithms + three invariant checks |
| `draw_case.py` | Draws the case pages using `scripts/seeten_draw.py` |
| `check_case.py` | Content self-check: matrix readback vs algorithms, printed-formula replay, claim cross-checks |
| `out/v3-index-schedules.pptx` | The generated pages (21: overview + axis walkthrough + virtual-column page + 7 methods x 2 + a harder non-square causal example + three performance comparison pages) |

```bash
python index_schedules.py          # check the seven algorithms first (expect zero conflicts)
python draw_case.py out/v3-index-schedules.pptx   # generate the pages
python check_case.py out/v3-index-schedules.pptx  # matrix + formula + claim self-check
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
| 4 | Left-up causal folding | S1 = S2: delegates to the square fold (page 5). S1 > S2: its own geometry, virtual height = 2m-n+1 (page 5b) | S1 = S2: k=2, 3×3 tiles; S1 > S2: k=3, 4×3 tiles | 12 tasks zero idle / 18 tasks zero idle |
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

- **Algorithm 3 (Causal Swizzle) is never selected directly** — it is only an internal delegate
  of algorithm 4 (Left-Up), which itself is only selected when the batch count is even and
  S1 = S2. The pages carry a reachability tag (`↪ 仅 Left-Up 内部委托` / `★ 偶 batch 且 S1 = S2`).
- For algorithm 4 (left-up causal folding), the `m > n` branch is **never selected by the
  current selector**: page 5b draws its geometry, and the page explicitly says so
  (`⚠ 选择器不会走这一支`). Only the S1 = S2 path is reachable.
- **GQA column splitting is conditional, not guaranteed.** Whether the g contributions of one
  KV column (`b, n2, s2`) land on the same core depends on `R` vs `g` alignment (and on the
  gcd correction). The 2-core example happens to be single-core per column, so the pages say
  "not guaranteed to share a core" instead of "always spans cores".
- Shortcuts such as "skip the reduction when only one tile contributes" **do not exist** in the
  reference implementation (it always goes seed → reduce → single atomic add). Don't copy an
  imagined optimization into a diagram.
- Capital-heavy headers (`MHA/GQA`) need ~20% extra width beyond the estimate: renderers
  measure wider than the estimator and clip both ends of the string.
- Performance comparison pages: one comparison class per page (determinism penalty /
  det-vs-det / nd-vs-nd), full-shape axes, legend states the plotted quantity
  (`opst / ours det cost`), ratio charts colour values below 1 gray, and kernel time comes
  from profiling only — never event-record timings.
- Keep >= 0.15 in between tables/figures and their neighbours (`check_gaps`); when panels
  stop fitting, split pages or drop auxiliary panels instead of tightening the gaps.
