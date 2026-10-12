"""Scar Face Shorts renderer (v2, brand identity).

Usage: python3 template/render.py episodes/<slug>.json [out.mp4]
Needs: Pillow (with raqm), numpy, ffmpeg.
"""
import json, math, os, sys, subprocess, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
FONT = os.path.join(ROOT, "template", "fonts", "ElMessiri.ttf")

W, H, FPS = 1080, 1920, 30
GOLD = (212, 175, 55)
GOLD_HI = (255, 214, 102)
BLACK = (11, 11, 11)
GRAY = (167, 167, 167)
WHITE = (245, 245, 245)

INTRO_D, ITEM_D, OUTRO_D = 3.0, 4.6, 4.0

_fc = {}
def font(size, weight=700):
    k = (size, weight)
    if k not in _fc:
        f = ImageFont.truetype(FONT, size, layout_engine=ImageFont.Layout.RAQM)
        f.set_variation_by_axes([weight])
        _fc[k] = f
    return _fc[k]

def ease_out(t):
    t = min(1.0, max(0.0, t)); return 1 - (1 - t) ** 3

def ease_in(t):
    t = min(1.0, max(0.0, t)); return t ** 3

# ---------------------------------------------------------------- background
def value_noise(h, w, scale, rng):
    gh, gw = h // scale + 2, w // scale + 2
    g = Image.fromarray((rng.random((gh, gw)) * 255).astype(np.uint8))
    return np.asarray(g.resize((gw * scale, gh * scale), Image.BICUBIC), dtype=np.float32)[:h, :w] / 255

def make_smoke(h, w, seed=7):
    rng = np.random.default_rng(seed)
    n = sum(value_noise(h, w, s, rng) * a for s, a in [(320, .5), (160, .25), (80, .15), (40, .1)])
    n = (n - n.min()) / (n.max() - n.min())
    n = np.clip((n - 0.45) / 0.55, 0, 1) ** 2.2
    img = np.zeros((h, w, 3), np.float32)
    for i, c in enumerate(GOLD):
        img[..., i] = BLACK[i] + n * c * 0.55
    return Image.fromarray(img.clip(0, 255).astype(np.uint8))

SMOKE = make_smoke(H + 600, W)

def skyline_strip():
    src = Image.open(os.path.join(BRAND, "banner_original.png")).convert("RGB")
    sw, sh = src.size
    crop = src.crop((0, int(sh * .33), int(sw * .345), int(sh * .68)))  # Riyadh towers, left of banner
    crop = crop.resize((W, int(W * crop.height / crop.width)), Image.LANCZOS)
    mask = Image.new("L", crop.size, 0); d = ImageDraw.Draw(mask)
    for y in range(crop.height):
        a = min(1, y / (crop.height * .45))
        d.line([(0, y), (W, y)], fill=int(255 * a * 0.85))
    return crop, mask

SKY, SKY_M = skyline_strip()
LOGO = Image.open(os.path.join(BRAND, "logo_sf_1024.png")).convert("RGBA")
AVATAR = Image.open(os.path.join(BRAND, "avatar_800x800.png")).convert("RGBA")

rng = np.random.default_rng(3)
EMBERS = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(40, 140), rng.uniform(2, 6), rng.uniform(0, 6.28))
          for _ in range(70)]

def background(gt):
    off = int(600 - (gt * 22) % 600)
    img = SMOKE.crop((0, off, W, off + H)).copy()
    img.paste(SKY, (0, H - SKY.height), SKY_M)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for x0, y0, sp, r, ph in EMBERS:
        y = (y0 - gt * sp) % H
        x = x0 + 18 * math.sin(gt * 1.3 + ph)
        a = int(140 + 110 * math.sin(gt * 5 + ph))
        d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD_HI + (max(0, a),))
    lay = lay.filter(ImageFilter.GaussianBlur(1.2))
    return Image.alpha_composite(img.convert("RGBA"), lay)

# ---------------------------------------------------------------- pieces
def paste_logo(canvas, size, cx, cy, alpha=255):
    lg = LOGO.resize((size, size), Image.LANCZOS)
    if alpha < 255:
        lg.putalpha(lg.getchannel("A").point(lambda v: v * alpha // 255))
    canvas.alpha_composite(lg, (int(cx - size / 2), int(cy - size / 2)))

def header(canvas, series):
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([50, 80, W - 50, 210], 34, fill=(0, 0, 0, 170), outline=GOLD + (200,), width=3)
    paste_logo(canvas, 150, 135, 145)
    d.text((W - 95, 145), series, font=font(56), fill=GOLD, anchor="rm", direction="rtl")

def progress(canvas, gt, total):
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, H - 12, W, H], fill=(40, 40, 40, 255))
    d.rectangle([0, H - 12, int(W * gt / total), H], fill=GOLD + (255,))

