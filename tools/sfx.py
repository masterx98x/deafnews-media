import numpy as np
SR = 44100
rng = np.random.default_rng(7)

def env(n, a=0.005, d=None, curve=4.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4))
    dur = n / SR
    e *= np.exp(-curve * t / dur) if d is None else np.exp(-t / d)
    return e

def lp(x, k=0.1):
    y = np.empty_like(x); s = 0.0
    for i, v in enumerate(x):
        s += k * (v - s); y[i] = s
    return y

def lp_fast(x, width):
    if width < 2: return x
    k = np.ones(int(width)) / int(width)
    return np.convolve(x, k, mode="same")

def whoosh(d=0.6, up=True):
    n = int(SR * d); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # band sweep via varying moving average widths
    segs = 24
    for i in range(segs):
        a, b = i * n // segs, (i + 1) * n // segs
        f = i / segs if up else 1 - i / segs
        w = int(60 - 55 * f)
        out[a:b] = lp_fast(noise, w)[a:b] - lp_fast(noise, w * 4)[a:b]
    e = np.sin(np.pi * t / d) ** 2
    return 1.6 * out * e

def boom(d=1.2):
    n = int(SR * d); t = np.arange(n) / SR
    f = 30 + 90 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 3.2)
    click = lp_fast(rng.standard_normal(n), 6) * np.exp(-t * 40) * 0.6
    return np.tanh(1.8 * (body + click)) * 0.9

def ding(f=1320, d=1.0):
    n = int(SR * d); t = np.arange(n) / SR
    s = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * (3 + 2 * m)) for m, a in [(1, 1), (2.76, .35), (5.4, .15)])
    return 0.5 * s * np.minimum(1, t / 0.003)

def success():
    a = ding(1046, 0.8); b = ding(1568, 1.0)
    out = np.zeros(int(SR * 1.2)); out[:len(a)] += a; o = int(SR * 0.12); out[o:o + len(b)] += b
    return out * 0.8

def pop(f0=500):
    d = 0.14; n = int(SR * d); t = np.arange(n) / SR
    f = f0 * (1 + 2.5 * np.exp(-t * 60))
    return 0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30)

def click():
    n = int(SR * 0.03); t = np.arange(n) / SR
    return 0.35 * lp_fast(rng.standard_normal(n), 3) * np.exp(-t * 250)

def typing(d=1.5, rate=13):
    n = int(SR * d); out = np.zeros(n); t = 0.0
    while t < d - 0.05:
        c = click() * rng.uniform(0.5, 1.0); i = int(t * SR)
        out[i:i + len(c)] += c[:n - i]
        t += rng.uniform(0.6, 1.4) / rate
    return out

def buzz(d=0.45):
    n = int(SR * d); t = np.arange(n) / SR
    s = np.sign(np.sin(2 * np.pi * 110 * t)) * 0.5 + np.sign(np.sin(2 * np.pi * 116 * t)) * 0.5
    return 0.35 * lp_fast(s, 8) * np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.05)

def siren(d=1.6):
    n = int(SR * d); t = np.arange(n) / SR
    f = 700 + 300 * np.sign(np.sin(2 * np.pi * 2.5 * t))
    s = np.sin(2 * np.pi * np.cumsum(lp_fast(f, 400)) / SR)
    s = np.tanh(2 * s) * 0.3
    return s * np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 0.2)

def scratch(d=0.5):
    n = int(SR * d); t = np.arange(n) / SR
    f = 900 * np.exp(-t * 6) + 80
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.6 * lp_fast(rng.standard_normal(n), 4)
    return 0.35 * s * np.exp(-t * 4)

def glitch(d=0.35):
    n = int(SR * d); out = np.zeros(n); i = 0
    while i < n:
        L = int(rng.uniform(0.01, 0.04) * SR)
        f = rng.choice([220, 440, 880, 1760, 3520])
        tt = np.arange(L) / SR
        seg = np.sign(np.sin(2 * np.pi * f * tt)) * rng.uniform(0.1, 0.3)
        if rng.random() < 0.4: seg = rng.standard_normal(L) * 0.2
        out[i:i + L] = seg[:n - i]; i += L
    return out

def boing(d=0.6):
    n = int(SR * d); t = np.arange(n) / SR
    f = 260 + 120 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 4)
    return 0.45 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)

def music(total, bpm=118):
    n = int(SR * total); out = np.zeros(n)
    beat = 60 / bpm
    kick = boom(0.35) * 0.55
    hat_n = int(SR * 0.05); hat = lp_fast(rng.standard_normal(hat_n), 1) - lp_fast(rng.standard_normal(hat_n), 3)
    hat *= np.exp(-np.arange(hat_n) / SR * 80) * 0.12
    # A minor - F - C - G
    roots = [110.0, 87.31, 130.81, 98.0]
    nb = int(total / beat) + 1
    for b in range(nb):
        i = int(b * beat * SR)
        if i >= n: break
        k = kick[:n - i]; out[i:i + len(k)] += k
        j = int((b + 0.5) * beat * SR)
        if j < n: h = hat[:n - j]; out[j:j + len(h)] += h
        # bass eighths
        root = roots[(b // 4) % 4]
        for e in range(2):
            s = int((b + e * 0.5) * beat * SR); L = int(beat * 0.45 * SR)
            if s >= n: continue
            tt = np.arange(L) / SR
            note = root * (2 if e == 1 else 1)
            v = (2 * ((note * tt) % 1) - 1) * np.exp(-tt * 6) * 0.13
            v = lp_fast(v, 12)
            out[s:s + L] += v[:n - s]
        # pluck arp on 16ths every other bar
        for q in range(4):
            s = int((b + q * 0.25) * beat * SR); L = int(beat * 0.25 * SR)
            if s >= n: continue
            tt = np.arange(L) / SR
            note = root * 4 * [1, 1.5, 2, 1.5][q] * (1.2 if (b // 4) % 4 in (0,) and q == 2 else 1)
            v = np.sin(2 * np.pi * note * tt) * np.exp(-tt * 18) * 0.05
            out[s:s + L] += v[:n - s]
    return out
