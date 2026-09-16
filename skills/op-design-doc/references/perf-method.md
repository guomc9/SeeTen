# 性能测试口径规范

算子详设文档第 8 节（测试设计）的性能数据必须按本口径采集与呈现。
（血泪教训：跨会话漂移与"测了什么口径"不清，曾让一整轮优化结论作废。）

## 计时方法（必须写明）

| 项 | 约定 |
|---|---|
| 计时器 | `msprof --aic-metrics=PipeUtilization`，取 op_summary 的 **Task Duration**（device 侧核时） |
| 聚合 | warmup 5 + repeat 20，取 **median of 25**（需要时附 min） |
| 禁用口径 | 不用 event record 端到端时间当核时；不写"约 x ms"无来源数字 |
| 对照实现 | 说明参考实现与开关（如 opst det = `torch.use_deterministic_algorithms(True)`） |

## A/B 对比纪律（防漂移）

- **同会话交错**：两个（或 N 个）变体的对比必须**逐 case 交错**跑
  （A(case1), B(case1), A(case2), B(case2)…），不要 A 全跑完再跑 B；
- **跨会话数字不可比**：同一二进制隔几小时复测 det 可漂 5~20µs；
  引用历史数字时必须注明采集日期/会话；
- **det 比 nd 更敏感**：barrier/同步多的路径受机器状态影响更大，结论要配配对方差；
- **build 目录切换**：变体用 `PYTHONPATH=<变体 build 目录>` 切换，bench 脚本若
  改写环境变量（如强制 PYTHONPATH）必须先审一遍——曾有脚本静默覆盖变体目录，
  导致"基线 vs 基线"的假阴性。

## 结果呈现

- **用例矩阵**：shape 表列全 `b n g s2 s1 d causal/dense`（口径：`causal / dense`，
  不用 non-causal；TND ragged 给各段长度，如 `s2=300+400 s1=100+800`）；
- **结果表**：核时（µs，median of 25）+ 比值（对照/本实现，≥0.8 标粗）+
  GM（几何均值）行 + 通过率（达标 case 数/总数）；
- **分 pipe 表**（需要归因时）：duration、MAC、MTE2、MTE1、fixpipe、scal_c、
  vec、scal_v、cube% —— 注明 profiled run 含采集开销，看结构与相对占用；
- **消融/优化结论**：只写经交错 A/B 验证过的；标"错值计时"的消融实验要注明
  语义已被破坏（结果不可用于正确性判断）。

## 正确性验证

- golden 一致（与参考实现的数值比对，bf16 给 rel 误差）；
- 确定性：同输入连续 N 次运行**逐位一致**（bitwise）；
- det/nd 互验（det 结果与 nd 结果在容差内一致）；
- 边界：非对齐尺寸、奇 batch、单段 >2048、空任务等。
