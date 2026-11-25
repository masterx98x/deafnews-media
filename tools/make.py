#!/usr/bin/env python3
"""DeafNews TikTok — un comando per tutto.
uso: python3 make.py <comando> specs/<slug>.json
  setup            modelli Kokoro + pacchetti (una volta per sessione, senza spec)
  voice            voce per scena (rigenera solo le scene col testo cambiato)
  check            contact sheet dei momenti più pieni + copertina -> out/check.jpg
  still SID T      un fotogramma a grandezza piena -> out/still.jpg
  build            voce + render parallelo + mix + copertina + montaggio
  publish          copia video/copertina/spec nel repo, commit, push, verifica URL
"""
import os, sys, json, hashlib, subprocess, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
WORK = os.environ.get("DN_WORK", "/home/claude/dn-work")
KOK = os.environ.get("KOKORO_DIR", "/home/claude/kokoro")
RAW = "https://raw.githubusercontent.com/masterx98x/deafnews-media/main"
FX = ("rubberband=pitch=1.06:formant=preserved,highpass=f=90,equalizer=f=3200:t=q:w=1.2:g=3.5,"
      "equalizer=f=200:t=q:w=1:g=-2,acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=2,"
      "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
      "silenceremove=start_periods=1:start_threshold=-45dB,areverse")

def sh(*a, **k): return subprocess.run(list(a), check=True, **k)
def dur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]))

