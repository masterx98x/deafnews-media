# DeafNews TikTok — motore di rendering guidato da JSON (spec in specs/<slug>.json)
import os, re, json, math, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
WORK = os.environ.get("DN_WORK", "/home/claude/dn-work")
VO_OFF, TAIL, CTA_TAIL = 0.2, 0.25, 1.4

MONT = "/usr/share/fonts/truetype/google-fonts/ofl/montserrat/Montserrat[wght].ttf"
ANTON = "/usr/share/fonts/truetype/google-fonts/ofl/anton/Anton-Regular.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

BG = (9, 12, 18)
COL = dict(green=(60, 255, 143), red=(255, 59, 92), yellow=(255, 201, 60), white=(245, 247, 250),
           grey=(140, 150, 165), cyan=(70, 200, 255))
DARK = dict(red=(50, 16, 26, 245), yellow=(50, 40, 16, 245), green=(16, 40, 30, 250))
GREEN, RED, YEL, WHITE, GREY, CYAN = (COL[k] for k in ("green", "red", "yellow", "white", "grey", "cyan"))
def col(c): return tuple(c) if isinstance(c, list) else COL.get(c or "white", WHITE)
def dark(c): return DARK.get(c, (22, 28, 40, 250))

# ---------- spec / timeline ----------
SPEC, TL, SC, TOTAL, CAPS, HLSET = None, [], {}, 0.0, {}, set()

def load(path):
    global SPEC, TL, SC, TOTAL, HLSET
    SPEC = json.load(open(path))
    durs = json.load(open(f"{WORK}/vo/durs.json"))
    TL, t0 = [], 0.0
    for i, s in enumerate(SPEC["scenes"]):
        last = i == len(SPEC["scenes"]) - 1
        d = VO_OFF + durs[s["id"]] + (CTA_TAIL if last else TAIL)
        TL.append(dict(s, sid=s["id"], start=t0, dur=d, off=VO_OFF, vo=durs[s["id"]]))
        t0 += d
    TOTAL = t0
    SC = {s["sid"]: s for s in TL}
    HLSET = {w.lower() for w in SPEC.get("hl", [])}
    _build_caps()
    return SPEC

def cue(sid, word):
    s = SC[sid]; i = s["cap"].find(word)
    if i < 0:
        raise SystemExit(f"[cue] '{word}' non trovato nei sottotitoli della scena '{sid}'")
    return s["off"] + s["vo"] * (i / len(s["cap"])) * 0.97

def at_time(sid, v, default=0.05):
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    return max(0.05, cue(sid, v) - 0.3)

# ---------- primitives ----------
_fc, _ec = {}, {}
def font(path, size, var=None):
    k = (path, size, var)
    if k not in _fc:
        f = ImageFont.truetype(path, size)
        if var: f.set_variation_by_name(var)
        _fc[k] = f
    return _fc[k]

def clamp(x, a=0, b=1): return max(a, min(b, x))
def eo(x): x = clamp(x); return 1 - (1 - x) ** 3
def eback(x):
    x = clamp(x); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def prog(t, a, d): return clamp((t - a) / d)
def popin(t, a, d=0.35):
    p = prog(t, a, d); return eback(p), clamp(p * 3)