def glow_text(canvas, xy, text, f, fill, glow=GOLD, r=14, anchor="mm"):
    g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).text(xy, text, font=f, fill=glow + (200,), anchor=anchor, direction="rtl")
    canvas.alpha_composite(g.filter(ImageFilter.GaussianBlur(r)))
    ImageDraw.Draw(canvas).text(xy, text, font=f, fill=fill, anchor=anchor, direction="rtl")

def sweep(canvas, p):
    """gold light sweep across the frame, p in [0,1]"""
    if not 0 < p < 1: return
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
    x = -400 + p * (W + 800)
    d.polygon([(x, 0), (x + 160, 0), (x - 240, H), (x - 400, H)], fill=GOLD_HI + (110,))
    canvas.alpha_composite(g.filter(ImageFilter.GaussianBlur(30)))

# ---------------------------------------------------------------- scenes
def scene_intro(c, t, ep):
    p = ease_out(t / 0.7)
    size = int(200 + 380 * p)
    paste_logo(c, size, W / 2, 700, int(255 * min(1, t / 0.3)))
    if t > 0.5:
        q = ease_out((t - 0.5) / 0.5)
        lay = Image.new("RGBA", c.size, (0, 0, 0, 0))
        glow_text(lay, (W / 2, 1080 + (1 - q) * 60), ep["intro"]["title"], font(120), GOLD_HI)
        ImageDraw.Draw(lay).text((W / 2, 1230 + (1 - q) * 60), ep["intro"]["sub"], font=font(66, 600),
                                 fill=WHITE, anchor="mm", direction="rtl")
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * q)))
        c.alpha_composite(lay)
    sweep(c, (t - 0.2) / 0.9)

def card_layer(it, num, t):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    cy = 560
    d.rounded_rectangle([60, cy, W - 60, cy + 880], 46, fill=(8, 8, 8, 225), outline=GOLD + (255,), width=5)
    d.rounded_rectangle([75, cy + 15, W - 75, cy + 865], 38, outline=(255, 255, 255, 25), width=2)
    # number badge
    d.ellipse([W / 2 - 95, cy - 95, W / 2 + 95, cy + 95], fill=GOLD + (255,), outline=BLACK + (255,), width=8)
    d.text((W / 2, cy - 4), num, font=font(118), fill=BLACK, anchor="mm")
    def fade(start):  # per-element alpha
        return int(255 * ease_out((t - start) / 0.4))
    a = fade(0.35)
    d.rounded_rectangle([W / 2 - 280, cy + 140, W / 2 + 280, cy + 232], 46, fill=GOLD + (a,))
    d.text((W / 2, cy + 184), it["tag"], font=font(52), fill=BLACK + (a,), anchor="mm", direction="rtl")
    a = fade(0.6)
    d.text((W / 2, cy + 345), it["title"], font=font(96), fill=WHITE + (a,), anchor="mm", direction="rtl")
    d.line([W / 2 - 120, cy + 425, W / 2 + 120, cy + 425], fill=GOLD + (a,), width=4)
    a = fade(0.9)
    for i, ln in enumerate(it["body"]):
        d.text((W / 2, cy + 515 + i * 92), ln, font=font(62, 500), fill=GRAY + (a,), anchor="mm", direction="rtl")
    a = fade(1.3)
    d.text((W / 2, cy + 790), it["plat"], font=font(50), fill=GOLD_HI + (a,), anchor="mm")
    return lay

def rounded(img, r):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], r, fill=255)
    img = img.convert("RGBA"); img.putalpha(m); return img

def cover(img, w, h, zoom=1.0):
    s = max(w / img.width, h / img.height) * zoom
    im = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))

