# SeeTen —— 张量表格绘制

[English](README.md) | **中文**

把"分块 + 核 + 轮次"这类并行方案的逻辑画成演示页面。
核心手法：**原生 PPT 表格当张量画布** —— 一个单元格 = 一个分块，填充色编码语义，
格内写清"是哪个轴的哪个索引"；再用伪代码块讲逻辑、用带箭头的连接线画数据流。

它同时是一份**实测过的风格规范**：画布、色板、字体、几何全部有确切数值，
按它画出来的页面观感统一，不会每页一个样。

```
SeeTen/
  package.json / bin/ / lib/    # npm CLI `seeten`：装 skill + 备 Python 依赖
                                #   （零 npm 依赖，只用 Node 内置模块）
  SKILL.md                      # 技能入口：什么时候用、硬规则、怎么用
  references/
    style-spec.md               # 实测风格规范：画布/色板/字体/几何/表式原型
    diagram-recipes.md          # 各类图的画法配方 + 画前自检清单
  scripts/
    seeten_draw.py              # python-pptx 生成库（核心）
    verify_demo.py              # 回读生成结果自检（表样式/边框/字体）
    render_deck.ps1             # 把 pptx 导成 PNG，供逐页看图改版式
  assets/
    palette.json                # 实测色板与几何常量（EMU 原值）
    color-sets.json             # lane 配色预设 + 伪代码块配色
  examples/demo.pptx            # 通用演示（2 页）
  cases/                        # 案例：用这套手法画出来的真实方案页
```

---

## 1. 安装（一条命令）

```bash
npx github:guomc9/SeeTen init
```

这一条命令会：

- 把 skill 装到你的 agent CLI 的 skill 目录（自动识别 `.claude/`、`AGENTS.md`、`CLAUDE.md`、`KIMI.md`）；
- 备好 `python-pptx` —— 系统 Python 已经装了就直接复用，没装就在 `~/.seeten/venv`
  建独立环境（**不动你的系统环境**）；
- 生成一份演示 deck 并跑版心自检，有问题当场就能看到；
- 报告 PNG 导出（WPS / LibreOffice）能不能用，也就是"渲染看图"这步可不可行。

机器上需要 **Node 18+** 和 **Python 3.8+**，其余都由它处理。
不需要 npm 账号、不需要先发布 —— `npx github:` 直接从仓库装。

| 命令 | 作用 |
|---|---|
| `seeten init [--global] [--no-demo]` | 装 skill + 备 Python 依赖 + 冒烟测试 |
| `seeten draw <脚本.py> [输出.pptx]` | 用同一套环境跑你的绘制脚本 |
| `seeten draw --demo [输出.pptx]` | 生成通用演示 deck |
| `seeten render <文件.pptx>` | 导出 PNG，逐页看版式 |
| `seeten doctor` | 自检：装了什么、还缺什么 |

`seeten draw` 会把 skill 的 `scripts/` 挂到 `PYTHONPATH` 上，所以你的脚本只要写
`from seeten_draw import *` 就行。

## 2. 手动安装（各 CLI 细节）

上面那条命令是推荐路径。这一节是它替你做的事 —— 如果你想自己接线，或者用的是比较特别的
CLI，就看这里。

这个 skill 是**文件目录形态**的：不绑定任何 CLI，只要那个 CLI 能读文件、能跑 Python 就能用。
所以"安装"= 让 agent 知道 `SKILL.md` 在哪，并允许它执行 `scripts/` 下的脚本。

手工装的话，Python 那边也要自己准备：

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install python-pptx
# macOS / Linux
.venv/bin/python -m pip install python-pptx
```

### 2.1 Claude Code（原生 skill 机制）

Claude Code 会把 `<项目>/.claude/skills/<名字>/SKILL.md` 和
`~/.claude/skills/<名字>/SKILL.md` 自动识别为 skill。**目录名必须与 `SKILL.md` 里的
`name` 一致，且只能用小写字母、数字、连字符**，所以安装时把目录名改成 `seeten-draw`：

```bash
# 项目级（跟着仓库走）
mkdir -p .claude/skills
cp -r /path/to/SeeTen .claude/skills/seeten-draw

# 个人级（所有项目都能用）
# Windows
xcopy /E /I SeeTen "%USERPROFILE%\.claude\skills\seeten-draw"
# macOS / Linux
cp -r SeeTen ~/.claude/skills/seeten-draw
```

装好后：直接说需求（"帮我画一页 xxx 的分块调度图"）会被自动匹配；
也可以显式调用 `/seeten-draw`。

> 只想保持 `SeeTen` 这个目录名也行 —— 那样不会被自动发现，但可以让 agent 直接读
> `SeeTen/SKILL.md`，效果一样。

### 2.2 Codex / OpenCode 等以 `AGENTS.md` 为指令文件的 CLI

这类 CLI 会读项目根目录的 `AGENTS.md`。在 `AGENTS.md` 里加一段指路：

```markdown
## 绘图规范（SeeTen）

