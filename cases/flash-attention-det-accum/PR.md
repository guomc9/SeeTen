# PR：确定性反向（BN2S2 + TND causal 调度）性能对比与分析

源分支：`det-cmp-v3-swizzle`（HEAD `02c043b`）
目标分支：`integration/FAG-V3-A5`（基线 `13e835c`「cube Optimize」已并入，PR 无冲突）

## Related Issue

None.

## Summary

本 PR 为 Ascend950 FA v3 反向补齐/优化确定性（det）路径，并给出与
**ops-transformer（opst）** 的全矩阵性能对比与分 pipe 归因：

- 确定性 bwd 采用 **BN2S2** 列独占调度 + 跨轮 fix 屏障，MHA 上 dk/dv 不落
  workspace、列尾直接 cast；`deterministic=True` 现在要求 BN2S2（v1/v2 流内
  VecDTM 回退已随目标主流水重写移除，`mha_bwd.cpp` 有显式校验）。
- **TND causal 专用调度**：每 batch `sq == sk` 时走左上对齐的 4 段式调度，
  与 opst 的 causal 语义一致，块冗余算力从 ~2× 降到 0；其余（ragged / GQA）
  走 dense + mask + 整块裁剪（pruning）。
- **TND ragged MHA 改 flat 分区**（替换原 legacy 回退），
  `tnd_ragged_mha_nc` det 72.5 → 31.8 µs。
- 已把目标分支的「cube Optimize」主流水并入本分支，并保留非确定实例化为原路径。

### 性能对比口径

msprof device 侧 kernel 时间（`Task Duration`），**median of 25**（warmup 5 +
repeat 20）；38 个 case（BSND 21 + TND 17，小/中/大 × MHA/GQA/MQA × c/nc，
det 与 nd 各一次）；opst 的 det 走 `torch.use_deterministic_algorithms(True)`。

### 结论摘要（详见 Validation 的表）

| 指标（opst / ours，≥0.8 达标） | 全部 38 | BSND 21 | TND 17 |
|---|---:|---:|---:|
| det 核时比 GM（达标率） | 0.741（34%） | 0.683（29%） | **0.819（41%）** |
| nd 核时比 GM（达标率） | 0.669（13%） | 0.681（5%） | 0.655（24%） |
| det/nd 确定性开销 GM：ours / opst | 1.193 / 1.320 | 1.222 / 1.226 | **1.158 / 1.447** |

- **确定性开销**：本实现整体 1.193×，优于 opst 的 1.320×；38 个 case 中
  **23 个**（60%）本实现开销 ≤ opst（TND 组尤其明显，1.158 vs 1.447）。
- **det vs det**：小档已占优（TND 小 GM 1.101、100% 达标；BSND 小 0.637 但 40%
  达标），中/大档落后（BSND 大 0.567、TND 大 0.666，0% 达标）。
- **nd（非确定路径）**：GM 0.669，是分支既有主流水差距（合并目标 cube Optimize
  后继承，与本 PR 的确定性改动无关；目标自身的优化也使部分 mid nd shape 变慢，
  如 GQA s1024 nc 69→93 µs，已用纯目标构建对照确认）。
- **分 pipe 归因（10.1 / 10.2）**：nd 是「重叠受限」——每条 pipe 都不高于 opst
  而 duration 长 1.45–1.51×（cube% 86–95 仍有余量）；det 的增量全部落在
  **MTE2 + fixpipe**（重复加载 Q/Kᵀ/K/dY 与 fp32 原子累加 + 每列 cast），
  MAC 不高于 opst；scalar/解码不是瓶颈（nd 实例化里 det 解码被
  `if constexpr (IS_DTM)` 编译掉，实测 scalar 全面低于 opst）。
- **极小档（0.26–0.33MB）尚未占优**：全部 pipe ≤0.5 µs、MAC 0.1 µs，而
  duration 20–34 µs ⇒ 差距 100% 在固定开销（启动 + 轮次/同步结构），
  det 2.3–2.4×、nd 1.4–1.7×。

## Validation

### 单元 / 一致性测试

`tests/test_flash_attn_npu_v3_bwd_det.py`：**38 case 全过**（BSND 21 + TND 17），
每个 case 跑 det 与 nondet 两条路径，校验：golden 一致、det 多次调用逐位一致、
det 与 nd 互验；causal 用例按每 batch `sq ≤ sk` 生成（否则 golden 自身退化 NaN）。

```bash
FLASH_ATTN_BUILD_VERSION=v3 python setup.py build
PYTHONPATH=build/lib.linux-x86_64-cpython-312 \
  python -u tests/test_flash_attn_npu_v3_bwd_det.py --repeat 10
```

### 9.1–9.3 确定性开销（det 核时 / nd 核时，>1 = det 更慢）

| 分组 | case 数 | ours GM | opst GM |
|---|---:|---:|---:|
| 全部 | 38 | 1.193 | 1.320 |
| BSND | 21 | 1.222 | 1.226 |
| TND | 17 | 1.158 | 1.447 |
| 小 | 12 | 1.156 | 1.412 |
| 中 | 17 | 1.186 | 1.301 |
| 大 | 9 | 1.258 | 1.240 |

（`ours 开销 ≤ opst` 的 case：23 / 38）

