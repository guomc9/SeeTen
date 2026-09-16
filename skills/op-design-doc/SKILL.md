---
name: op-design-doc
description: 编写"算子详细设计 + 性能测试"Markdown 文档 —— 按固定章节骨架（需求分析 → 原型设计 → 特性实现 → Tiling/分核/内存 → 流水 → 测试设计）产出算子详设 .md；遇到 Markdown 表达不了的复杂表格（合并单元格、多级表头、跨行跨列）时，用 scripts/table_image.py 把 JSON 规格直出 PNG 图片嵌入。触发：算子详设、算子设计文档、算子性能测试报告、detailed design、详设模板、合并单元格表格、跨行跨列表格、表格转图片。
---

# 算子详设文档编写（op-design-doc）

产出一份**算子详细设计 + 性能测试**的 Markdown 文档。两类内容：
**设计叙述**（问题 → 方案 → 实现 → 资源/流水）与 **数据报告**（核时 / 分 pipe / 加速比）。
章节骨架与文风约定见 `references/doc-structure.md`；性能测试口径见
`references/perf-method.md`；可填空模板见 `templates/op-design-template.md`。

```
skills/op-design-doc/
  SKILL.md                        # 本入口
  references/
    doc-structure.md              # 八节骨架逐章写作规范（写什么、怎么写）
    perf-method.md                # 性能测试口径（计时方法、交错 A/B、漂移纪律）
  templates/
    op-design-template.md         # 可填空的完整模板（复制后逐节替换）
  scripts/
    table_image.py                # 复杂表格 JSON → PNG（合并单元格/多级表头）
  examples/
    branch-table.json             # 普通表格示例（v2-stream dQ 收尾分支）
    merged-table.json             # 跨行跨列示例
```

## 什么时候用它

- 要给一个算子 / kernel 方案写**正式设计文档**（详设）+ 性能测试报告（.md）；
- 文档里有 Markdown 原生表格表达不了的表格：**合并单元格、多级表头、跨行跨列、
  需要配色语义的表格** —— 用 `scripts/table_image.py` 出 PNG 嵌入；
- 需要把已有的性能数据（msprof 核时、分 pipe、多版本对比）整理成规范章节。

不适用：纯 PPT 汇报页（走 seeten-draw skill）；无设计内容的纯性能数据贴（直接给表）。

## 文档骨架（固定八节，顺序不要换）

```
标题 = 算子/方案名 + 版本分支
1. 需求分析     —— 问题是什么、为什么必须解决（功能分析）
2. 原型设计     —— 接口、输入输出、开关参数（如 deterministic）
3. 特性实现方案 —— 核心机制：计算逻辑（Cube/VEC 分工）、小而典型的案例、逐步推演
4. Tiling 切分  —— 数据布局、轴序、切分规则
5. 分核策略     —— 任务怎么铺到核上（调度）
6. 片上内存资源设计 —— workspace / L1 / UB / L0C 布局与预算
7. 流水设计     —— 阶段衔接、旗标/同步、重叠设计（前后方案对比）
8. 测试设计     —— 正确性验证 + 性能测试（口径、矩阵、结果、结论）
```

逐章写法见 `references/doc-structure.md`。**先写"小而典型的案例"再写一般规则**
（例子的做法：b=1、n2=1、g=1、S1/S2 各两三块，把累加过程逐轮写出来）。

## 工作流

1. **收集素材**：算子代码（kernel/tiling/调度）、接口定义、已有 profiling/性能数据、
   相关历史文档。性能数据若需新测，口径按 `references/perf-method.md`
   （msprof Task Duration、median of 25、交错 A/B、同会话漂移纪律）。
2. **复制模板** `templates/op-design-template.md` 为目标 `.md`，逐节替换占位。
   图片统一放目标文档旁的 `figs/` 子目录，引用相对路径 `figs/xxx.png`。
3. **复杂表格出图**：凡是 Markdown 表格写不下的（合并单元格/多级表头/跨行跨列/
   需要底色语义），把表格写成 JSON 规格（见 `examples/*.json` 与脚本 docstring），
   跑 `python scripts/table_image.py spec.json figs/xxx.png`，在 .md 里
   `![表格标题](figs/xxx.png)`。**简单表格（无合并、无配色）直接用 Markdown 表格，
   不要出图**（保持可 diff、可检索）。
4. **自检**（见下）后交付。

## 表格出图约定（table_image.py）

- 输入：JSON 规格。`header` / `rows` 为二维数组，每个单元格
  `{"t": 文本, "span": {"r": n 或 "c": n}, "fill": "RRGGBB", "color": ..., "bold": true}`；
  `span` 缺省 = 单格；`col_w` 列宽（英寸）；`size` 字号；`zebra` 隔行浅色。
- 文本过长自动按列宽折行（不在英文标识符中间断开）；`\n` 手动换行。
- 字体：自动找 CJK（`~/.seeten/fonts/` 下 NotoSansCJKsc / HeiTi，缺失时自动下载），
  也可用 spec 的 `"font": "<ttf/otf 路径>"` 指定。
- 图片风格：表头浅蓝底、隔行 zebra、细边框 —— 与 seeten 系列图风格一致；
  需要强调语义的格子用 `fill`（如 `F5EBD2` 卡其、`DCE6F7` 浅蓝）。

## 自检清单（交付前逐项过）

1. **结构**：八节齐全、顺序正确；标题含算子/方案名与分支版本。
2. **数字可回读**：文中每个性能数字都能在附录数据源（脚本输出/CSV）里找到；
   性能口径（计时方法、warmup/repeat、median）在测试节写明。
3. **图文一致**：图片文件存在于 `figs/`、与正文引用一致；表格图片内容与正文描述一致。
4. **术语口径**：与项目现行口径一致（如 `causal / dense`；布局名 BSND/TND；
   轴名 b/n2/g/s1/s2/d 全小写）。
5. **案例可复现**：小案例的输入形状、分块数、每轮任务/累加式子全部具体写出，
   读者能照着推演。
6. **不过度装饰**：能 Markdown 表格的不出图；图片只放必须合并/配色的表格。
