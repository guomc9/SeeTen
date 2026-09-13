---
name: seeten-draw
description: 用原生 PPT 表格当"张量画布"画张量分块与任务调度示意图 —— 单元格 = 分块，填充色 = 语义，格内写清是哪个轴的哪个索引；再配伪代码块、任务矩阵、覆盖图、流水甘特表。当需要把"分块累加 + 核间同步"这类算子方案画成 PPT 页面、张量块表格、数据流示意图、调度矩阵时使用；也用于把一段 kernel 逻辑讲成"块 + 核 + 轮次"。触发词：张量表格、块网格、数据流图、调度矩阵、流水甘特、伪代码块、python-pptx 画图。
---

# SeeTen —— 张量表格绘制

把"分块 + 核 + 轮次"这类并行方案的逻辑画成 PPT 页面：
**原生 PPT 表格当张量画布**，格子 = 分块，填充色 = 语义，格内写轴的索引，
数据流用带箭头的连接线，逻辑用伪代码块先讲清楚。

```
SeeTen/
  README.md / README.zh-CN.md   # 安装与使用（英文为主，中文见 .zh-CN）
  package.json / bin/ / lib/    # npm CLI `seeten`：装 skill + 备 Python 依赖（零 npm 依赖）
  SKILL.md                      # 你正在读的入口
  references/
    style-spec.md               # 实测风格规范：画布/色板/字体/几何/表式原型
    diagram-recipes.md          # 各类图的画法配方 + 画前自检清单
  scripts/
    seeten_draw.py              # python-pptx 生成库（推荐入口：直接调 API）
    verify_demo.py              # 回读生成结果做自检（表样式/边框/字体/CJK 字体）
    render_deck.ps1             # 把 pptx 导成 PNG，供逐页看图改版式
  assets/
    palette.json                # 实测色板与几何常量（EMU 原值）
    color-sets.json             # lane 配色预设 + 伪代码块配色
  examples/
    demo.pptx                   # 通用演示（由 seeten_draw.py 的 demo() 生成）
  cases/                        # 案例：用这套规范画出来的真实方案页
```

## 什么时候用它

- 要把一个并行算子的方案画成页面：**哪个核算哪一块、第几轮算、怎么累加**；
- 要把一段 kernel 逻辑画成"块 + 核 + 轮次"的示意图；
- 要画任务调度矩阵（轮 × 核）、(S1, S2) 覆盖图、流水甘特表、算子级数据流图。

## 怎么用

0. **环境（第一次用才需要）**：`npx github:guomc9/SeeTen init` —— 一条命令把 skill 装到
   agent CLI 的目录、并在 `~/.seeten/venv` 备好 python-pptx。装完用 `seeten doctor` 自检。
   环境就绪后，绘制脚本统一用 `seeten draw <脚本.py> <输出.pptx>` 跑（它会自动挂好环境）。
1. **先读规则**：`references/style-spec.md` 定死了画布、版心、色板、字号、表式；
   `references/diagram-recipes.md` 开头是通用规则，后面是各类图的配方。
2. **选配方**：从 `diagram-recipes.md` 挑最接近的一张，照它的坐标和表式画。
3. **取参数**：字号/行高/列宽/颜色只从 `assets/palette.json`、`assets/color-sets.json`
   和 `style-spec.md` 取，不要自己另定。
4. **生成**：
   ```python
   import sys; sys.path.insert(0, r"<SeeTen>\scripts")
   from seeten_draw import *
   prs = new_deck("4:3"); s = blank_slide(prs)
   title(s, "分块与轮次")
   block_grid(s, 1.0, 3.0, fills, labels)          # 块网格
   tensor_block(s, 1.52, 5.59, "B0", GROUP0)       # 单个分块
   task_matrix(s, 0.73, 6.0, cores, rows)          # 轮 x 核
   note(s, 0.73, 10.1, "一句话要点")                # 图注
   save(prs, "out.pptx")
   ```
   ```powershell
   seeten draw --demo examples\demo.pptx    # 通用演示（用提前备好的环境）
   seeten render examples\demo.pptx         # 导出 PNG 逐页看图
   seeten doctor                            # 环境出问题时先跑这个
   ```
   没装 CLI 的话，等价的手工命令是 `python scripts\seeten_draw.py examples\demo.pptx`
   （需先 `pip install python-pptx`）。
