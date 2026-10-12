import os, math, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
OUT = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(OUT, "frames"); os.makedirs(FR, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG1, BG2 = (14, 10, 28), (52, 12, 60)
ACCENT = (255, 70, 90)
GOLD = (255, 200, 60)
WHITE = (245, 245, 250)
MUTED = (180, 175, 200)

MESSIRI = os.path.join(OUT, "fonts", "ElMessiri.ttf")
_fc = {}
def f(size, bold=True):
    key = (size, bold)
    if key not in _fc:
        fnt = ImageFont.truetype(MESSIRI, size, layout_engine=ImageFont.Layout.RAQM)
        fnt.set_variation_by_axes([700 if bold else 500])
        _fc[key] = fnt
    return _fc[key]

def ease(t):
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3

def background(t):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        k = y / H
        c = tuple(int(BG1[i] * (1 - k) + BG2[i] * k) for i in range(3))
        d.rectangle([0, y, W, y + 4], fill=c)
    # moving diagonal stripes
    off = int(t * 120) % 160
    # glow circles
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    cx = W // 2 + int(200 * math.sin(t * 0.8))
    for r, a in [(520, 18), (380, 22), (240, 26)]:
        od.ellipse([cx - r, 700 - r, cx + r, 700 + r], fill=(ACCENT[0], ACCENT[1], ACCENT[2], a))
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    return img

def header(d):
    # channel bar
    d.rounded_rectangle([60, 90, W - 60, 210], 30, fill=(0, 0, 0, 120))
    d.text((W - 100, 150), "أخبار سكارفيس في دقيقة", font=f(54), fill=WHITE, anchor="rm", direction="rtl")
    d.rounded_rectangle([90, 120, 270, 180], 20, fill=ACCENT)
    d.text((180, 150), "عاجل", font=f(40), fill=WHITE, anchor="mm", direction="rtl")

def wrap(text, font, maxw, draw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if draw.textlength(test, font=font, direction="rtl") <= maxw:
            cur = test
        else:
            lines.append(cur); cur = w_
    if cur: lines.append(cur)
    return lines

def draw_text_block(layer, lines, font, y, fill, alpha, line_h):
    d = ImageDraw.Draw(layer)
    for i, ln in enumerate(lines):
        d.text((W // 2, y + i * line_h), ln, font=font, fill=fill + (alpha,), anchor="mm", direction="rtl")

SCENES = [
    dict(kind="intro", dur=3.0, title="٣ أخبار ألعاب", sub="لازم تعرفها هالأسبوع"),
    dict(kind="news", dur=4.5, tag="الثلاثاء ١٣ أكتوبر", num="١",
         title="يوم مزدحم!", body="Valor Mortis و Planet Zoo 2|ينزلون بنفس اليوم", plat="PS5 • Xbox • PC"),
    dict(kind="news", dur=4.5, tag="الخميس ١٥ أكتوبر", num="٢",
         title="عودة Castlevania", body="جزء جديد باسم|Belmont's Curse", plat="PS5 • Xbox • Switch • PC"),
    dict(kind="news", dur=4.5, tag="١٩ - ٢٦ أكتوبر", num="٣",
         title="Steam Next Fest", body="أسبوع كامل من الديموهات المجانية|جربها قبل تشتري", plat="PC"),
    dict(kind="outro", dur=3.5, title="أي لعبة بتجرب؟", sub="اكتبها بالتعليقات", cta="اشترك عشان توصلك الأخبار أول بأول"),
]

def render_scene(sc, t, gt):
    img = background(gt)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    header(d)
    p = ease(t / 0.6)
    a = int(255 * p)
    dy = int((1 - p) * 80)
    # progress bar
    total = sum(s["dur"] for s in SCENES)
    d.rectangle([0, H - 14, int(W * gt / total), H], fill=ACCENT + (255,))

    if sc["kind"] == "intro":
        s = 0.7 + 0.3 * ease(t / 0.5)
        fnt = f(int(130 * s))
        d.text((W // 2, 820 + dy), sc["title"], font=fnt, fill=GOLD + (a,), anchor="mm", direction="rtl")
        p2 = ease((t - 0.5) / 0.6)
        d.text((W // 2, 1000), sc["sub"], font=f(70), fill=WHITE + (int(255 * p2),), anchor="mm", direction="rtl")
    elif sc["kind"] == "news":
        # card
        cy = 560 + dy
        d.rounded_rectangle([70, cy, W - 70, cy + 900], 50, fill=(20, 16, 40, int(220 * p)), outline=ACCENT + (a,), width=6)
        # number badge
        d.ellipse([W // 2 - 90, cy - 90, W // 2 + 90, cy + 90], fill=ACCENT + (a,))
        d.text((W // 2, cy), sc["num"], font=f(110), fill=WHITE + (a,), anchor="mm")
        # date tag
        p2 = ease((t - 0.3) / 0.5)
        d.rounded_rectangle([W // 2 - 270, cy + 140, W // 2 + 270, cy + 230], 45, fill=GOLD + (int(255 * p2),))
        d.text((W // 2, cy + 185), sc["tag"], font=f(50), fill=(30, 20, 40, int(255 * p2)), anchor="mm", direction="rtl")
        # title
        p3 = ease((t - 0.6) / 0.5)
        d.text((W // 2, cy + 340), sc["title"], font=f(92), fill=WHITE + (int(255 * p3),), anchor="mm", direction="rtl")
        # body
        p4 = ease((t - 1.0) / 0.6)
        lines = sc["body"].split("|")
        draw_text_block(layer, lines, f(60, False), cy + 490, MUTED, int(255 * p4), 90)
        # platforms
        p5 = ease((t - 1.6) / 0.5)
        d.text((W // 2, cy + 800), sc["plat"], font=f(48), fill=GOLD + (int(255 * p5),), anchor="mm")
    else:
        pulse = 1 + 0.05 * math.sin(t * 6)
        d.text((W // 2, 760 + dy), sc["title"], font=f(int(100 * pulse)), fill=GOLD + (a,), anchor="mm", direction="rtl")
        p2 = ease((t - 0.4) / 0.5)
        d.text((W // 2, 930), sc["sub"], font=f(72), fill=WHITE + (int(255 * p2),), anchor="mm", direction="rtl")
        p3 = ease((t - 0.9) / 0.5)
        d.rounded_rectangle([110, 1150, W - 110, 1290], 70, fill=ACCENT + (int(255 * p3),))
        d.text((W // 2, 1220), sc["cta"], font=f(48), fill=WHITE + (int(255 * p3),), anchor="mm", direction="rtl")
        d.text((W // 2, 1400), "@Scarfce001", font=f(56), fill=MUTED + (int(255 * p3),), anchor="mm")

    # fade out last 0.3s of scene
    out = Image.alpha_composite(img, layer).convert("RGB")
    rem = sc["dur"] - t
    if rem < 0.25:
        k = rem / 0.25
        out = Image.blend(Image.new("RGB", (W, H), BG1), out, max(0, k))
    return out

n = 0
gt = 0.0
for sc in SCENES:
    frames = int(sc["dur"] * FPS)
    for i in range(frames):
        t = i / FPS
        render_scene(sc, t, gt + t).save(os.path.join(FR, f"{n:05d}.jpg"), quality=90)
        n += 1
    gt += sc["dur"]

dst = os.path.join(OUT, "scar_news_sample.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(FR, "%05d.jpg"),
                "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
                "-filter_complex", "[1:a]volume=0.0[a]", "-map", "0:v", "-map", "[a]", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", dst], check=True)
print(dst, n)