def setup():
    os.makedirs(KOK, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        if not os.path.exists(f"{KOK}/{f}"):
            sh("curl", "-sL", "-o", f"{KOK}/{f}", f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/{f}")
    sh(sys.executable, "-m", "pip", "install", "--break-system-packages", "-q", "kokoro-onnx", "soundfile")
    print("setup ok")

def voice(spec):
    os.makedirs(f"{WORK}/vo_raw", exist_ok=True); os.makedirs(f"{WORK}/vo", exist_ok=True)
    hp, dp = f"{WORK}/vo/hash.json", f"{WORK}/vo/durs.json"
    hashes = json.load(open(hp)) if os.path.exists(hp) else {}
    durs = json.load(open(dp)) if os.path.exists(dp) else {}
    k = None
    for s in spec["scenes"]:
        sid, h = s["id"], hashlib.md5(s["voice"].encode()).hexdigest()
        if hashes.get(sid) == h and os.path.exists(f"{WORK}/vo/{sid}.wav"): continue
        if k is None:
            from kokoro_onnx import Kokoro
            k = Kokoro(f"{KOK}/kokoro-v1.0.onnx", f"{KOK}/voices-v1.0.bin")
        import soundfile as sf
        a, sr = k.create(s["voice"], voice="im_nicola", speed=1.12, lang="it")
        sf.write(f"{WORK}/vo_raw/{sid}.wav", a, sr)
        sh("ffmpeg", "-y", "-v", "error", "-i", f"{WORK}/vo_raw/{sid}.wav", "-af", FX, "-ar", "24000", f"{WORK}/vo/{sid}.wav")
        durs[sid] = dur(f"{WORK}/vo/{sid}.wav"); hashes[sid] = h
    json.dump(durs, open(dp, "w")); json.dump(hashes, open(hp, "w"))
    tot = sum(durs[s["id"]] for s in spec["scenes"])
    print(f"voce ok: {tot:.1f}s di parlato, " + " ".join(f"{s['id']}={durs[s['id']]:.1f}" for s in spec["scenes"]))

# ---------- audio ----------
def mix():
    import numpy as np, soundfile as sf, engine as E, sfx as S
    SR = S.SR; N = int(E.TOTAL * SR) + SR
    vb, fb = np.zeros(N), np.zeros(N)
    def add(buf, sig, t, g=1.0):
        i = int(max(0, t) * SR)
        if i < N: seg = sig[:N - i]; buf[i:i + len(seg)] += seg * g
    for s in E.TL:
        a, sr = sf.read(f"{WORK}/vo/{s['sid']}.wav")
        if a.ndim > 1: a = a.mean(1)
        add(vb, np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a), s["start"] + s["off"])
    LIB = dict(pop=(lambda: S.pop(520), .55), boom=(lambda: S.boom(1.2), .9), glitch=(lambda: S.glitch(.35), .5),
               buzz=(lambda: S.buzz(.4), .5), ding=(lambda: S.ding(1320, .8), .45), success=(S.success, .5),
               typing=(lambda: S.typing(1.2), .6), whoosh=(lambda: S.whoosh(.8), .4), siren=(lambda: S.siren(1.4), .4),
               scratch=(lambda: S.scratch(.5), .5), boing=(S.boing, .5), click=(S.click, .5))
    def play(names, t):
        for n in ([names] if isinstance(names, str) else names):
            if n != "none": f, g = LIB[n]; add(fb, f(), t, g)
    add(fb, S.whoosh(.6), 0, .6)
    for s in E.TL[1:]: add(fb, S.whoosh(.5), s["start"] - .25, .35)
    for s in E.TL:
        sid, T0 = s["sid"], s["start"]
        for e in E.items_of(s):
            ta = T0 + E.at_time(sid, e.get("at")); typ = e["type"]
            if "sfx" in e: play(e["sfx"], ta); continue
            if typ == "title": add(fb, S.pop(450), ta, .55)
            elif typ == "emoji": add(fb, S.pop(560), ta, .45)
            elif typ == "badge":
                if e.get("impact"): add(fb, S.boom(1.2), ta, .9)
                elif e.get("color", "red") == "red": add(fb, S.buzz(.4), ta, .5)
                else: add(fb, S.pop(600), ta, .6)
            elif typ in ("pill", "card"): add(fb, S.pop(500), ta, .55)
            elif typ == "list":
                for i, r in enumerate(e["rows"]):
                    add(fb, S.pop(520), T0 + E.at_time(sid, r[2] if len(r) > 2 else None, ta - T0 + i * .4), .55)
            elif typ == "code":
                if "type_at" in e:
                    ty = E.at_time(sid, e["type_at"]); n = sum(len(l[0]) for l in e["lines"]) / 30
                    add(fb, S.typing(n), T0 + ty, .7)
                    if e.get("done"): add(fb, S.success(), T0 + ty + n + .2, .5)
                else: add(fb, S.typing(1.4), ta, .6)
                for ln in e["lines"]:
                    if len(ln) > 2: add(fb, S.pop(600), T0 + E.at_time(sid, ln[2]), .45)
            elif typ == "gauge": add(fb, S.siren(1.4), ta - .1, .4); add(fb, S.boom(1.3), ta, .9)
            elif typ == "timeline":
                add(fb, S.whoosh(1.2), ta, .4)
                if e.get("right_at"): add(fb, S.ding(1568, .6), T0 + E.at_time(sid, e["right_at"]), .4)
            elif typ == "hearts": add(fb, S.success(), ta, .5)
    mus = S.music(E.TOTAL + 1); mus = np.pad(mus, (0, max(0, N - len(mus))))[:N]
    env = S.lp_fast(np.abs(vb), 2200); env /= env.max() + 1e-9
    duck = 1 - .55 * np.clip(env * 6, 0, 1)
    fade = np.minimum(1, np.arange(N) / (.3 * SR)) * np.clip((E.TOTAL - np.arange(N) / SR) / 1.2, 0, 1)
    vb /= np.abs(vb).max()
    m = np.tanh((vb * .85 + fb * .55 + mus * .35 * duck * fade) * 1.1); m = m / np.abs(m).max() * .95
    m = m[:int(E.TOTAL * SR)]
    sf.write(f"{WORK}/out/mix.wav", np.stack([m, m], 1).astype(np.float32), SR)
    sh("ffmpeg", "-y", "-v", "error", "-i", f"{WORK}/out/mix.wav", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
       "-ar", "44100", "-c:a", "aac", "-b:a", "192k", f"{WORK}/out/mix.m4a")

# ---------- video ----------
def _rs(si):
    import engine as E; return E.render_scene(si)

def check():
    import engine as E
    from PIL import Image, ImageDraw
    shots = []
    for si, s in enumerate(E.TL):
        for t in E.busy_times(si): shots.append((f"{s['sid']} {t:.1f}s", E.frame(si, t)))
    E.cover(f"{WORK}/out/cover_check.jpg"); shots.append(("copertina", Image.open(f"{WORK}/out/cover_check.jpg")))
    tw, th, cols = 324, 576, 6
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), (0, 0, 0)); d = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(shots):
        x, y = i % cols * tw, i // cols * th
        sheet.paste(im.resize((tw, th)), (x, y)); d.rectangle((x, y, x + tw, y + 26), fill=(0, 0, 0)); d.text((x + 6, y + 6), lab, fill=(255, 255, 0))
    sheet.save(f"{WORK}/out/check.jpg", quality=80)
    print(f"check ok: {WORK}/out/check.jpg ({len(shots)} fotogrammi, totale {E.TOTAL:.1f}s)")

