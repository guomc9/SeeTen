#!/usr/bin/env python3
"""Generate the SeeTen case data module perf_matrix.py from the benchmark CSVs.

Sources:
  ours : /data/g00977778/tmp-prof/matrix_perf_merged.csv   (post-merge build)
  opst : /data/g00977778/tmp-prof/matrix_perf_opst.csv
Case list / labels come from tests/test_flash_attn_npu_v3_bwd_det.py.
"""
import ast
import csv
import os

MAIN = "/data/g00977778/flash-attention-npu"
TEST = os.path.join(MAIN, "tests", "test_flash_attn_npu_v3_bwd_det.py")
OUT = os.path.expanduser("~/SeeTen/cases/flash-attention-det-accum/perf_matrix.py")


def load_cases():
    tree = ast.parse(open(TEST, encoding="utf-8").read())
    tables = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id in (
                "BSND_CASES", "VARLEN_CASES"):
            rows = []
            for el in node.value.elts:
                vals = []
                for x in el.elts:
                    if isinstance(x, ast.Constant):
                        vals.append(x.value)
                    elif isinstance(x, ast.List):
                        vals.append([y.value for y in x.elts])
                    else:
                        vals.append(None)
                rows.append(vals)
            tables[node.targets[0].id] = rows
    return tables


def head_type(hq, hkv):
    if hkv == hq:
        return "MHA"
    if hkv == 1:
        return "MQA"
    return "GQA"


def bsnd_label(c):
    _, b, sq, sk, hq, hkv, hd, causal = c[:8]
    cs = "c" if causal else "nc"
    return f"b{b}·{sq}×{sk}·{cs}·H{hq}/{hkv}·D{hd}"


def bsnd_short(c):
    _, b, sq, sk, hq, hkv, hd, causal = c[:8]
    cs = "c" if causal else "nc"
    return f"b{b}·{sq}×{sk}{cs} {head_type(hq, hkv)}"


def tnd_short(c):
    _, cu_q, cu_k, hq, hkv, hd, causal = c[:7]
    sq = [cu_q[i + 1] - cu_q[i] for i in range(len(cu_q) - 1)]
    sk = [cu_k[i + 1] - cu_k[i] for i in range(len(cu_k) - 1)]
    if len(set(sq)) == 1 and sq == sk:
        seq = f"{len(sq)}×{sq[0]}"
    elif len(sq) >= 6:
        seq = f"{len(sq)}×{sq[0]}"
    else:
        seq = f"R{len(sq)}·{max(sq)}/{max(sk)}"
    cs = "c" if causal else "nc"
    return f"{seq}{cs} {head_type(hq, hkv)}"


def tnd_label(c):
    _, cu_q, cu_k, hq, hkv, hd, causal = c[:7]
    sq = [cu_q[i + 1] - cu_q[i] for i in range(len(cu_q) - 1)]
    sk = [cu_k[i + 1] - cu_k[i] for i in range(len(cu_k) - 1)]
    def seq(v):
        if len(set(v)) == 1:
            return f"{len(v)}×{v[0]}"
        return "+".join(str(x) for x in v)
    desc = seq(sq) if sq == sk else f"{seq(sq)}/{seq(sk)}"
    cs = "c" if causal else "nc"
    return f"{desc}·{cs}·H{hq}/{hkv}·D{hd}"


METRIC = "med"      # "med" = 中位数（口径见文件头）；"min" = 原最小值口径


def shape_bsnd(c):
    """标签口径：n = KV 头数（n2），g = 分组比（Hq/Hkv）。"""
    _, b, sq, sk, hq, hkv, hd, causal = c[:8]
    return (f"b{b} n{hkv} g{hq // hkv} s2={sk} s1={sq} d{hd} "
            f"{'c' if causal else 'nc'}")


def shape_tnd(c):
    _, cu_q, cu_k, hq, hkv, hd, causal = c[:7]

    def seq(cu):
        segs = [cu[i + 1] - cu[i] for i in range(len(cu) - 1)]
        return (str(segs[0]) if len(set(segs)) == 1
                else "+".join(str(x) for x in segs))

    return (f"b{len(cu_q) - 1} n{hkv} g{hq // hkv} s2={seq(cu_k)} "
            f"s1={seq(cu_q)} d{hd} {'c' if causal else 'nc'}")