def load_item_images(ep):
    mpath = os.path.join(ROOT, "assets", ep["slug"], "manifest.json")
    if not os.path.exists(mpath): return
    man = json.load(open(mpath, encoding="utf-8"))
    for i, it in enumerate(ep["items"]):
        e = man.get(str(i))
        if not e: continue
        fn = e["files"].get(it.get("shot", "shot0"))
        if not fn: continue
        shot = Image.open(os.path.join(ROOT, "assets", ep["slug"], fn)).convert("RGB")
        it["_shot"] = shot
        bg = cover(shot, W, H, 1.0).filter(ImageFilter.GaussianBlur(28))
        bg = Image.blend(bg, Image.new("RGB", (W, H), BLACK), 0.55)
        it["_bg"] = bg

def item_background(it, t, gt):
    base = background(gt)
    if "_bg" not in it: return base
    k = min(ease_out(t / 0.5), 1 - ease_in((t - (ITEM_D - 0.35)) / 0.35))
    z = 1 + 0.06 * t / ITEM_D
    bg = cover(it["_bg"], W, H, z).convert("RGBA")
    return Image.blend(base, bg, max(0.0, min(1.0, k)))

PANEL_W, PANEL_H, PANEL_Y = 960, 540, 330
def card_layer_img(it, num, t):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    z = 1 + 0.07 * t / ITEM_D                         # slow ken-burns inside the panel
    panel = rounded(cover(it["_shot"], PANEL_W, PANEL_H, z), 34)
    lay.alpha_composite(panel, ((W - PANEL_W) // 2, PANEL_Y))
    d.rounded_rectangle([(W - PANEL_W) // 2, PANEL_Y, (W + PANEL_W) // 2, PANEL_Y + PANEL_H], 34,
                        outline=GOLD + (255,), width=5)
    d.ellipse([W / 2 - 85, PANEL_Y - 85, W / 2 + 85, PANEL_Y + 85], fill=GOLD + (255,), outline=BLACK + (255,), width=8)
    d.text((W / 2, PANEL_Y - 4), num, font=font(104), fill=BLACK, anchor="mm")
    cy = PANEL_Y + PANEL_H + 40
    d.rounded_rectangle([60, cy, W - 60, cy + 650], 46, fill=(8, 8, 8, 230), outline=GOLD + (255,), width=5)
    def fade(start): return int(255 * ease_out((t - start) / 0.4))
    a = fade(0.35)
    d.rounded_rectangle([W / 2 - 280, cy + 45, W / 2 + 280, cy + 137], 46, fill=GOLD + (a,))
    d.text((W / 2, cy + 89), it["tag"], font=font(52), fill=BLACK + (a,), anchor="mm", direction="rtl")
    a = fade(0.6)
    d.text((W / 2, cy + 240), it["title"], font=font(92), fill=WHITE + (a,), anchor="mm", direction="rtl")
    d.line([W / 2 - 120, cy + 315, W / 2 + 120, cy + 315], fill=GOLD + (a,), width=4)
    a = fade(0.9)
    for i, ln in enumerate(it["body"]):
        d.text((W / 2, cy + 395 + i * 84), ln, font=font(58, 500), fill=GRAY + (a,), anchor="mm", direction="rtl")
    a = fade(1.3)
    d.text((W / 2, cy + 590), it["plat"], font=font(48), fill=GOLD_HI + (a,), anchor="mm")
    return lay

def scene_item(c, t, it, num):
    lay = card_layer_img(it, num, t) if "_shot" in it else card_layer(it, num, t)
    x = int((1 - ease_out(t / 0.5)) * W)            # slide in from right
    out = ease_in((t - (ITEM_D - 0.35)) / 0.35)      # slide out to left
    x -= int(out * W)
    c.alpha_composite(lay, (x, 0)) if x >= 0 else c.alpha_composite(lay.crop((-x, 0, W, H)), (0, 0))

def scene_outro(c, t, ep):
    p = ease_out(t / 0.6)
    s = int(260 + 140 * p)
    av = AVATAR.resize((s, s), Image.LANCZOS)
    m = Image.new("L", (s, s), 0); ImageDraw.Draw(m).ellipse([0, 0, s - 1, s - 1], fill=255)
    av.putalpha(m)
    d = ImageDraw.Draw(c)
    d.ellipse([W / 2 - s / 2 - 8, 640 - s / 2 - 8, W / 2 + s / 2 + 8, 640 + s / 2 + 8], outline=GOLD + (255,), width=6)
    c.alpha_composite(av, (int(W / 2 - s / 2), int(640 - s / 2)))
    if t > 0.3:
        q = ease_out((t - 0.3) / 0.5)
        pulse = 1 + 0.04 * math.sin(t * 6)
        glow_text(c, (W / 2, 990), ep["outro"]["title"], font(int(104 * pulse)), GOLD_HI)
        d.text((W / 2, 1120), ep["outro"]["sub"], font=font(68, 600), fill=WHITE + (int(255 * q),), anchor="mm", direction="rtl")
    if t > 0.8:
        q = ease_out((t - 0.8) / 0.5)
        d.rounded_rectangle([100, 1250, W - 100, 1390], 70, fill=GOLD + (int(255 * q),))
        d.text((W / 2, 1320), ep["outro"]["cta"], font=font(50), fill=BLACK + (int(255 * q),), anchor="mm", direction="rtl")
        d.text((W / 2, 1460), "@Scarfce001", font=font(56), fill=GRAY + (int(255 * q),), anchor="mm")

AR = "٠١٢٣٤٥٦٧٨٩"

def timeline(ep):
    tl = [("intro", INTRO_D, None)]
    for i, it in enumerate(ep["items"]):
        tl.append(("item", ITEM_D, (it, AR[i + 1])))
    tl.append(("outro", OUTRO_D, None))
    return tl

# ---------------------------------------------------------------- audio
SR = 44100
def synth_audio(ep, total, cuts, path):
    n = int(total * SR); t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    bpm = 100; beat = 60 / bpm
    def add(sig, at):
        i = int(at * SR); j = min(n, i + len(sig)); out[i:j] += sig[: j - i]
    # kick
    kt = np.arange(int(.35 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9) * .55
    # hat
    hn = np.random.default_rng(1).standard_normal(int(.06 * SR)).astype(np.float32)
    hat = np.diff(hn, prepend=0) * np.exp(-np.arange(len(hn)) / SR * 70) * .07
    b = 0.0; k = 0
    while b < total - 0.5:
        if k % 2 == 0: add(kick, b)
        add(hat, b + beat / 2)
        b += beat; k += 1
    # dark pad (A minor-ish), slow fade in/out
    pad = sum(np.sin(2 * np.pi * f * t) * a for f, a in [(55, .10), (110, .06), (130.8, .04), (164.8, .035)])
    env = np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 1.5)
    out += (pad * env * (0.8 + 0.2 * np.sin(2 * np.pi * t / 4))).astype(np.float32)
    # whooshes at scene cuts
    wl = int(.5 * SR); wt = np.arange(wl) / SR
    wn = np.random.default_rng(2).standard_normal(wl).astype(np.float32)
    whoosh = np.convolve(wn, np.ones(30) / 30, "same") * np.sin(np.pi * wt / .5) ** 2 * .45
    for c in cuts: add(whoosh, max(0, c - 0.25))
    # impact on logo reveal
    add(kick * 1.6, 0.05)
    out = np.tanh(out * 1.2) * 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((out * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- render
def render(ep_path, out_path):
    ep = json.load(open(ep_path, encoding="utf-8"))
    load_item_images(ep)
    tl = timeline(ep)
    total = sum(d for _, d, _ in tl)
    tmp = tempfile.mkdtemp()
    cuts, n, gt = [], 0, 0.0
    for kind, dur, data in tl:
        cuts.append(gt)
        for i in range(int(dur * FPS)):
            t = i / FPS
            c = item_background(data[0], t, gt + t) if kind == "item" else background(gt + t)
            header(c, ep["series"])
            if kind == "intro": scene_intro(c, t, ep)
            elif kind == "item": scene_item(c, t, *data)
            else: scene_outro(c, t, ep)
            progress(c, gt + t, total)
            # fade from black at very start, to black at very end
            if gt + t < 0.25 or total - (gt + t) < 0.3:
                k = min((gt + t) / 0.25, (total - gt - t) / 0.3)
                c = Image.blend(Image.new("RGBA", (W, H), BLACK + (255,)), c, max(0, min(1, k)))
            c.convert("RGB").save(os.path.join(tmp, f"{n:05d}.jpg"), quality=92)
            n += 1
        gt += dur
    wav = os.path.join(tmp, "a.wav")
    synth_audio(ep, total, cuts[1:], wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(tmp, "%05d.jpg"),
                    "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path], check=True)
    return out_path, total

if __name__ == "__main__":
    ep = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "shorts", os.path.basename(ep).replace(".json", ".mp4"))
    print(render(ep, out))
