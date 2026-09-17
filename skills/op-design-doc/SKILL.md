---
name: op-design-doc
description: 编写"算子详细设计 + 性能测试"Markdown 文档（两种体裁：单版本详设；版本演进的性能优化文档）—— 详设按固定章节骨架（需求分析 → 原型设计 → 特性实现 → Tiling/分核/内存 → 流水 → 测试设计），优化文档按（背景目标 → 方法论 → 优化项 → 负结果台账 → 评测 → 结论）；配图用 LibreOffice 真渲染 pptx 页面（scripts/render_pptx.py）或复杂表格直出 PNG（scripts/table_image.py）。触发：算子详设、算子设计文档、算子性能测试报告、性能优化文档、版本演进、负结果台账、detailed design、详设模板、合并单元格表格、表格转图片、pptx 转图片。
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
    doc-structure.md              # 八节骨架逐章写作规范 + 写作风格/数据表约定
    perf-method.md                # 性能测试口径（计时方法、交错 A/B、漂移纪律）
    pptx-render.md                # ★ pptx 页面 → 图片的真渲染管线（配图必读）
  templates/
    op-design-template.md         # 详设模板（单版本：需求→原型→实现→…→测试）
    op-perf-opt-template.md       # 性能优化文档模板（版本演进：目标→方法论→优化项→
                                  #   负结果台账→评测→结论；见 references/doc-structure.md）
  scripts/
    table_image.py                # 复杂表格 JSON → PNG（合并单元格/多级表头）
    render_pptx.py                # pptx → PNG（LibreOffice headless + PyMuPDF；含抽内嵌图）
    pptx_tweaks.py                # pptx 预处理：去标题页号 / 蓝格白字加粗
  examples/
    branch-table.json             # 普通表格示例（v2-stream dQ 收尾分支）
    merged-table.json             # 跨行跨列示例
```

## 什么时候用它

- 要给一个算子 / kernel 方案写**正式设计文档**（详设）+ 性能测试报告（.md）；
- 要写**性能优化文档**：版本演进（v0→v1→v2）、每个优化项的问题/方案/正确性/收益、
  以及"试过但关闭"的**负结果台账**（模板 `templates/op-perf-opt-template.md`）；
- 配图：把已有演示文件的页面**真渲染**成图片嵌入（`references/pptx-render.md`）；
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

0. **判断体裁**：单版本方案 → 详设（`templates/op-design-template.md`）；
   版本演进/优化过程 → 性能优化文档（`templates/op-perf-opt-template.md`，
   其骨架与收益/比值写法见 `references/doc-structure.md`）。
1. **收集素材**：算子代码（kernel/tiling/调度）、接口定义、已有 profiling/性能数据、
   相关历史文档。性能数据若需新测，口径按 `references/perf-method.md`
   （msprof Task Duration、median of 25、交错 A/B、同会话漂移纪律）。
2. **复制模板** 为目标 `.md`，逐节替换占位。表格尽量**由脚本从原始数据直出**。
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
2. **自包含**：不出现"详见 / 参见某个演示文件"的交叉引用；被引用的页面内容以
   **真渲染图片**纳入正文；伪代码/面板若已含在页面图内，正文不再重复抄写。
3. **版本纪律**：一份详设只描述一个版本；后续改进版本另写《性能优化》文档，
   本文不出现改进版本代号与相关表格。
4. **数字可回读**：性能数字均可在附录数据源找到；计时口径（msprof / median / A/B）写明。
5. **图文一致**：图片存在且与正文引用一致；页面图来自真渲染（箭头、字体完整）。
6. **术语口径**：与项目现行口径一致（如 `causal / dense`；轴名 b/n2/g/s1/s2/d 小写）。
7. **案例可复现**：小案例的形状、分块数与每轮任务/累加式子具体写出，可照着推演。
8. **机制断言先对代码核实**：写"怎么算/怎么写"之前回读实现（曾把"每 task 落盘"
   误写成"列内 L0C 连续累加"）。
9. **不过度装饰**：简单表格用 Markdown；用例表拆列（b/n2/g/s2/s1/d/mask），
   重复段长用 `n×v` 简写；表格配色彩克制（白/灰斑马即可）。