### 9.4–9.6 det-vs-det（比值 = opst-det / ours-det，≥0.8 达标）

| 分组 | 小 GM（达标） | 中 GM（达标） | 大 GM（达标） |
|---|---:|---:|---:|
| BSND | 0.637（40%） | 0.767（36%） | 0.567（0%） |
| TND | **1.101（100%）** | 0.665（0%） | 0.666（0%） |

### 9.7–9.9 nd-vs-nd（比值 = opst-nd / ours-nd）

| 分组 | 小 GM（达标） | 中 GM（达标） | 大 GM（达标） |
|---|---:|---:|---:|
| BSND | 0.725（20%） | 0.686（0%） | 0.628（0%） |
| TND | 0.713（43%） | 0.628（17%） | 0.604（0%） |

### 9.10 / 9.11 明细（GM 行，µs）

| layout | ours det | ours nd | opst det | opst nd | det GM（pass） | nd GM（pass） |
|---|---:|---:|---:|---:|---:|---:|
| BSND | 70.9 | 58.0 | 48.4 | 39.5 | 0.68（29%） | 0.68（5%） |
| TND | 133.2 | 115.0 | 109.1 | 75.4 | 0.82（41%） | 0.66（24%） |

明细页（9.10/9.11）逐 case 列出 4 条核时与 det/nd ratio，**加粗 = 双方更优的
核时，下划线 = ratio ≥ 0.8 达标**；空缺 = opst 无法运行。

### 10.1 / 10.2 分 pipe profiling（msprof PipeUtilization，单次 profiled run）

**10.1 BSND 五档（0.26 / 0.33 / 0.92 / 10.5 / 41.9 MB）**

- 0.26 / 0.33 MB：ours 各 pipe ≤0.5 µs、MAC 0.1 µs，duration 20–34 µs；
  实测（median of 25）落后 det 2.3–2.4×、nd 1.4–1.7× ⇒ 固定开销。
- 0.92 MB：ours det 24.8 vs 26.9 µs（1.09× 占优）、nd 20.5 vs 20.4（持平）。
- 10.5 MB：det 缺口 MTE2 +26.6、fixpipe +8.9；nd 各口 ≤ opst 而 duration 1.35×。
- 41.9 MB：det 缺口 MTE2 +44.8、fixpipe +35.0；nd 各口 ≤ opst 而 duration 1.49×。

**10.2 TND causal 三档（3.3 / 41.9 / 41.9 MB）**

| case | ours det | ours nd | opst det | opst nd | 备注 |
|---|---:|---:|---:|---:|---|
| 中 2×2048 H8 D128 | 404.8 | 283.7 | 264.2 | 188.4 | det：MTE2 +62.5、fixpipe +80.9 |
| 大 4×2048 H4 D128 | 356.5 | 282.0 | 260.3 | 194.0 | det：MTE2 +54.3、fixpipe +64.1 |

- 中/大档 nd 每条 pipe ≤ opst、duration 1.45–1.51× ⇒ 重叠/串联受限；
- 小档（3.3 MB）ours 占优：实测 nd 1.19×、det 1.29×。

### 10.3 结论与优化优先级（记录在案，不在本 PR 实施）

1. **主流水重叠**（round/barrier、每任务串联、双缓冲）—— nd 与 det 同时受益；
2. **BN2S2 det 引入 KV 驻留 + L0C 累积**（对齐目标主流水）—— 直接消 det 的
   MTE2 / fixpipe 缺口；
3. 固定开销专项（极小档 ≤0.35MB）—— 仅影响该档，低优先级；
4. 解码 / scalar 专项 —— 不做（实测不是瓶颈，lookahead 削减收益 ≈ 0）。

## Additional Information

- **对比对象的可运行边界**：opst 的 TND causal 要求 `atten_mask` 的 Skv 恰为
  2048，因此单段长度 > 2048 的 causal 用例 opst 无法运行（明细表中记为空缺，
  不影响 ours 的测试与结论）。
- **确定性前提**：`deterministic=True` 必须落到 BN2S2 调度（有显式校验，不再
  回退旧流内方案）；非确定路径保持原实例化（`09b51d6` 隔离）。
- **极小档与中/大档结论相反**：0.92 MB 起 det 占优，而 0.26–0.33 MB 档因固定
  开销落后 2.3–2.4×（det），引用"小 shape 已占优"时需注明档位。
- **nd 差距的来源**：合并目标「cube Optimize」后 nd 与纯目标构建一致（A/B 对照
  通过），该差距为分支既有主流水问题，非本 PR 引入；目标自身的优化亦使部分 mid
  nd shape 变慢（GQA s1024 nc 69→93 µs、square nc 73→82、rect 28→33）。
- **FWD 侧已知问题（仅记录，不影响本 PR 的 bwd 接口）**：`flash_attn_func` /
  `flash_attn_varlen_func` 返回的 `softmax_lse` 目前为 `+inf`（fwd 未落地 lse
  写出），走 autograd 端到端时梯度会全 0；直接调用 bwd 接口（传入合法 lse）
  不受影响。基线分支同样存在。
- 数据与图（38 case 全矩阵、分 pipe profiling、9.1–10.2 各页）见 SeeTen 案例
  `flash-attention-det-accum`（`perf_matrix.py` / `profile_data.py` 为数据源，
  `check_case.py` 逐格回读校验）。
