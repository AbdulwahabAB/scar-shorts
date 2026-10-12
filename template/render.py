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

INTRO_D, ITEM_D, OUTRO_D = 3.0, 6.5, 4.0

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
# Default channel avatar: avatar-v2 logo ring (reads best small); falls back to the original avatar.
_AV_DEFAULT = os.path.join(BRAND, "avatar-v2", "avatar_C_logo_ring.png")
AVATAR = Image.open(_AV_DEFAULT if os.path.exists(_AV_DEFAULT)
                    else os.path.join(BRAND, "avatar_800x800.png")).convert("RGBA")

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

# ---------------------------------------------------------------- text: measure, fit, blend
class TextOverflow(Exception):
    """Raised when a piece of text cannot fit its box, even wrapped and at its minimum size."""

_MEAS = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

def ink_w(text, f, direction="rtl"):
    l, _, r, _ = _MEAS.textbbox((0, 0), text, font=f, direction=direction)
    return r - l

def _latin(tok):
    return bool(tok) and all(ord(ch) < 0x0600 for ch in tok) and any(ch.isalpha() for ch in tok)

def _split2(text, f, max_w, direction, sep, allow_name_break=True):
    """Best balanced 2-line split on `sep` where both lines fit, else None.
    Avoids breaking inside an English name ("Warrior | of Light") when another break works."""
    parts = text.split(sep)
    best = None
    for k in range(1, len(parts)):
        a, b = sep.join(parts[:k]), sep.join(parts[k:])
        wa, wb = ink_w(a, f, direction), ink_w(b, f, direction)
        if wa <= max_w and wb <= max_w:
            inside_name = sep == " " and _latin(parts[k - 1]) and _latin(parts[k])
            if inside_name and not allow_name_break: continue
            score = (inside_name, max(wa, wb))
            if best is None or score < best[0]:
                best = (score, [a, b])
    return best[1] if best else None

def fit_text(text, max_w, start, min_size, weight=700, max_lines=1, wrap_below=None,
             direction="rtl", sep=" ", where="text"):
    """Return (font, lines). Order: one line down to `wrap_below`, then two lines down to
    `min_size`, then one line down to `min_size`. Never drops text: raises TextOverflow."""
    sizes = list(range(start, min_size - 1, -2))
    floor1 = wrap_below if (max_lines > 1 and wrap_below) else min_size
    for sz in sizes:
        if sz >= floor1 and ink_w(text, font(sz, weight), direction) <= max_w:
            return font(sz, weight), [text]
    if max_lines >= 2:
        for allow in (False, True):              # shrink before splitting an English name
            for sz in sizes:
                lines = _split2(text, font(sz, weight), max_w, direction, sep, allow)
                if lines:
                    return font(sz, weight), lines
    for sz in sizes:
        if sz < floor1 and ink_w(text, font(sz, weight), direction) <= max_w:
            return font(sz, weight), [text]
    w = ink_w(text, font(min_size, weight), direction)
    raise TextOverflow(f'{where}: "{text}" is {w}px wide at the minimum {min_size}px font; the box is '
                       f'{max_w}px' + (" (also tried 2 lines)" if max_lines > 1 else "") +
                       ". Shorten the text.")

_tiles = {}
def text_tile(text, f, fill, direction="rtl"):
    """Text drawn once at full opacity on its own transparent tile; offsets are from the 'mm' anchor."""
    key = (text, f.size, f.getname(), id(f), fill, direction)
    if key not in _tiles:
        l, t, r, b = _MEAS.textbbox((0, 0), text, font=f, anchor="mm", direction=direction)
        pad = 6
        tile = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((-l + pad, -t + pad), text, font=f, fill=fill[:3] + (255,),
                                  anchor="mm", direction=direction)
        _tiles[key] = (tile, l - pad, t - pad)
    return _tiles[key]

def with_alpha(tile, alpha):
    if alpha >= 255: return tile
    t = tile.copy(); t.putalpha(t.getchannel("A").point(lambda v: v * alpha // 255)); return t

def blend_on(canvas, tile, x, y, alpha=255):
    """Alpha-composite (never pixel-replace) so faded text blends instead of punching holes."""
    if alpha <= 0: return
    canvas.alpha_composite(with_alpha(tile, alpha), (int(x), int(y)))

def put_text(canvas, cx, cy, text, f, fill, alpha=255, direction="rtl"):
    tile, ox, oy = text_tile(text, f, fill, direction)
    blend_on(canvas, tile, cx + ox, cy + oy, alpha)

def pill_tile(w, h, r, fill=None, outline=None, width=0, text=None, f=None, tcolor=None):
    tile = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0)); d = ImageDraw.Draw(tile)
    d.rounded_rectangle([0, 0, w - 1, h - 1], r, fill=fill, outline=outline, width=width)
    if text:
        t, ox, oy = text_tile(text, f, tcolor)
        tile.alpha_composite(t, (int(w / 2 + ox), int(h / 2 + oy)))
    return tile