5. **自检**：跑 `verify_demo.py` 确认表样式已剥离、边框/字体/CJK 字体在位。
6. **渲染看一眼（必做，别只靠数字判断版式）**：
   ```powershell
   seeten render examples\demo.pptx
   # 或直接用脚本：powershell -File scripts\render_deck.ps1 examples\demo.pptx
   ```
   它用本机 WPS 的 COM 接口（`KWPP.Application`）把每页导成 PNG 到同级 `_render\`，
   然后用 Read 工具**逐页看图**改版式 —— 空白是否过多、标记是否贴错表、字号是否被挤，
   这些只有看到图才知道。装了 LibreOffice 的话等价命令：
   `soffice --headless --convert-to png --outdir <dir> <pptx>`。

## 硬规则（每次画图都必须满足）

1. **画布先定，内容不许越界。**
   比例从 `sd.CANVAS_PRESETS` 里选（`4:3` 默认 / `16:9` / `16:10`），**一旦选定就不再改**。
   所有文字和表格必须落在版心内（四边留 0.6 in）。收尾跑 `sd.check_layout(prs)`：
   文字按字号算实际占位、表格按真实列宽行高算外框，`0 越界 / 0 重叠` 才算画完。
2. **不留大块空白。** 留白处要补**有用的**表，不是用废话填空。可选补法：
   对比表（换一种做法会怎样）、代价数字（任务总数/总槽位/空泡）、中间形态（如折叠前
   后的那张表）、对象说明（每个核负责哪些列）。
3. **每页都要有标题；有子标题就放在标题下方、字号更小。**
   标题 30 pt（`sd.title`，y=0.62）；子标题 16 pt `#333333`（`subtitle`，y=1.22）；
   正文从 y≈1.68 开始。
4. **表格的归属标记要紧贴自己的表。** `B=1` 这类标记只占**自己表格的宽度**、贴在表格正上方，
   并用一小段竖线钉住表格。同名标记宁可短，也不要悬在两张表中间。
5. **讲逻辑，不给代码位置。** 例子前先放**伪代码块**（`sd.pseudocode_block`，浅灰底 + 等宽字 +
   注释灰 + 关键字蓝），说清每一步在做什么；页面上不出现文件名、行号、函数引用。
6. **不许拿抽象堆砌。** 能用具体例子说清的就不要引入新符号。伪代码用「任务号 / 第几列 / 第几批」
   这类具体名字，不要 p、w、x、y 满屏。
7. **表项要写清是哪个轴的哪个索引。** 格内写 `S1=2  S2=3` / `B=1 N2=1 G=1`，
   **不要**写成逗号或分号分隔的裸数字。轴的含义放在表格外面的小面板里。
8. **任务矩阵：轮数是纵轴，核数是横轴。** 行 = 第 N 轮，列 = C1..Ck（`sd.task_matrix`）。
9. **配色用预设色组。** 从 `assets/color-sets.json` 的 `lane_sets` 选一套：
   `cool`（默认，低饱和冷色）/ `deck`（深色高对比）/ `clay`（暖色）/ `mist`（极简蓝灰）。
   每色自带文字色，避免浅底压白字；空位用 `hole` 灰。
10. **解释文字放表格外面。** 一行一句、越短越好；表格区域只放表格。
    一个主题可以跨页：算法页讲逻辑（伪代码 + 任务矩阵），例子页给数值（覆盖图 + 读法）；
    轴用 `sd.axis_arrow` 标，元素关系用 `sd.arrow` 少量点缀。
11. **术语不硬译。** `swizzle` / `layout` / `causal` / `mask` / `task id` / `idle` /
    `fold` / `buffer` / `lane` / `tile` / `workspace` 这类词直接用英文，解释句用中文 ——
    硬翻出来的中文比英文更难懂。页面上**不要写 Markdown 记号**（`**加粗**` 会原样显示星号）。
12. **标题带序号**（`1.` `2.` …），并按页序组织；每条规则要**标清适用场景**：
    用 `sd.tag_row(...)` 打一行标签（layout / causal / 头型 MHA-GQA / 是否列私有 之类），
    别让读者自己猜这条规则适用于什么形状。
13. **光给结果不够，要讲"为什么这么分"。** 表格里同一个轴的值会在不同 lane 上重复出现
    （比如同一个 S2 出现在多条 core 的任务里），必须结合**遍历顺序 / 计算流程**解释清楚：
    task id 先走哪个轴、为什么这样走、于是哪些值会重复 —— 在矩阵下面用 2~3 行说明。
14. **颜色别只做一级区分。** 只按 lane 上色时，同一条 lane 的多个任务长得一模一样，
    分不出先后。同一条 lane 的任务再用**同色相的深浅**区分（`sd.lane_shades`：
    色相 = 哪条 lane，深浅 = 第几个任务），并在图例里写明"越深越靠前"。

**收尾三件事，缺一不算画完**：
① `sd.check_layout(prs)` 0 越界 0 重叠 → ② `verify_demo.py` 表样式/字体回读一致 →
③ `render_deck.ps1` 渲染后逐页看图，凭视觉再调一轮版式。

## 风格地基（复刻这套观感时不变的部分）

- **一页一套配色语义**：要么"分组色"（区分不同归属），要么"操作数色"（区分不同张量），
  要么"lane 色"（区分不同核）。不要混用。
- **中英分 run**：ASCII 用 `Times New Roman`，中文用 `Noto Sans SC`，并且要写 `a:ea`
  （库里的 `text()` / `_write_cell_lines()` 已自动处理）。
- **几何照抄实测值**：单元格 0.670 × 0.660 in，边框 `#DDDEDF` 1 pt，表格不带 `tableStyleId`。
  这几项是这套风格"手感"的来源。

## 与其他 skill 的关系

本 skill 只负责**画法**（风格 + 配方 + 生成器），不做完整的 PPTX 工程流程
（模板/母版/封面/动画）。需要整本 deck 的生成、模板填充、视觉重建时交给 `ppt-master`，
本 skill 作为它的"张量页"素材来源。
