"""案例数据：把「(轮, 核) → (批, 头, 组, S1, S2)」的七种任务索引算法做成可算的纯函数。

这些函数都是纯标量整数运算，取自一个 Ascend FA 反向算子的确定性梯度累加方案
（"事前调度"路线：先排好任务，让一条核独占一条 KV 列，dK/dV 就由单核按程序序累加）。
放到案例里是为了给 `draw_case.py` 提供**真实可算**的数据 —— 页面上的每个数字都从
这里算出来，不是手填的。

坐标：内部用 1-based，`Decode` 出口统一转成 0-based 的 Coord。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- Kind 枚举

KIND_DENSE_SWIZZLE = 1        # 列优先：低位是 KV 列
KIND_DENSE_INDEX = 2          # 批优先：低位是批
KIND_CAUSAL_SWIZZLE = 3       # 两个批折成一个满矩形
KIND_LEFT_UP_CAUSAL = 4       # 左上对齐 causal
KIND_GQA_DENSE = 5            # GQA：任务切片 + gcd 修正
KIND_TND_DENSE = 6            # 变长 batch（MHA）：逐批列私有
KIND_TND_GQA_DENSE = 7        # 变长 batch（GQA）：按面积展平

KIND_CN = {KIND_DENSE_SWIZZLE: "列私有 swizzle", KIND_DENSE_INDEX: "先分批再分列",
           KIND_CAUSAL_SWIZZLE: "因果折叠", KIND_LEFT_UP_CAUSAL: "左上因果折叠",
           KIND_GQA_DENSE: "GQA 切片", KIND_TND_DENSE: "变长列私有",
           KIND_TND_GQA_DENSE: "变长展平"}


# ---------------------------------------------------------------- 标量助手

def ceil_div(a, b):
    return (a + b - 1) // b


def gcd(a, b):
    while b > 0:
        a, b = b, a % b
    return a


def nz(v, base):
    """C++ 惯用法：v 为 0 时取 base。"""
    return v if v != 0 else base


@dataclass
class Shape:
    batch: int = 0
    qSeqLen: int = 0
    kvSeqLen: int = 0
    qHeadNum: int = 0
    kvHeadNum: int = 0
    groupNum: int = 1
    qTile: int = 128
    kvTile: int = 128
    coreNum: int = 0

    def M(self):
        return ceil_div(self.qSeqLen, self.qTile)

    def N(self):
        return ceil_div(self.kvSeqLen, self.kvTile)

    def Bh(self):
        return self.batch * self.kvHeadNum


@dataclass
class Raw:
    w: int = 0          # 1-based 合并 (批, 头, 组) 索引
    s1: int = 0
    s2: int = 0


@dataclass
class Coord:
    batch: int = 0
    n2: int = 0
    g: int = 0
    s1: int = 0
    s2: int = 0
    valid: bool = False
    parity: int = 0
    fold_count: int = 1
    fold: list = field(default_factory=lambda: [(0, 0), (0, 0)])   # [(批, s2), ...]


# ---------------------------------------------------------------- 七种算法

def cal_dense_swizzle_index(k, m, n, b, j, r, c: Raw):
    """列私有 swizzle：一条 lane 在 m 轮内独占一条 KV 列，列内把 S1 逐行走一遍。"""
    c.w = 0
    j, r = j - 1, r - 1
    k = min(k, b * m)
    if j > k:
        return
    p = (r // m) * k + j          # 每个 m 轮跨度内 p 固定
    w, y = p // n, p % n          # 低位 = KV 列
    x = (y + r) % m               # 列内 S1 往下走一行
    if x >= m:
        x -= m
    w, x, y = w + 1, x + 1, y + 1
    if 1 <= w <= b and 1 <= x <= m and 1 <= y <= n:
        c.w, c.s1, c.s2 = w, x, y


def cal_dense_index(k, m, n, b, j, r, c: Raw):
    """先分批再分列：task id 低位是批，所以核数可以超过 S1 块数。"""
    c.w = 0
    k = min(k, b * m)
    if j > k:
        return
    p = (ceil_div(r, m) - 1) * k + j
    w = nz(p % b, b)              # 低位 = 批
    y = ceil_div(p, b)
    x = nz(y % m, m) + nz(r % m, m) - 1
    if x > m:
        x -= m
    if 1 <= w <= b and 1 <= x <= m and 1 <= y <= n:
        c.w, c.s1, c.s2 = w, x, y


def cal_causal_swizzle_index(k, m, n, b, j, r, c: Raw, fold=None):
    """因果折叠：两个相邻批拼成一个虚拟矩形，两个三角正好凑满。"""
    c.w = 0
    n_new = n + 1 if m == n else (n - m + 2) + (n + 1)
    cal_dense_swizzle_index(k, m, n_new, b >> 1, j, r, c)
    if c.w == 0:
        return
    w, x, y = c.w, c.s1, c.s2
    if y >= x + 1:
        y = (n << 1) - m - y + 2
        x = m + 1 - x
        w = w << 1
    else:
        w = (w << 1) - 1
    if 1 <= w <= b and 1 <= x <= m and 1 <= y <= n:
        c.w, c.s1, c.s2 = w, x, y
        if fold is not None and m == n:
            odd = w if (w & 1) else w - 1
            if w & 1:
                fold.parity = 0
                fold.fold = [(odd, y), (odd + 1, (m - y + 2) if y >= 2 else 0)]
            else:
                yv = m - y + 2
                fold.parity = 1
                fold.fold = [(odd, yv if yv <= m else 0), (odd + 1, y)]
    else:
        c.w = 0


def cal_left_up_causal_index(k, m, n, b, j, r, c: Raw, fold=None):
    """左上对齐 causal：m>n 时虚拟高 = 2m-n+1，每列只有 m 行有活。"""
    c.w = 0
    pairs = b >> 1
    if k <= 0 or m <= 0 or n <= 0 or pairs <= 0 or j < 1 or r < 1:
        return
    if m <= n:
        active_k = min(k, m * pairs)
        if j > active_k:
            return
        cal_causal_swizzle_index(active_k, m, m, b, j, r, c, fold)
        return
    virtual_m = 2 * m - n + 1
    active_k = min(k, n * pairs)
    if j > active_k:
        return
    column_id = (r - 1) // virtual_m * active_k + j - 1
    if column_id >= n * pairs:
        return
    pair_id = column_id // n + 1
    vs2 = column_id % n + 1
    vs1 = (r - 1) % virtual_m + 1
    odd_len = m - vs2 + 1
    if vs1 <= odd_len:
        c.w, c.s1, c.s2 = 2 * pair_id - 1, vs2 + vs1 - 1, vs2
        if fold is not None:
            fold.parity = 0
            fold.fold = [(2 * pair_id - 1, vs2), (2 * pair_id, n - vs2 + 1)]
        return
    off = vs1 - odd_len
    c.w, c.s1, c.s2 = 2 * pair_id, m - off + 1, n - vs2 + 1
    if fold is not None:
        fold.parity = 1
        fold.fold = [(2 * pair_id - 1, vs2), (2 * pair_id, n - vs2 + 1)]


def cal_gqa_dense_index(k, m, n, b, core, rnd, g, c: Raw):
    """GQA：一条 lane 独占 R 个连续任务号，gcd 修正让同轮键不撞。"""
    c.w = 0
    k = min(min(k, b * g * m), b * n)
    R = max(ceil_div(b * n * g, k), ceil_div(n, m), g)
    if not (1 <= core <= k) or not (1 <= rnd <= R * m):
        return
    ID = (core - 1) * R + ceil_div(rnd, m)
    if ID > g * n * b:
        return
    N = b * g
    b_id = ceil_div(nz(ID % N, N), g)
    y = ceil_div(ID, N)
    w = nz(ID % g, g)
    gd = gcd(N, R)
    t1 = R // gd
    t1_new = t1 * m
    y1 = nz(y % t1_new, t1_new)
    offset = ceil_div(y1, t1)
    if t1_new < n:
        n1 = nz(n % t1_new, t1_new)
        if y <= n - n1:
            delta = ceil_div(y, t1_new)
            ID += delta
            if ID > (delta - 1) * (N // gd) * m * R + offset * (N // gd) * R:
                ID -= (N // gd) * R
            b_id = ceil_div(nz(ID % N, N), g)
            w = nz(ID % g, g)
            y = ceil_div(ID, N)
    x = nz(rnd % m, m) + offset - 1
    if x > m:
        x -= m
    c.w, c.s1, c.s2 = w + (b_id - 1) * g, x, y


def cal_tnd_dense_swizzle(s: Shape, cu_q, cu_k, prefix, j, r, out: Coord):
    """变长 batch（MHA）：逐批 round 前缀，批内列私有。"""
    out.__init__()
    if not (1 <= j <= s.coreNum) or r < 1:
        return False
    j, r = j - 1, r - 1
    n1 = s.kvHeadNum * s.groupNum
    for bidx in range(s.batch):
        if r >= prefix[bidx + 1]:
            continue
        qs = 0 if bidx == 0 else cu_q[bidx - 1]
        ks = 0 if bidx == 0 else cu_k[bidx - 1]
        s1_len, s2_len = cu_q[bidx] - qs, cu_k[bidx] - ks
        if s1_len <= 0 or s2_len <= 0:
            return False
        s1o, s2o = ceil_div(s1_len, s.qTile), ceil_div(s2_len, s.kvTile)
        delta = r - prefix[bidx]
        linear = delta // s1o * s.coreNum + j
        if linear >= s2o * n1:
            return False
        n1idx, s2idx = linear // s2o, linear % s2o
        s1idx = (s2idx + delta) % s1o
        out.batch, out.n2, out.g = bidx, n1idx // s.groupNum, n1idx % s.groupNum
        out.s1, out.s2, out.valid = s1idx, s2idx, True
        return True
    return False


def cal_tnd_gqa_dense(s: Shape, cu_q, cu_k, area_prefix, j, r, max_round, out: Coord):
    """变长 batch（GQA）：按面积展平后等分成 k 段，每段顺序扫。"""
    out.__init__()
    if not (1 <= j <= s.coreNum) or not (1 <= r <= max_round):
        return False
    n1 = s.kvHeadNum * s.groupNum
    ID = (j - 1) * max_round + r
    w = 0
    while w + 1 < s.batch and ID > area_prefix[w + 1] * n1:
        w += 1
    if ID > area_prefix[w + 1] * n1:
        return False
    delta = ID - area_prefix[w] * n1
    qs = 0 if w == 0 else cu_q[w - 1]
    ks = 0 if w == 0 else cu_k[w - 1]
    m, n, g = ceil_div(cu_q[w] - qs, s.qTile), ceil_div(cu_k[w] - ks, s.kvTile), s.groupNum
    base = m * n * g
    delta_n = (delta - 1) // base + 1
    delta = nz(delta % base, base)
    m_new = m * g
    gd = gcd(m_new, max_round)
    t1 = max_round // gd
    x = nz(delta % m_new, m_new)
    y = ceil_div(delta, m_new)
    if t1 < n:
        tail = nz(n % t1, t1)
        if y <= n - tail:
            adj = ceil_div(y, t1)
            delta += adj
            if delta > adj * (m_new // gd) * max_round:
                delta -= (m_new // gd) * max_round
            x, y = nz(delta % m_new, m_new), ceil_div(delta, m_new)
    n1_id = ceil_div(x, m)
    x = nz(x % m, m)
    if delta_n > s.kvHeadNum or n1_id > g or y > n:
        return False
    out.batch, out.n2, out.g = w, delta_n - 1, n1_id - 1
    out.s1, out.s2, out.valid = x - 1, y - 1, True
    return True


# ---------------------------------------------------------------- 门面与校验

def decode(kind, s: Shape, r, j, **kw):
    """(轮, 核) → Coord 或 None（入参均 1-based）。"""
    out = Coord()
    raw = Raw()
    if kind == KIND_DENSE_SWIZZLE:
        cal_dense_swizzle_index(s.coreNum, s.M(), s.N(), s.Bh(), j, r, raw)
    elif kind == KIND_DENSE_INDEX:
        cal_dense_index(s.coreNum, s.M(), s.N(), s.Bh(), j, r, raw)
    elif kind == KIND_CAUSAL_SWIZZLE:
        cal_causal_swizzle_index(s.coreNum, s.M(), s.N(), s.Bh(), j, r, raw, out)
    elif kind == KIND_LEFT_UP_CAUSAL:
        cal_left_up_causal_index(s.coreNum, s.M(), s.N(), s.Bh(), j, r, raw, out)
    elif kind == KIND_GQA_DENSE:
        cal_gqa_dense_index(s.coreNum, s.M(), s.N(), s.Bh(), j, r, s.groupNum, raw)
    elif kind == KIND_TND_DENSE:
        ok = cal_tnd_dense_swizzle(s, kw["cu_q"], kw["cu_k"], kw["prefix"], j, r, out)
        return out if ok else None
    elif kind == KIND_TND_GQA_DENSE:
        ok = cal_tnd_gqa_dense(s, kw["cu_q"], kw["cu_k"], kw["area_prefix"], j, r,
                                 kw["max_round"], out)
        return out if ok else None
    else:
        return None
    if raw.w < 1:
        return None
    n1 = s.groupNum * s.kvHeadNum
    out.batch, n1i = (raw.w - 1) // n1, (raw.w - 1) % n1
    out.n2, out.g = n1i // s.groupNum, n1i % s.groupNum
    out.s1, out.s2 = raw.s1 - 1, raw.s2 - 1
    out.valid = (out.batch < s.batch and out.n2 < s.kvHeadNum and out.g < s.groupNum
                 and raw.s1 <= s.M() and raw.s2 <= s.N())
    return out if out.valid else None


def tasks_of(kind, s: Shape, max_round, **kw):
    kw.setdefault("max_round", max_round)
    out = {}
    for r in range(1, max_round + 1):
        for j in range(1, s.coreNum + 1):
            out[(j, r)] = decode(kind, s, r, j, **kw)
    return out


def check(kind, s: Shape, max_round, **kw):
    """三条不变量：任务不重复、同一轮各核的 S1 不撞、swizzle 类列私有。"""
    ts = tasks_of(kind, s, max_round, **kw)
    valid = [c for c in ts.values() if c is not None]
    keys = [(c.batch, c.n2, c.g, c.s1, c.s2) for c in valid]
    dq = []
    for r in range(1, max_round + 1):
        seen = {}
        for j in range(1, s.coreNum + 1):
            c = ts.get((j, r))
            if c is None:
                continue
            k2 = (c.batch, c.n2, c.g, c.s1)
            if k2 in seen:
                dq.append((r, seen[k2], j))
            seen[k2] = j
    priv = True
    for j in range(1, s.coreNum + 1):
        run, prev = [], None
        for r in range(1, max_round + 1):
            c = ts.get((j, r))
            if c is None:
                continue
            wy = (c.batch, c.s2)
            if wy != prev:
                if len(set(run)) != len(run):
                    priv = False
                run, prev = [], wy
            run.append(c.s1)
    return {"slots": len(ts), "valid": len(valid), "holes": len(ts) - len(valid),
            "dup": len(keys) - len(set(keys)), "dq_conflict": len(dq),
            "column_private": priv,
            "cols_per_lane": {j: sorted({(c.batch + 1, c.s2 + 1)
                                         for (jj, _), c in ts.items() if jj == j and c})
                              for j in range(1, s.coreNum + 1)}}


def cases():
    """案例里用到的 7 个例子（与页面一一对应）。"""
    out = []
    s = Shape(batch=2, qSeqLen=384, kvSeqLen=384, qHeadNum=1, kvHeadNum=1, coreNum=2)
    out.append(("列私有 swizzle", KIND_DENSE_SWIZZLE, s, 9, {}, False))
    s = Shape(batch=2, qSeqLen=256, kvSeqLen=256, qHeadNum=1, kvHeadNum=1, coreNum=4)
    out.append(("先分批再分列", KIND_DENSE_INDEX, s, 2, {}, False))
    s = Shape(batch=2, qSeqLen=384, kvSeqLen=384, qHeadNum=1, kvHeadNum=1, coreNum=2)
    out.append(("因果折叠", KIND_CAUSAL_SWIZZLE, s, 6, {}, True))
    s = Shape(batch=2, qSeqLen=384, kvSeqLen=256, qHeadNum=1, kvHeadNum=1, coreNum=2)
    out.append(("左上因果折叠", KIND_LEFT_UP_CAUSAL, s, 5, {}, True))
    s = Shape(batch=1, qSeqLen=256, kvSeqLen=256, qHeadNum=2, kvHeadNum=1,
              groupNum=2, coreNum=2)
    out.append(("GQA 切片", KIND_GQA_DENSE, s, 4, {}, False))
    s = Shape(batch=2, qHeadNum=1, kvHeadNum=1, coreNum=2)
    pre = [0, 3, 7]
    out.append(("变长列私有", KIND_TND_DENSE, s, pre[2],
                dict(cu_q=[384, 640], cu_k=[256, 640], prefix=pre), False))
    s = Shape(batch=2, qHeadNum=2, kvHeadNum=1, groupNum=2, coreNum=2)
    out.append(("变长展平", KIND_TND_GQA_DENSE, s, 6,
                dict(cu_q=[256, 384], cu_k=[256, 512], area_prefix=[0, 4, 6]), False))
    return out


if __name__ == "__main__":
    for name, kind, s, mr, kw, _causal in cases():
        r = check(kind, s, mr, **kw)
        gqa = kind in (KIND_GQA_DENSE, KIND_TND_GQA_DENSE)
        priv = "不适用(GQA 走共享累加)" if gqa else r["column_private"]
        print(f"{name:12s} slots={r['slots']:3d} valid={r['valid']:3d} "
              f"holes={r['holes']:2d} dup={r['dup']} dq冲突={r['dq_conflict']} "
              f"列私有={priv}")