def size_mb_bsnd(c):
    """数据量 MB（bf16：q + out + dy + k + v，1 MB = 1e6 B）。"""
    _, b, sq, sk, hq, hkv, hd = c[:7]
    n = (b * sq * hq * hd) * 3 + (b * sk * hkv * hd) * 2
    return n * 2.0 / 1e6


def size_mb_tnd(c):
    _, cu_q, cu_k, hq, hkv, hd = c[:6]
    n = (cu_q[-1] * hq * hd) * 3 + (cu_k[-1] * hkv * hd) * 2
    return n * 2.0 / 1e6


def load_csv(path):
    out = {}
    for r in csv.DictReader(open(path)):
        name = r["case"].split(":", 1)[-1]
        def f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        out[name] = (f(r[f"det_{METRIC}_us"]), f(r[f"nd_{METRIC}_us"]))
    return out


def main():
    tables = load_cases()
    ours = load_csv("/data/g00977778/tmp-prof/matrix_perf_merged.csv")
    opst = load_csv("/data/g00977778/tmp-prof/matrix_perf_opst.csv")

    cases, shorts, shapes, od, ond, pd, pnd, sizes = [], [], [], [], [], [], [], []
    for c in tables["BSND_CASES"]:
        name = c[0]
        cases.append((name, "BSND", bsnd_label(c)))
        shorts.append(bsnd_short(c))
        shapes.append(shape_bsnd(c))
        sizes.append(size_mb_bsnd(c))
        od.append(ours[name][0]); ond.append(ours[name][1])
        p = opst.get(name, (None, None))
        pd.append(p[0]); pnd.append(p[1])
    n_bsnd = len(cases)
    for c in tables["VARLEN_CASES"]:
        name = c[0]
        cases.append((name, "TND", tnd_label(c)))
        shorts.append(tnd_short(c))
        shapes.append(shape_tnd(c))
        sizes.append(size_mb_tnd(c))
        od.append(ours[name][0]); ond.append(ours[name][1])
        p = opst.get(name, (None, None))
        pd.append(p[0]); pnd.append(p[1])

    def fmt(v):
        return "None" if v is None else f"{v:.1f}"

    with open(OUT, "w", encoding="utf-8") as f:
        f.write('"""性能矩阵数据（msprof device 侧 kernel 时间，median of 25，μs）。\n\n'
                "本仓库 = det-cmp-v3-swizzle @ 合并 integration/FAG-V3-A5(cube Optimize) 后；\n"
                "opst = 参考仓库（det 用 torch.use_deterministic_algorithms(True)）。\n"
                "口径：msprof Task Duration 中位数（warmup 5 + repeat 20），非 event record。\n"
                'None = 该 case 参考实现无法运行。\n"""\n\n')
        f.write("# (case_name, layout, label)\nCASES = [\n")
        for n, lay, lab in cases:
            f.write(f'    ("{n}", "{lay}", "{lab}"),\n')
        f.write("]\n\n")
        f.write("# 图中用短标签（横轴空间有限）\nSHORT = [\n")
        for sh in shorts:
            f.write(f'    "{sh}",\n')
        f.write("]\n\n")
        f.write("# 表里用的 shape 描述（b n g s2 s1 d c/nc）\nSHAPE = [\n")
        for sh in shapes:
            f.write(f'    "{sh}",\n')
        f.write("]\n\n")
        f.write("# 数据量 MB（bf16：q + out + dy + k + v）\nSIZE_MB = [\n    "
                + ", ".join(f"{v:.2f}" for v in sizes) + ",\n]\n\n")
        for nm, arr in (("OURS_DET", od), ("OURS_ND", ond),
                        ("OPST_DET", pd), ("OPST_ND", pnd)):
            f.write(f"{nm} = [\n    " + ", ".join(fmt(v) for v in arr))
            f.write(",\n]\n\n")
        f.write(f"N_BSND = {n_bsnd}\nN_TND = {len(cases) - n_bsnd}\n")
    print(f"wrote {OUT}: {len(cases)} cases ({n_bsnd} BSND + {len(cases)-n_bsnd} TND)")


if __name__ == "__main__":
    main()