# ---------------------------------------------------------------- data checks
PLATFORMS = {"PS5", "PS4", "Xbox", "Switch 2", "Switch", "PC"}

def check_platforms(it, where):
    toks = [p.strip() for p in it["plat"].split("•")]
    errs = [f'{where} plat: unknown platform "{p}" (allowed: {", ".join(sorted(PLATFORMS))})'
            for p in toks if p not in PLATFORMS]
    texts = " ".join([it.get("title", ""), it.get("info", "")] + list(it.get("bullets", [])))
    if "Switch 2" in texts and "Switch 2" not in toks:
        errs.append(f'{where}: text says "Switch 2" but platforms say {it["plat"]!r}')
    if "Switch" in toks and "Switch 2" in texts:
        errs.append(f'{where}: platforms list plain "Switch" while the text says "Switch 2"')
    return errs

# ---------------------------------------------------------------- scenes
def scene_intro(c, t, ep):
    """Hook first (readable from frame 1), then a short logo slam."""
    hook = ep["intro"].get("hook") or [ep["intro"]["title"], ep["intro"]["sub"]]
    p = ease_out(t / 0.25)
    lay = Image.new("RGBA", c.size, (0, 0, 0, 0))
    f1, _ = fit_text(hook[0], 960, 104, 56, where="intro hook[0]")
    glow_text(lay, (W / 2, 640), hook[0], font(max(40, int(f1.size * (0.9 + 0.1 * p)))), GOLD_HI, r=16)
    if len(hook) > 1:
        q = ease_out((t - 0.35) / 0.35)
        f2, _ = fit_text(hook[1], 960, 84, 48, where="intro hook[1]")
        put_text(lay, W / 2, 790 + (1 - q) * 40, hook[1], f2, WHITE, int(255 * q))
    c.alpha_composite(lay)
    if t > 1.1:                                   # logo slam
        q = ease_out((t - 1.1) / 0.35)
        size = int(560 - 200 * q)
        paste_logo(c, size, W / 2, 1180, int(255 * q))
    sweep(c, (t - 1.1) / 0.8)

def rounded(img, r):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], r, fill=255)
    img = img.convert("RGBA"); img.putalpha(m); return img

def cover(img, w, h, zoom=1.0):
    s = max(w / img.width, h / img.height) * zoom
    im = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))

def _prep_item(it, shot):
    it["_shot"] = shot
    bg = cover(shot, W, H, 1.0).filter(ImageFilter.GaussianBlur(28))
    it["_bg"] = Image.blend(bg, Image.new("RGB", (W, H), BLACK), 0.55)

PANEL_W, PANEL_H, PANEL_Y = 960, 430, 330

def load_item_images(ep):
    mpath = os.path.join(ROOT, "assets", ep["slug"], "manifest.json")
    man = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {}
    brand_panel = Image.open(os.path.join(BRAND, "banner_original.png")).convert("RGB")
    bw, bh = brand_panel.size
    brand_panel = brand_panel.crop((0, int(bh * .30), int(bw * .55), int(bh * .70)))   # Riyadh skyline
    for i, it in enumerate(ep["items"]):
        e = man.get(str(i)) or {}
        meta = e.get("meta") or {}
        # "price" absent -> use the Steam (SA) price; "price": null or "" -> no badge.
        if "price" not in it and meta.get("price"):
            it["price"] = meta["price"].replace("SR", "ريال").strip()
        fn = (e.get("files") or {}).get(it.get("shot", "shot0"))
        shot = Image.open(os.path.join(ROOT, "assets", ep["slug"], fn)).convert("RGB") if fn else brand_panel
        _prep_item(it, shot)
        clip = (e.get("files") or {}).get("clip")
        if clip and not it.get("no_clip"):
            d = tempfile.mkdtemp()
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", os.path.join(ROOT, "assets", ep["slug"], clip),
                            "-vf", f"scale={PANEL_W}:{PANEL_H}", "-q:v", "3", os.path.join(d, "%04d.jpg")], check=True)
            it["_clip"] = sorted(os.path.join(d, f) for f in os.listdir(d))

