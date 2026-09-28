# Case：IndexSelect（行 gather）SIMT 执行体 ↔ 数据对应图

一句话：6 页图说清 5 个 SIMT 变体的**分工方式**——哪个执行体搬哪块数据、warp 每步
事务多宽。源图从一份外部参考 PPTX 迁移而来，本目录固化迁移方法与画法规则。

## 图集（figs/）

| 文件 | 内容 |
|---|---|
| `gather_addressing.png` | 语义图：Src（M×K）— Index（N）— Dst（N×K），虚线箭头成对 |
| `variant_basic.png` | basic：每线程一整行 |
| `variant_coalesced.png` | coalesced：每 block 一行，4B 步进 |
| `variant_16B.png` | 16B：每 block 一行，float4 步进 |
| `variant_seg16B.png` | seg_16B：每 warp 负责行内一段（512B 对齐） |
| `variant_stream.png` | 16B_stream：输出展平后的全局顺序流（左右对比面板） |

## 画法规则

### 1. 三段式布局（固定）

```
Src (GM) 矩阵          执行体竖条             Dst (GM) 矩阵
[M 行 x K 列]   虚线→  T0..T5 + Registers  →虚线  [N 行 x K 列]
   ↓ 实线              ↕ 实线                     ↓ 实线
[L2 Cache 灰盒] ←—— 横向实线 ——→            [L2 Cache 灰盒]
```

- 矩阵 = 原生表格，**每格写该行内容值**（行号即可）；行填充用同一条蓝色阶梯，
  Dst 行颜色 = 它的源行颜色，gather 映射不看箭头也能读出。
- index 列夹在中间：竖列、绿色阶梯、格内写行号。
- 中间执行体竖条：basic 用 Thread（T0..T5…），其余用 Block（B0..B5…）；
  每行右侧挂一个浅紫 Registers 格 = 一步的寄存器事务。

### 2. lane / warp 分工 = 矩阵首行（本案例最关键的表达）

Src 和 Dst 的**首行不画数据，画分工标签格**；标签的**重复周期 = 该执行体在行内
推进一轮占的列数**：

| 变体 | 首行标签 | 周期语义 |
|---|---|---|
| basic（每线程一行） | 不画分工行（首行仍是数据） | 线程整行负责，行内无交错 |
| coalesced（每 block 一行） | `T0 T1 … T31 T0 T1 …` | lane 级交错，周期 = blockDim |
| 16B（float4 步进） | `W0 W1 W2 W3 W0 …` | warp 级，周期 = blockDim/32 |
| seg_16B（行内分段） | `W0 W0 W1 W1 W2 W2 …` | **同一 warp 连续两格 = 段内独占** |
| stream（展平顺序流） | 整面顺序 `W0..W15` + 左缘 SM0/Iter 纵条 | 全局顺序扫描，不分行内段 |

标签格紫色梯度白字；数据格蓝阶梯白字；填充要够深，白字优先。

### 3. 两套箭头，别混用

- **虚线** = 数据归属：`Src 行 → 执行体`、`执行体 → Dst 行`，允许交叉扇出。
- **实线** = 访存流向：矩阵 → 下方 L2 Cache 灰盒（向下）；执行体 ↔ L2（横向）；
  Warp 内每步 GM ↔ Registers（横向短箭头，旁标 T1/T2 步次）。

### 4. 量化注记（底部一句话，必写）

把合并效果写死在图里：
`单个 Warp 每次在 L2 读写 4B×32 = 128B 数据`（16B 版则为 `16B×32 = 512B`）。

### 5. 文档配图版式（本案例实测）

1. 中文标题（22pt 粗）→ 实测定位表（表外标题 + 项/结论两列）→ 红色粗体要点一行
   → 三段式示意图。
2. 页内垂直节奏：标题 y≈0.3，表头 y≈1.0（panel 表体 0.42 in/行），要点贴表尾，
   示意图整体平移到 y≈3.3 起点；画布高度 = 平移后 max bottom + 0.3 in。

## 从外部 PPTX 迁移此类页（migrate_ref_figures.py）

```bash
python cases/index-select-simt/migrate_ref_figures.py <参考.pptx>
```

步骤：复制 deck 只留目标页 → 删原英文标题（顶部宽文本框）与代码段（含 `//`、
`int ` 等的顶部文本框）→ 量剩余形状 min/max top → **先整体平移原图到目标起点，
再叠加自己的标题/表/注记**（顺序反了会把自己加的件一起挪走）。

参考 PPTX 是私人素材、不入库；脚本里 `SRC` 改为命令行传入。迁移产物（pptx/png）
用 LibreOffice 转 PDF、PyMuPDF 出 PNG（110 dpi），逐张看图验收。