def build(spec, path):
    import engine as E
    from multiprocessing import Pool
    voice(spec); E.load(path)
    slug = spec["slug"]; out = f"{WORK}/out"
    for f in os.listdir(out):
        if f.startswith(("scene_", "tmp_")): os.remove(f"{out}/{f}")
    order = sorted(range(len(E.TL)), key=lambda i: -E.TL[i]["dur"])
    with Pool(os.cpu_count() or 2) as pool:
        job = pool.map_async(_rs, order)
        mix(); E.cover(f"{out}/copertina-{slug}.jpg")
        job.get()
    open(f"{out}/list.txt", "w").write("".join(f"file 'scene_{i:02d}.mp4'\n" for i in range(len(E.TL))))
    sh("ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", f"{out}/list.txt", "-c", "copy", f"{out}/video_only.mp4")
    final = f"{out}/{slug}-tiktok.mp4"
    sh("ffmpeg", "-y", "-v", "error", "-i", f"{out}/video_only.mp4", "-i", f"{out}/mix.m4a", "-map", "0:v", "-map", "1:a",
       "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", final)
    print(f"build ok: {final} ({dur(final):.1f}s, {os.path.getsize(final) / 1e6:.1f} MB) + {out}/copertina-{slug}.jpg")

def publish(spec, path):
    slug = spec["slug"]; out = f"{WORK}/out"
    shutil.copy(f"{out}/{slug}-tiktok.mp4", f"{REPO}/videos/{slug}.mp4")
    shutil.copy(f"{out}/copertina-{slug}.jpg", f"{REPO}/covers/{slug}.jpg")
    dst = f"{REPO}/specs/{slug}.json"
    if os.path.abspath(path) != dst: shutil.copy(path, dst)
    g = ["git", "-C", REPO, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com"]
    sh(*g, "add", f"videos/{slug}.mp4", f"covers/{slug}.jpg", f"specs/{slug}.json")
    msg = (f"Aggiungi video {slug}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
           "Claude-Session: https://claude.ai/code/session_01L6H1yNkRgj2T7pW5cbFkXg")
    sh(*g, "commit", "-q", "-m", msg)
    for i in range(3):
        if subprocess.run(g + ["push", "-q", "origin", "main"]).returncode == 0: break
        time.sleep(3)
    url = f"{RAW}/videos/{slug}.mp4"
    for i in range(10):
        code = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-I", url], capture_output=True, text=True).stdout
        if code == "200": break
        time.sleep(4)
    print(f"publish {'ok' if code == '200' else 'ERRORE ' + code}: {url}")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "setup": setup(); sys.exit()
    path = sys.argv[2]; spec = json.load(open(path))
    os.makedirs(f"{WORK}/out", exist_ok=True)
    if cmd == "voice": voice(spec)
    elif cmd == "publish": publish(spec, path)
    elif cmd == "build": build(spec, path)
    else:
        import engine as E
        voice(spec)  # in cache: rigenera solo le scene cambiate
        E.load(path)
        if cmd == "check": check()
        elif cmd == "still":
            si = [s["sid"] for s in E.TL].index(sys.argv[3])
            E.frame(si, float(sys.argv[4])).save(f"{WORK}/out/still.jpg", quality=88); print(f"{WORK}/out/still.jpg")