def item_background(it, t, gt):
    base = background(gt)
    if "_bg" not in it: return base
    k = min(ease_out(t / 0.5), 1 - ease_in((t - (ITEM_D - 0.35)) / 0.35))
    z = 1 + 0.06 * t / ITEM_D
    bg = cover(it["_bg"], W, H, z).convert("RGBA")
    return Image.blend(base, bg, max(0.0, min(1.0, k)))

CARD_X0, CARD_X1 = 60, W - 60
CARD_Y = PANEL_Y + PANEL_H + 35
TEXT_W = 880                  # 40px padding each side of the 960px card
BULLET_W = 800                # leaves room for the gold dot
SAFE_BOTTOM = 1700            # keep the card above YouTube's caption/button overlay
ENTER, EXIT = 0.35, 0.35      # card fades + drifts vertically; it never crosses a frame edge

def layout_card(it, where):
    """Lay out every text element of a card once, validating that all of it fits.
    Returns {"h": card height, "els": [(tile, x, y, fade_start), ...]} with card-relative y."""
    els = []
    def add_text(text, f, fill, cy, start, direction="rtl"):
        tile, ox, oy = text_tile(text, f, fill, direction)
        els.append((tile, W / 2 + ox, cy + oy, start))
    y = 36
    f, (tag,) = fit_text(it["tag"], 760, 58, 44, where=f"{where} tag")
    pw = max(600, ink_w(tag, f) + 90)
    els.append((pill_tile(pw, 96, 48, fill=GOLD + (255,), text=tag, f=f, tcolor=BLACK), (W - pw) / 2, y, 0.35))
    y += 96 + 26
    f, lines = fit_text(it["title"], TEXT_W, 104, 52, max_lines=2, wrap_below=60, where=f"{where} title")
    lh = int(f.size * 1.2)
    for ln in lines:
        add_text(ln, f, WHITE, y + lh / 2, 0.6); y += lh
    if it.get("info"):
        y += 6
        f, (ln,) = fit_text(it["info"], TEXT_W, 40, 30, 500, where=f"{where} info")
        add_text(ln, f, GRAY, y + 25, 0.6); y += 50
    y += 16
    els.append((pill_tile(240, 4, 0, fill=GOLD + (255,)), W / 2 - 120, y, 0.6)); y += 4 + 24
    for i, b in enumerate(it.get("bullets", [])):
        f, lines = fit_text(b, BULLET_W, 54, 40, 600, max_lines=2, wrap_below=46, where=f"{where} bullets[{i}]")
        lh = int(f.size * 1.42)
        for j, ln in enumerate(lines):
            cy = y + lh / 2
            add_text(ln, f, WHITE, cy, 1.1 + i * 0.6)
            if j == 0:
                xr = W / 2 + ink_w(ln, f) / 2
                els.append((pill_tile(18, 18, 9, fill=GOLD + (255,)), xr + 18, cy - 9, 1.1 + i * 0.6))
            y += lh
        y += 8
    price = it.get("price")
    if price:
        y += 14
        f, (pt,) = fit_text(price, 640, 58, 44, where=f"{where} price")
        pw = ink_w(pt, f) + 90
        els.append((pill_tile(pw, 90, 40, fill=(56, 47, 18, 255), outline=GOLD + (255,), width=4,
                              text=pt, f=f, tcolor=GOLD_HI), (W - pw) / 2, y, 2.4))
        y += 90
    y += 22
    f, lines = fit_text(it["plat"], TEXT_W, 50, 34, max_lines=2, wrap_below=40, direction="ltr",
                        sep=" • ", where=f"{where} plat")
    lh = int(f.size * 1.35)
    for ln in lines:
        add_text(ln, f, GOLD, y + lh / 2, 2.4, direction="ltr"); y += lh
    h = int(y + 40)
    # Hard checks: every element inside the card, the card inside the safe area.
    for tile, x, ty, _ in els:
        if x < CARD_X0 + 10 or x + tile.width > CARD_X1 - 10:
            raise TextOverflow(f"{where}: an element is {int(x + tile.width - x)}px wide and leaves the card "
                               f"(x={int(x)}..{int(x + tile.width)}, card={CARD_X0}..{CARD_X1}).")
    if CARD_Y + h > SAFE_BOTTOM:
        raise TextOverflow(f"{where}: card content is {h}px tall but only {SAFE_BOTTOM - CARD_Y}px fit above "
                           f"the YouTube overlay. Shorten bullets or drop the price/info line.")
    return {"h": h, "els": els}