画张量/分块/调度类示意图、PPT 页面时，先读 `SeeTen/SKILL.md` 并遵守其中的硬规则；
风格参数一律从 `SeeTen/assets/*.json` 与 `SeeTen/references/style-spec.md` 取。
生成脚本用 `SeeTen/scripts/seeten_draw.py`（需要 python-pptx）。
```

### 2.3 Kimi Code 及其他 CLI

同一个套路：把你那个 CLI 的"项目指令文件"指向上面的片段即可。
不同 CLI 的指令文件名不一样（`AGENTS.md`、`KIMI.md`、`CLAUDE.md` 等），
先看它的文档或 `--help` 确认；实在没有指令文件机制，就在对话里直接说：

```
读 SeeTen/SKILL.md，按它的规范和脚本画一页 xxx。
```

**通用兜底**：任何 agent CLI，只要把 `SKILL.md` 的内容贴进上下文、并允许它调用
`scripts/seeten_draw.py`，就能完整使用本 skill。

### 2.4 直接用（不经过 agent）

```bash
python scripts/seeten_draw.py examples/demo.pptx   # 生成演示 deck
python scripts/verify_demo.py examples/demo.pptx   # 回读自检
```

## 3. 快速上手

```python
import sys; sys.path.insert(0, "SeeTen/scripts")
from seeten_draw import *

prs = new_deck("4:3")            # 画布比例先定，之后不改
s = blank_slide(prs)
title(s, "分块与轮次")
text(s, 0.73, 1.22, "输入：核数 2 · S1 分 3 块 · S2 分 3 块", size=16, w=13)

block_grid(s, 1.0, 3.0, fills, labels)                 # 块网格
task_matrix(s, 0.73, 6.0, ["C1", "C2"], rows)          # 任务矩阵：轮 x 核
pseudocode_block(s, 0.73, 1.7, 9.6, ["对每个 (轮 r, 核 j):", "    ..."])
note(s, 0.73, 10.4, "顺序固定，结果就固定。")

save(prs, "out.pptx")
print(check_layout(prs))         # 收尾必须 0 越界 0 重叠
```

主要 API：

| 构件 | 用途 |
|---|---|
| `new_deck(preset)` / `blank_slide` / `save` | 画布（`4:3` / `16:9` / `16:10`） |
| `title` / `text` / `subtitle` / `note` | 标题、正文、图注（中英自动分 run 设字体） |
| `block_grid` / `tensor_block` | 块网格、单个分块 |
| `spec_table` / `round_table` / `accum_table` / `gantt_table` | 各类表格原型 |
| `task_matrix` | 任务矩阵（**行 = 轮，列 = 核**） |
| `trace_table` | 转置视角（**行 = 核，列 = 轮**）：每条核这一轮守在哪条列 |
| `axis_grid` | 带轴头的 (S1, S2) 覆盖图 |
| `pseudocode_block` | 伪代码块 |
| `panel` / `panel_height` | 带表外标题的小表（填空白用：对比/数字/中间形态）与它的高度（先算高度再决定放哪栏） |
| `arrow` / `axis_arrow` | 连接线、轴箭头 |
| `lane_colors` / `text_on` | lane 配色预设、按底色亮度自动选字色 |
| `check_layout` | 版心硬检查（文字按实际占位、表格按真实框） |

## 4. 渲染回看（强烈建议）

数字检查（`check_layout`）只能保证"没越界、没重叠"，**版式好不好看必须看图**：

```powershell
# 需要本机装了 WPS（用它的 COM 接口）
powershell -File scripts\render_deck.ps1 examples\demo.pptx
# 装了 LibreOffice 的话
soffice --headless --convert-to png --outdir <目录> examples\demo.pptx
```

导出的 PNG 放在 pptx 同级的 `_render\`，逐页看一眼再调版式。

## 5. 硬规则（用之前先读）

完整版在 `SKILL.md`，最容易踩的几条：

1. **画布先定，内容不许越界**：四边留 0.6 in，收尾跑 `check_layout`，0 越界 0 重叠才算完。
2. **不留大块空白**，空处补对比表 / 代价数字表 / 中间形态图，不要拿废话填。
3. **每页都要有标题**；有子标题就放标题下方、字号更小。
4. **表格的归属标记要紧贴自己的表**（只占自己表格的宽度 + 一小段竖线钉住）。
5. **讲逻辑不给代码位置**：例子前先放伪代码块；页面上不出现文件名/行号。
6. **表项写清轴的索引**（`S1=2 S2=3`），不要写逗号分隔的裸数字。
7. **任务矩阵行是轮、列是核**。
8. **浅底不要写白字** —— 块内字色交给 `text_on(fill)` 自动选。

## 6. 案例

`cases/flash-attention-det-accum/` —— 一个真实方案（Ascend FA 反向算子的确定性梯度累加）
的调度图案例：七种任务索引算法的 Python 实现 + 不变量校验 + 绘制脚本 + 输出页面。
它演示了上面这套规范在"轮次 × 核 × 分块"这类问题上的完整用法。

## 7. 许可

内部资料，未附开源许可；使用前请与作者确认。