FONTS = dict(anton=(ANTON, None), mono=(MONO, None), bold=(MONT, "Bold"), black=(MONT, "Black"))
def text_el(txt, size, color=WHITE, f="black", stroke=0, maxw=None):
    path, var = FONTS[f]
    if maxw:  # rimpicciolisce finché sta nella larghezza
        while size > 20 and font(path, size, var).getlength(txt) > maxw: size -= 2
    k = ("t", txt, size, color, f, stroke)
    if k in _ec: return _ec[k]
    fo = font(path, size, var)
    bb = fo.getbbox(txt, stroke_width=stroke)
    im = Image.new("RGBA", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((-bb[0] + 2, -bb[1] + 2), txt, font=fo, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
    _ec[k] = im
    return im

def emoji_el(ch, size):
    k = ("e", ch, size)
    if k in _ec: return _ec[k]
    base = ("e", ch, 0)
    if base not in _ec:
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((80, 80), ch, font=ImageFont.truetype(EMOJI, 109), embedded_color=True, anchor="mm")
        bb = im.getbbox()
        _ec[base] = im.crop(bb) if bb else im
    b = _ec[base]; s = size / max(b.size)
    _ec[k] = b.resize((max(1, int(b.width * s)), max(1, int(b.height * s))), Image.LANCZOS)
    return _ec[k]

def rrect_el(w, h, r, fill, outline=None, ow=0):
    k = ("r", w, h, r, fill, outline, ow)
    if k not in _ec:
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=outline, width=ow)
        _ec[k] = im
    return _ec[k]

def put(c, el, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if alpha <= 0.01 or scale <= 0.01: return
    e = el
    if abs(scale - 1) > 0.01:
        e = e.resize((max(1, int(e.width * scale)), max(1, int(e.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.1: e = e.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 0.99:
        e = e.copy(); e.putalpha(e.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(cx - e.width / 2), int(cy - e.height / 2)
    if 0 <= x and 0 <= y and x + e.width <= W and y + e.height <= H:
        c.alpha_composite(e, (x, y))
    else:
        tmp = Image.new("RGBA", c.size, (0, 0, 0, 0)); tmp.paste(e, (x, y), e); c.alpha_composite(tmp)

def make_bg():
    im = Image.new("RGBA", (W, H), BG + (255,)); d = ImageDraw.Draw(im)
    for x in range(0, W, 60): d.line((x, 0, x, H), fill=(20, 28, 38, 255))
    for y in range(0, H, 60): d.line((0, y, W, y), fill=(20, 28, 38, 255))
    g = Image.new("L", (W, H), 0); ImageDraw.Draw(g).ellipse((-200, 300, W + 200, 1500), fill=60)
    glow = Image.new("RGBA", (W, H), (30, 80, 70, 0)); glow.putalpha(g.filter(ImageFilter.GaussianBlur(160)))
    im.alpha_composite(glow); return im
BGIMG = make_bg()
_tint = {}
def tint(c, a):
    if (c, a) not in _tint: _tint[(c, a)] = Image.new("RGBA", (W, H), c + (a,))
    return _tint[(c, a)]

def header(c, T):
    put(c, rrect_el(300, 70, 35, (20, 26, 36, 235), GREEN, 3), 230, 190)
    put(c, text_el("DeafNews", 38, WHITE), 230, 190)
    put(c, rrect_el(300, 70, 35, (60, 14, 24, 235), RED, 3), 560, 190)
    put(c, text_el("CYBERSECURITY", 30, RED), 560, 190)
    if TOTAL: ImageDraw.Draw(c).rectangle((0, 0, int(W * T / TOTAL), 10), fill=GREEN)

T_GLOBAL = 0.0
def code_window(c, cx, cy, w, h, title, lines, t_type=None, alpha=1.0, scale=1.0):
    k = ("cw", w, h, title)
    if k not in _ec:
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), 26, fill=(16, 21, 30, 250), outline=(50, 62, 80), width=3)
        d.rounded_rectangle((0, 0, w - 1, 70), 26, fill=(28, 35, 48, 255)); d.rectangle((0, 40, w - 1, 70), fill=(28, 35, 48, 255))
        for i, cc in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse((28 + i * 40, 22, 54 + i * 40, 48), fill=cc)
        d.text((w // 2, 36), title, font=font(MONO, 26), fill=GREY, anchor="mm")
        _ec[k] = im
    im = _ec[k].copy(); d = ImageDraw.Draw(im)
    fs = 34
    while fs > 22 and max([font(MONO, fs).getlength(x) for x, _ in lines] + [0]) > w - 90: fs -= 2
    f = font(MONO, fs)
    left = t_type if t_type is not None else 10 ** 9
    for i, (txt, cc) in enumerate(lines):
        if left <= 0: break
        show = txt[:int(left)]
        d.text((36, 100 + i * 56), show, font=f, fill=cc)
        left -= len(txt)
        if (left <= 0 or i == len(lines) - 1) and int(T_GLOBAL * 2) % 2 == 0:
            cw = f.getlength(show); d.rectangle((38 + cw, 104 + i * 56, 56 + cw, 140 + i * 56), fill=GREEN)
    put(c, im, cx, cy, scale, alpha)

def gauge(c, cx, cy, value, label, alpha=1.0, vmax=10.0):
    R = 300
    im = Image.new("RGBA", (2 * R + 40, R + 180), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    box = (20, 20, 20 + 2 * R, 20 + 2 * R)
    d.arc(box, 180, 360, fill=(40, 48, 62), width=46)
    frac = clamp(value / vmax); r = value / vmax * 10
    cc = GREEN if r < 4 else (YEL if r < 7 else RED)
    if frac > 0: d.arc(box, 180, 180 + 180 * frac, fill=cc, width=46)
    ang = math.pi * (1 - frac); x0, y0 = 20 + R, 20 + R
    d.line((x0, y0, x0 + (R - 70) * math.cos(ang), y0 - (R - 70) * math.sin(ang)), fill=WHITE, width=12)
    d.ellipse((x0 - 22, y0 - 22, x0 + 22, y0 + 22), fill=WHITE)
    d.text((x0, y0 + 90), f"{value:.1f}", font=font(ANTON, 130), fill=cc, anchor="mm")
    put(c, im, cx, cy, 1, alpha)
    if label: put(c, text_el(label, 52, cc), cx, cy + 290, 1, alpha)

# ---------- captions ----------
def _chunks(cap, maxw=3):
    out, cur = [], []
    for w in cap.split():
        cur.append(w)
        if len(cur) >= maxw or re.search(r"[.!?:,]$", w) and len(cur) >= 2:
            out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out

def _build_caps():
    CAPS.clear()
    for s in TL:
        ch = _chunks(s["cap"]); tot = sum(len(x) + 1 for x in ch); acc = 0; lst = []
        for x in ch:
            a = s["off"] + s["vo"] * acc / tot; acc += len(x) + 1
            lst.append((a, s["off"] + s["vo"] * acc / tot, x))
        CAPS[s["sid"]] = lst

def is_hl(w):
    w = w.strip("…").lower()
    return bool(re.search(r"\d", w)) or w.endswith("!") or w.strip(".,:;?!\"'()") in HLSET

def caption(c, sid, t):
    for a, b, txt in CAPS[sid]:
        if a <= t < b + 0.05:
            sc = 1.12 - 0.12 * eo(prog(t, a, 0.12))
            words = txt.upper().split(); f = font(MONT, 76, "Black"); gap = 22
            lines, cur, cw = [], [], 0
            for w in words:
                l = f.getlength(w)
                if cur and cw + gap + l > 900: lines.append(cur); cur, cw = [], 0
                cur.append((w, l)); cw += (gap if cw else 0) + l
            lines.append(cur)
            y0 = 1390 - (len(lines) - 1) * 50
            for li, line in enumerate(lines):
                x = W / 2 - (sum(l for _, l in line) + gap * (len(line) - 1)) / 2
                for w, l in line:
                    put(c, text_el(w, 76, YEL if is_hl(w) else WHITE, stroke=8), x + l / 2, y0 + li * 100, sc)
                    x += l + gap
            return

# ---------- elementi ----------
# Campi comuni: at (parola dei sottotitoli o secondi), until, x, y, rot, wobble, pulse, sfx
def _box_text(c, e, t, fill, outline, ow, txt, size, tc, f, a, rot, x, y, wmin=0, pad=80):
    ic = e.get("icon"); isz = int(size * 1.15) if ic else 0
    el = text_el(txt, size, tc, f, maxw=e.get("maxw", 940 - pad - (isz + 20 if ic else 0)))
    w = max(wmin, e.get("w", el.width + pad + (isz + 20 if ic else 0))); h = e.get("h", int(el.height + size * 0.75))
    put(c, rrect_el(int(w), int(h), min(int(h) // 2, e.get("r", 34)), fill, outline, ow), x, y, a[0], a[1], rot)
    if ic:  # emoji a sinistra dentro il box, testo centrato nello spazio restante
        ix = x - w / 2 + 30 + isz / 2
        put(c, emoji_el(ic, isz), ix, y, a[0], a[1], rot)
        x = (ix + isz / 2 + 10 + x + w / 2 - 20) / 2
    put(c, el, x, y, a[0], a[1], rot)

def draw_el(c, sid, e, t, s):
    typ = e["type"]; ta = at_time(sid, e.get("at"))
    if t < ta: return
    if "until" in e and t >= at_time(sid, e["until"], 1e9) + 0.25: return
    x, y = e.get("x", W / 2), e.get("y", 700)
    rot = e.get("rot", 0) + (e["wobble"] * math.sin(t * 6) if "wobble" in e else 0)
    a = popin(t, ta)
    if "pulse" in e: a = (a[0] * (1 + e["pulse"] * math.sin(t * 6)), a[1])
    cc = e.get("color")
    if typ == "title":
        put(c, text_el(e["text"], e.get("size", 120), col(cc or "yellow"), "anton", maxw=e.get("maxw", 980)), x, y, a[0], a[1], rot)
    elif typ == "text":
        put(c, text_el(e["text"], e.get("size", 44), col(cc or "grey"), e.get("font", "bold"), maxw=e.get("maxw", 980)), x, y, a[0], a[1], rot)
    elif typ == "emoji":
        put(c, emoji_el(e["e"], e.get("size", 120)), x, y, a[0], a[1], rot)
    elif typ == "badge":  # rettangolo pieno colorato, testo bianco Anton; impact = entra grande e trema
        rot = e.get("rot", -3)
        if e.get("impact"):
            p = prog(t, ta, 0.25); sh = math.sin(t * 90) * 14 * (1 - p)
            a = (2.4 - 1.4 * eo(p), clamp(p * 3)); x += sh
        _box_text(c, e, t, col(cc or "red"), None, 0, e["text"], e.get("size", 90), WHITE, "anton", a, rot, x, y)
    elif typ == "pill":  # box scuro con bordo colorato
        _box_text(c, e, t, dark(cc), col(cc or "yellow"), 3, e["text"], e.get("size", 50),
                  col(e.get("text_color", cc or "white")), e.get("font", "bold"), a, rot, x, y)
    elif typ == "card":  # box con etichetta piccola + testo grande
        w, h = e.get("w", 720), e.get("h", 220)
        put(c, rrect_el(w, h, 36, dark(cc), col(cc or "cyan"), 4), x, y, a[0], a[1])
        put(c, text_el(e.get("label", ""), 50, GREY, "mono", maxw=w - 60), x, y - h * 0.22, a[0], a[1])
        put(c, text_el(e["text"], e.get("size", 100), WHITE, e.get("font", "mono"), maxw=w - 60), x, y + h * 0.16, a[0], a[1])
    elif typ == "list":  # righe [emoji, testo, parola-cue]
        step = e.get("step", 150); rh = e.get("row_h", int(step * 0.83))
        for i, row in enumerate(e["rows"]):
            tr = at_time(sid, row[2] if len(row) > 2 else None, ta + i * 0.4)
            if t < tr: continue
            b = popin(t, tr); yy = e.get("y", 600) + i * step
            put(c, rrect_el(880, rh, 30, dark(cc or "red"), col(cc or "red"), 3), W / 2, yy, b[0], b[1])
            put(c, emoji_el(row[0], 80), 180, yy, b[0], b[1])
            put(c, text_el(row[1], e.get("size", 48), WHITE, "bold", maxw=660), W / 2 + 50, yy, b[0], b[1])
    elif typ == "code":  # lines: [testo, colore, at?]; type_at: digitazione; done: [testo, colore]
        lines = []
        for ln in e["lines"]:
            if len(ln) > 2 and t < at_time(sid, ln[2]): lines.append(("", WHITE))
            else: lines.append((ln[0], col(ln[1] if len(ln) > 1 else "white")))
        tt, tdone = None, None
        if "type_at" in e:
            ty = at_time(sid, e["type_at"]); tdone = ty + sum(len(l[0]) for l in e["lines"]) / 30 + 0.2
            if t < tdone: tt = max(0, (t - ty) * 30)
        if e.get("done") and tdone and t >= tdone: lines.append((e["done"][0], col(e["done"][1])))
        code_window(c, x, y, e.get("w", 960), e.get("h", 100 + 56 * (len(e["lines"]) + bool(e.get("done")))),
                    e.get("title", "terminal"), lines, tt, clamp(prog(t, ta, 0.3)))
    elif typ == "gauge":
        fl = (0.5 + 0.5 * math.sin(t * 12)) * clamp(1 - prog(t, ta + 0.3, 1.5))
        if fl > 0.02: c.alpha_composite(tint(RED, int(60 * fl)))
        vmax = e.get("max", 10)
        v = e["value"] * eo(prog(t, ta, 0.6)); sh = math.sin(t * 80) * 12 * clamp(1 - prog(t, ta + 0.6, 0.6))
        gauge(c, x + sh, y, v, e.get("label", "") if t > ta + 0.6 else "", 1, vmax)
    elif typ == "timeline":  # barra che si riempie da left a right
        d = ImageDraw.Draw(c); p = eo(prog(t, ta, e.get("dur", 2.5))); x0, x1 = 140, 940
        d.rounded_rectangle((x0, y - 16, x1, y + 16), 16, fill=(40, 48, 62))
        if p > 0: d.rounded_rectangle((x0, y - 16, x0 + (x1 - x0) * p, y + 16), 16, fill=col(cc or "red"))
        put(c, text_el(e.get("left", ""), 40, WHITE, "bold"), x0 + 90, y + 80, a[0], a[1])
        if e.get("emoji"): put(c, emoji_el(e["emoji"], 90), x0 + (x1 - x0) * p, y - 100, 1, a[1])
        tr = at_time(sid, e.get("right_at"), ta + 1)
        if t > tr:
            b = popin(t, tr)
            put(c, text_el(e.get("right", ""), 40, GREEN, "bold"), x1 - 90, y + 80, b[0], b[1])
            if e.get("end_emoji"): put(c, emoji_el(e["end_emoji"], 80), x1, y - 100, b[0], b[1])
    elif typ == "line":  # linea [x1,y1,x2,y2]
        if a[1] > 0.6: ImageDraw.Draw(c).line(tuple(e["xy"]), fill=col(cc or "cyan"), width=e.get("width", 4))
    elif typ == "hearts":
        for i in range(6):
            p = prog(t, ta + i * 0.18, 1.6)
            if 0 < p < 1: put(c, emoji_el("❤️", 70), x + 40 * math.sin(i * 2 + p * 6), y - 500 * p, 1, 1 - p)
    else:
        raise SystemExit(f"[engine] tipo elemento sconosciuto: {typ}")

def cta_items(s):
    cap = s["cap"]
    def w(word, fb): return word if word in cap else fb
    return [
        dict(type="title", text=s.get("lead", "LA STORIA COMPLETA SU"), size=60, color="grey", y=430),
        dict(type="badge", text="deafnews.it", y=580, at=w("deafnews.it", 0.6), _cta="url", sfx=["ding"]),
        dict(type="emoji", e="🔗", size=90, x=140, y=500, rot=-15, at=w("deafnews.it", 0.6), sfx="none"),
        dict(type="badge", text="SEGUIMI", size=84, y=820, rot=0, w=560, h=140, r=70, at=w("Seguimi", 2.0), pulse=0.05, _cta="follow"),
        dict(type="emoji", e="👆", size=110, x=W / 2 + 260, y=900, rot=-20, wobble=8, at=w("Seguimi", 2.0), sfx="none"),
        dict(type="pill", text=s.get("question", "Che ne pensate?"), color="cyan", text_color="white", size=56, y=1060, w=820, h=150, at=w("commenti", 3.0)),
        dict(type="emoji", e="💬", size=80, x=200, y=1060, at=w("commenti", 3.0), sfx="none"),
        dict(type="hearts", x=880, y=1250, at=s["off"] + s["vo"] - 0.3, sfx="success"),
    ]

def items_of(s):
    return cta_items(s) if s.get("preset") == "cta" else s.get("items", [])

def frame(si, t):
    global T_GLOBAL
    s = TL[si]; T_GLOBAL = s["start"] + t
    c = BGIMG.copy()
    yy = int((T_GLOBAL * 300) % H); ImageDraw.Draw(c).rectangle((0, yy, W, yy + 3), fill=(22, 80, 56, 255))
    for e in items_of(s):
        if e.get("_cta") == "url":
            ta = at_time(s["sid"], e["at"])
            if t >= ta:
                b = popin(t, ta); p = 1 + 0.04 * math.sin(t * 6)
                put(c, rrect_el(860, 170, 85, (16, 40, 30, 250), GREEN, 5), W / 2, e["y"], b[0] * p, b[1])
                put(c, text_el("deafnews.it", 100, GREEN, "anton"), W / 2, e["y"], b[0] * p, b[1])
            continue
        draw_el(c, s["sid"], e, t, s)
    header(c, T_GLOBAL)
    caption(c, s["sid"], t)
    if si > 0 and t < 0.15: c.alpha_composite(tint(BG, int(255 * (1 - t / 0.15))))
    if si == len(TL) - 1:
        fo = clamp((s["dur"] - t) / 0.5)
        if fo < 1: c.alpha_composite(tint((0, 0, 0), int(255 * (1 - fo))))
    return c.convert("RGB")

def render_scene(si):
    s = TL[si]; n = int(round(s["dur"] * FPS))
    out, tmp = f"{WORK}/out/scene_{si:02d}.mp4", f"{WORK}/out/tmp_{si:02d}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-r", str(FPS), tmp], stdin=subprocess.PIPE)
    for i in range(n): p.stdin.write(frame(si, i / FPS).tobytes())
    p.stdin.close()
    if p.wait() == 0: os.replace(tmp, out)
    return si

def busy_times(si):
    """momenti da controllare: quando tutto è comparso (e prima di ogni 'until')"""
    s = TL[si]; its = items_of(s); sid = s["sid"]
    ats, untils = [], []
    for e in its:
        ats.append(at_time(sid, e.get("at")))
        for r in e.get("rows", []): ats.append(at_time(sid, r[2] if len(r) > 2 else None))
        if "until" in e: untils.append(at_time(sid, e["until"], 1e9))
    ts = []
    for u in sorted(set(untils)):
        before = [a for a in ats if a < u]
        ts.append(min(u - 0.05, max(before + [0]) + 0.45))
    ts.append(min(s["dur"] - 0.6, max(ats + [0]) + 0.6))
    return ts

def cover(path):
    """copertina: SPEC['cover'] = lista di elementi (stessi tipi, senza animazione)"""
    global TOTAL
    c = BGIMG.copy(); tot, TOTAL = TOTAL, 0
    for e in SPEC["cover"]:
        e = dict(e, at=0.0); e.pop("until", None)
        draw_el(c, "__cover__", e, 10.0, None)
    header(c, 0); TOTAL = tot
    c.convert("RGB").save(path, quality=92)