def card_layer_img(it, num, t):
    card = it["_card"]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    if it.get("_clip"):                               # gameplay clip (muted) inside the panel
        fr = it["_clip"][min(int(t * FPS), len(it["_clip"]) - 1)]
        panel = rounded(Image.open(fr).convert("RGB"), 34)
    else:
        z = 1 + 0.07 * t / ITEM_D                     # slow ken-burns on the screenshot
        panel = rounded(cover(it["_shot"], PANEL_W, PANEL_H, z), 34)
    lay.alpha_composite(panel, ((W - PANEL_W) // 2, PANEL_Y))
    d.rounded_rectangle([(W - PANEL_W) // 2, PANEL_Y, (W + PANEL_W) // 2, PANEL_Y + PANEL_H], 34,
                        outline=GOLD + (255,), width=5)
    d.ellipse([W / 2 - 80, PANEL_Y - 80, W / 2 + 80, PANEL_Y + 80], fill=GOLD + (255,), outline=BLACK + (255,), width=8)
    put_text(lay, W / 2, PANEL_Y - 2, str(num), font(98), BLACK, direction="ltr")   # Western digits: ٥ reads as 0
    d.rounded_rectangle([CARD_X0, CARD_Y, CARD_X1, CARD_Y + card["h"]], 46, fill=(8, 8, 8, 232),
                        outline=GOLD + (255,), width=5)
    for tile, x, y, start in card["els"]:
        blend_on(lay, tile, x, CARD_Y + y, int(255 * ease_out((t - start) / 0.4)))
    return lay

def scene_item(c, t, it, num):
    lay = card_layer_img(it, num, t)
    k_in = ease_out(t / ENTER)
    k_out = 1 - ease_in((t - (ITEM_D - EXIT)) / EXIT)
    k = max(0.0, min(k_in, k_out))
    dy = int((1 - k_in) * 70 - (1 - k_out) * 40)     # small vertical drift only: no edge clipping
    if k <= 0: return
    if k < 1: lay = with_alpha(lay, int(255 * k))
    if dy >= 0: c.alpha_composite(lay.crop((0, 0, W, H - dy)), (0, dy))
    else:       c.alpha_composite(lay.crop((0, -dy, W, H)), (0, 0))

def scene_outro(c, t, ep):
    p = ease_out(t / 0.6)
    s = int(260 + 140 * p)
    av = AVATAR.resize((s, s), Image.LANCZOS)
    m = Image.new("L", (s, s), 0); ImageDraw.Draw(m).ellipse([0, 0, s - 1, s - 1], fill=255)
    av.putalpha(m)
    d = ImageDraw.Draw(c)
    if not os.path.exists(_AV_DEFAULT):   # v2 avatar already has its own gold ring
        d.ellipse([W / 2 - s / 2 - 8, 640 - s / 2 - 8, W / 2 + s / 2 + 8, 640 + s / 2 + 8], outline=GOLD + (255,), width=6)
    c.alpha_composite(av, (int(W / 2 - s / 2), int(640 - s / 2)))
    o = ep["outro"]
    if t > 0.3:
        q = ease_out((t - 0.3) / 0.5)
        pulse = 1 + 0.04 * math.sin(t * 6)
        ft, _ = fit_text(o["title"], int(960 / 1.04), 104, 60, where="outro title")   # room for the 4% pulse
        glow_text(c, (W / 2, 990), o["title"], font(int(ft.size * pulse)), GOLD_HI)
        fs, _ = fit_text(o["sub"], 960, 68, 44, 600, where="outro sub")
        put_text(c, W / 2, 1120, o["sub"], fs, WHITE, int(255 * q))
    if t > 0.8:
        q = int(255 * ease_out((t - 0.8) / 0.5))
        fc, _ = fit_text(o["cta"], W - 280, 50, 36, where="outro cta")
        blend_on(c, pill_tile(W - 200, 140, 70, fill=GOLD + (255,), text=o["cta"], f=fc, tcolor=BLACK), 100, 1250, q)
        put_text(c, W / 2, 1460, "@Scarfce001", font(56), GRAY, q, direction="ltr")

def timeline(ep):
    tl = [("intro", INTRO_D, None)]
    n = len(ep["items"])
    for i, it in enumerate(ep["items"]):
        num = n - i if ep.get("countdown") else i + 1     # countdown: 5, 4, 3, 2, 1
        tl.append(("item", ITEM_D, (it, num)))
    tl.append(("outro", OUTRO_D, None))
    return tl

def validate_episode(ep):
    """Lay out every card and text line once. Collects every overflow/data problem and fails loudly."""
    errs = []
    def guard(fn, *a, **k):
        try: return fn(*a, **k)
        except TextOverflow as e: errs.append(str(e))
    guard(fit_text, ep["series"], 720, 56, 56, where="header series")
    hook = ep["intro"].get("hook") or [ep["intro"]["title"], ep["intro"]["sub"]]
    guard(fit_text, hook[0], 960, 104, 56, where="intro hook[0]")
    if len(hook) > 1: guard(fit_text, hook[1], 960, 84, 48, where="intro hook[1]")
    o = ep["outro"]
    guard(fit_text, o["title"], int(960 / 1.04), 104, 60, where="outro title")
    guard(fit_text, o["sub"], 960, 68, 44, 600, where="outro sub")
    guard(fit_text, o["cta"], W - 280, 50, 36, where="outro cta")
    for i, it in enumerate(ep["items"]):
        where = f'{ep["slug"]} item {i} ({it.get("title", "?")})'
        errs += check_platforms(it, where)
        card = guard(layout_card, it, where)
        if card: it["_card"] = card
    if errs:
        raise SystemExit("Render aborted, text does not fit or data is inconsistent:\n  - " + "\n  - ".join(errs))

# ---------------------------------------------------------------- audio
SR = 44100
DROP_AT = 1.1          # logo slam in the intro: full beat drops here

def synth_audio(ep, total, cuts, path):
    """Energetic dark trap bed (140 BPM, A minor) + risers/impacts on scene cuts. All synthesized."""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(11)
    n = int(total * SR) + SR
    drums = np.zeros(n, np.float32); music = np.zeros(n, np.float32); fx = np.zeros(n, np.float32)
    duck = np.ones(n, np.float32)

    def add(buf, sig, at, gain=1.0):
        i = int(at * SR)
        if i >= n or i + len(sig) <= 0: return
        j = min(n, i + len(sig)); buf[max(0, i):j] += (sig[max(0, -i): j - i] * gain).astype(np.float32)
    def env(L, a, d):            # attack/decay envelope, seconds
        t = np.arange(int(L * SR)) / SR
        return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
    def bp(x, lo, hi): return sosfilt(butter(2, [lo, hi], "bandpass", fs=SR, output="sos"), x)
    def lp(x, f): return sosfilt(butter(2, f, "lowpass", fs=SR, output="sos"), x)
    def hp(x, f): return sosfilt(butter(2, f, "highpass", fs=SR, output="sos"), x)

    # ---- instruments
    kt = np.arange(int(.45 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 140 * np.exp(-kt * 38)) / SR) * np.exp(-kt * 7)
    kick[:120] += rng.standard_normal(120) * np.linspace(.6, 0, 120)            # click
    kick = np.tanh(kick * 1.8) * .9
    clap = bp(rng.standard_normal(int(.25 * SR)), 900, 4500) * env(.25, .002, .06) * .9
    clap += np.sin(2 * np.pi * 190 * np.arange(len(clap)) / SR) * env(.25, .001, .04) * .35
    hat = hp(rng.standard_normal(int(.05 * SR)), 7000) * env(.05, .0005, .012) * .28
    ohat = hp(rng.standard_normal(int(.25 * SR)), 6500) * env(.25, .001, .09) * .18

    def bass808(freq, L, glide_from=None):
        t = np.arange(int(L * SR)) / SR
        f = np.full_like(t, freq)
        if glide_from: f = freq + (glide_from - freq) * np.exp(-t * 18)
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = np.sin(ph) + .35 * np.sin(2 * ph) + .12 * np.sin(3 * ph)   # harmonics so phones hear it
        return np.tanh(x * 2.2) * .7 * np.minimum(1, t / .005) * np.exp(-t / (L * .6))

    def saw(freq, L, harm=7):
        t = np.arange(int(L * SR)) / SR
        return sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, harm + 1)) * .5

    bpm = 140; beat = 60 / bpm; bar = beat * 4; s16 = beat / 4
    roots = [55.0, 43.65, 49.0, 41.2]                       # A1 F1 G1 E1
    chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [196, 246.9, 293.7], [164.8, 207.7, 246.9]]
    arp = [[440, 523.3, 659.3, 523.3], [349.2, 440, 523.3, 440], [392, 493.9, 587.3, 493.9], [329.6, 415.3, 493.9, 415.3]]
    end_beat = total - 0.7

    # ---- intro (before drop): tension
    add(fx, kick * 1.3, 0.0)
    boom_t = np.arange(int(1.5 * SR)) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 30 * np.exp(-boom_t * 6)) / SR) * np.exp(-boom_t * 2.2) * .9
    add(fx, boom, 0.0, .8)
    add(music, saw(110, DROP_AT, 5) * env(DROP_AT, .02, 3) * .18, 0.0)
    rise_L = DROP_AT
    nz = hp(rng.standard_normal(int(rise_L * SR)), 1500)
    add(fx, nz * np.linspace(0, 1, len(nz)) ** 2 * .2, 0.0)

    # ---- main loop from the drop
    tb = DROP_AT; k = 0
    while tb < end_beat:
        ci = (k // 16) % 4                                   # chord per bar (16 sixteenths)
        step = k % 16
        if step in (0, 10) or (step == 7 and (k // 16) % 2): # trap kick pattern
            add(drums, kick, tb)
            L = min(bar, end_beat - tb + .3)
            g = roots[(ci + 1) % 4] * 2 if step == 10 and ci % 2 else None
            add(music, bass808(roots[ci], max(.2, L * .9), glide_from=g), tb)
            e = 1 - .65 * np.exp(-np.arange(int(.3 * SR)) / SR / .08)
            i = int(tb * SR); duck[i:i + len(e)] = np.minimum(duck[i:i + len(e)], e[: max(0, min(len(e), n - i))])
        if step in (4, 12): add(drums, clap, tb)
        roll = (k // 16) % 2 == 1 and step >= 12
        if step % 2 == 0 or roll:
            add(drums, hat, tb, .9 if step % 4 == 0 else .6)
        if roll and step == 14:                              # triplet flutter
            for r in range(3): add(drums, hat, tb + r * s16 * 2 / 3, .5)
        if step == 14 and not roll: add(drums, ohat, tb)
        if step % 2 == 0:                                    # dark arp (8ths)
            f = arp[ci][(step // 2) % 4]
            add(music, lp(saw(f, s16 * 1.8, 6), 2600) * env(s16 * 1.8, .003, .12) * .55, tb)
        if step == 0:                                        # pad chord per bar
            L = min(bar, end_beat - tb)
            pad = sum(saw(f / 2, L, 4) for f in chords[ci]) * env(L, .08, L) * .11
            add(music, lp(pad, 1500), tb)
        tb += s16; k += 1

    # ---- risers + impacts on every scene cut
    for c in cuts:
        L = 0.9
        r = hp(rng.standard_normal(int(L * SR)), 2000) * np.linspace(0, 1, int(L * SR)) ** 2.5 * .25
        t = np.arange(int(L * SR)) / SR
        r += np.sin(2 * np.pi * np.cumsum(300 + 900 * (t / L) ** 2) / SR) * (t / L) ** 3 * .12
        add(fx, r, c - L)
        add(fx, kick * 1.2, c)
        add(fx, boom * .6, c)
        add(fx, hp(rng.standard_normal(int(.4 * SR)), 3000) * env(.4, .001, .08) * .25, c)   # crash-ish
    # outro ending hit
    add(fx, kick * 1.3, end_beat); add(fx, boom, end_beat, .9)

    mix = drums * .95 + music * duck * .9 + fx * .85
    mix = mix[: int(total * SR)]
    fade = np.minimum(1, (total - np.arange(len(mix)) / SR) / .4)
    mix = np.tanh(mix * 1.15) * fade
    mix = mix / (np.abs(mix).max() + 1e-9) * .89
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- render
def render(ep_path, out_path):
    ep = json.load(open(ep_path, encoding="utf-8"))
    load_item_images(ep)
    validate_episode(ep)                  # fails fast, before minutes of frame rendering
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
            if gt + t < 0.06 or total - (gt + t) < 0.3:
                k = min((gt + t) / 0.06, (total - gt - t) / 0.3)
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
    if sys.argv[1] == "--check":          # validate text layout only, no rendering
        for p in sys.argv[2:]:
            e = json.load(open(p, encoding="utf-8")); load_item_images(e); validate_episode(e)
            print(f"OK  {p}: every text element fits")
        sys.exit(0)
    ep = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "shorts", os.path.basename(ep).replace(".json", ".mp4"))
    print(render(ep, out))
