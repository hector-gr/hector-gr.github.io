"""ReImaGin explainer — 1920x1080 (16:9), light editorial, Twitter-legible type.
Pipes frames straight to ffmpeg."""
import math, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

W, H = 1920, 1080
FPS, DUR = 30, 157.0
M = 120
MEDIA = "pptx/ppt/media/"
OUT = "reimagin_explainer_v2.mp4"

# ── palette: Cream & Claret (light) ───────────────────────────────────────────
BG    = (244, 239, 229)   # warm cream ground
SURF  = (235, 228, 214)   # deeper cream panel
INK   = (40, 30, 30)      # dark warm — primary text
MUTED = (120, 102, 92)    # secondary text
FAINT = (220, 211, 196)   # hairlines / card edges
TERRA = (140, 36, 58)     # claret — primary accent
RED   = (188, 52, 52)     # vivid brick — on-image rings / markers
GOLD  = (166, 126, 50)    # brass — generated labels / arrows
GREEN = (86, 104, 66)     # olive — success

# ── fonts: Iowan Old Style (display/body/caps) · Andale Mono (code) ────────────
IOW = "/System/Library/Fonts/Supplemental/Iowan Old Style.ttc"
AND = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"
_fc = {}
def F(kind, size):
    k = (kind, size)
    if k not in _fc:
        spec = {"display": (IOW, 4), "serif": (IOW, 0), "italic": (IOW, 2),
                "black": (IOW, 4), "caps": (IOW, 1), "capsb": (IOW, 1),
                "mono": (AND, 0), "monob": (AND, 0)}[kind]
        _fc[k] = ImageFont.truetype(spec[0], size, index=spec[1])
    return _fc[k]

# ── easing ────────────────────────────────────────────────────────────────────
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, s, d): return clamp((t - s) / d) if d > 0 else (1.0 if t >= s else 0.0)
def eo(x): return 1 - (1 - x) ** 3
def eo5(x): return 1 - (1 - x) ** 5
def eio(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def lerp(a, b, x): return a + (b - a) * x
def mix(c1, c2, x): return tuple(int(round(lerp(a, b, clamp(x)))) for a, b in zip(c1, c2))
def fade(t, s, d_in, hold=999, d_out=.45):
    if t < s: return 0.0
    a = prog(t, s, d_in)
    if t > s + d_in + hold: a *= 1 - prog(t, s + d_in + hold, d_out)
    return clamp(a)

# ── images (fully static: nothing recomputed per frame, so no jitter) ─────────
_raw, _fit = {}, {}
def raw(n):
    if n not in _raw: _raw[n] = Image.open(MEDIA + n).convert("RGB")
    return _raw[n]
def grade(im):
    im = ImageEnhance.Color(im).enhance(.94)
    return ImageEnhance.Contrast(im).enhance(1.02)
def fitted(n, w, h):
    k = (n, w, h)
    if k not in _fit:
        p = n if n.startswith("/") or "/" in n else MEDIA + n
        im = Image.open(p).convert("RGB")
        sc = max(w / im.width, h / im.height)
        im = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))),
                       Image.Resampling.LANCZOS)
        L, T = (im.width - w) // 2, (im.height - h) // 2
        _fit[k] = grade(im.crop((L, T, L + w, T + h)))
    return _fit[k]
_mk = {}
def rmask(w, h, r):
    k = (w, h, r)
    if k not in _mk:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
        _mk[k] = m
    return _mk[k]
def card(base, name, cx, cy, w, h, alpha=1.0, r=4, edge=FAINT, hi=False):
    if alpha <= .01: return
    w, h, cx, cy = int(w), int(h), int(cx), int(cy)
    m = rmask(w, h, r)
    if alpha < .999: m = m.point(lambda p: int(p * alpha))
    base.paste(fitted(name, w, h), (cx - w // 2, cy - h // 2), m)
    ec, ew = (mix(BG, GOLD, .85), 3) if hi else (edge, 1)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                         outline=ec + (int(255 * alpha),), width=ew)
    base.paste(ov, (cx - w // 2, cy - h // 2), ov)

_cont = {}
def img_contain(base, name, cx, cy, boxw, boxh, alpha=1.0):
    """Paste an image scaled to FIT inside the box (no cropping); supports alpha + RGBA."""
    if alpha <= .01: return
    key = (name, boxw, boxh)
    if key not in _cont:
        p = name if "/" in name else MEDIA + name
        im = Image.open(p)
        im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
        sc = min(boxw / im.width, boxh / im.height)
        im = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))),
                       Image.Resampling.LANCZOS)
        _cont[key] = im
    im = _cont[key]
    x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    if im.mode == "RGBA":
        m = im.split()[3]
        if alpha < .999: m = m.point(lambda q: int(q * alpha))
        base.paste(im, (x, y), m)
    elif alpha < .999:
        base.paste(im, (x, y), Image.new("L", im.size, int(255 * alpha)))
    else:
        base.paste(im, (x, y))
    return im.width, im.height

def surface(base, x0, y0, x1, y1, alpha, fill=SURF, edge=FAINT, r=6):
    if alpha <= .01: return
    w, h = int(x1 - x0), int(y1 - y0)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    a = int(255 * alpha)
    ImageDraw.Draw(ov).rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                         fill=fill + (a,), outline=edge + (a,), width=1)
    base.paste(ov, (int(x0), int(y0)), ov)

def rule(d, x0, x1, y, alpha, color=FAINT, w=1):
    if alpha > .01: d.line([(x0, y), (x1, y)], fill=mix(BG, color, alpha), width=w)
def rule_grow(d, x0, x1, y, p, color=FAINT, w=1):
    if p > .01: d.line([(x0, y), (x0 + (x1 - x0) * eo(clamp(p)), y)], fill=color, width=w)

# ── type: single code path so a finished reveal never shifts ──────────────────
def _place(s, font, x, y, anchor):
    asc, desc = font.getmetrics(); th = asc + desc; tw = font.getlength(s)
    ox = x if anchor[0] == "l" else (x - tw / 2 if anchor[0] == "m" else x - tw)
    return int(ox), int(y - th / 2), int(tw), th
_var = {}
def _big(font, S):                       # cached supersampled variant (same face/index)
    k = (id(font), S)
    if k not in _var: _var[k] = font.font_variant(size=font.size * S)
    return _var[k]
def rtext(base, s, font, x, y, color, p=1.0, anchor="lm"):
    # Reveal = gentle float-up + fade, rendered 3x and downscaled so the motion is
    # sub-pixel smooth; the p>=1 path draws direct and lands on the identical pixels.
    if p <= .002 or not s: return
    p = clamp(p); ox, oy, tw, th = _place(s, font, x, y, anchor)
    if p >= .999:
        ImageDraw.Draw(base).text((ox, oy), s, font=font, fill=color, anchor="la"); return
    e = eo(p)
    a = int(255 * clamp(p * 1.5))
    rise = (1 - e) * th * 0.32
    S = 3; pad = max(4, int(th * 0.55))
    lay = Image.new("RGBA", ((tw + 12) * S, (th + pad * 2) * S), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((6 * S, (pad + rise) * S), s, font=_big(font, S),
                             fill=color + (a,), anchor="la")
    lay = lay.resize((tw + 12, th + pad * 2), Image.Resampling.LANCZOS)
    base.paste(lay, (ox - 6, oy - pad), lay)
def wrap(s, font, maxw):
    out, cur = [], ""
    for wd in s.split():
        t = (cur + " " + wd).strip()
        if font.getlength(t) <= maxw or not cur: cur = t
        else: out.append(cur); cur = wd
    if cur: out.append(cur)
    return out
def rblock(base, s, font, x, y, color, p=1.0, maxw=880, lh=None, anchor="lm", stagger=.13):
    lines = wrap(s, font, maxw); lh = lh or int(font.size * 1.3); n = max(1, len(lines))
    for i, ln in enumerate(lines):
        lp = clamp((p - i * stagger) / max(.001, 1 - stagger * (n - 1)))
        rtext(base, ln, font, x, y + i * lh, color, lp, anchor)
    return y + n * lh
def tracked(base, s, font, x, y, color, alpha=1.0, tr=5, anchor="lm"):
    if alpha <= .01 or not s: return
    wid = sum(font.getlength(c) + tr for c in s) - tr
    asc, desc = font.getmetrics(); th = asc + desc
    lay = Image.new("RGBA", (int(wid) + 8, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay); cx = 0
    for c in s:
        d.text((cx, 0), c, font=font, fill=color + (int(255 * clamp(alpha)),), anchor="la")
        cx += font.getlength(c) + tr
    ox = x if anchor[0] == "l" else (x - wid / 2 if anchor[0] == "m" else x - wid)
    base.paste(lay, (int(ox), int(y - th / 2)), lay)

# ── primitives ────────────────────────────────────────────────────────────────
def ring(base, cx, cy, rad, color, alpha=1.0, width=4):
    if alpha <= .01: return
    rad = int(rad)
    ov = Image.new("RGBA", (rad * 2 + 24, rad * 2 + 24), (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse([12, 12, 12 + rad * 2, 12 + rad * 2],
                               outline=color + (int(255 * clamp(alpha)),), width=width)
    base.paste(ov, (int(cx - rad - 12), int(cy - rad - 12)), ov)
def arrow_down(d, cx, y0, y1, color, p=1.0, w=3, head=15):
    if p <= .01: return
    ye = y0 + (y1 - y0) * eo(clamp(p))
    d.line([(cx, y0), (cx, ye)], fill=color, width=w)
    if p >= .98:
        d.polygon([(cx - head, y1 - head * 1.2), (cx + head, y1 - head * 1.2), (cx, y1)], fill=color)
def arrow_right(d, x0, x1, cy, color, p=1.0, w=3, head=15):
    if p <= .01: return
    xe = x0 + (x1 - x0) * eo(clamp(p))
    d.line([(x0, cy), (xe, cy)], fill=color, width=w)
    if p >= .98:
        d.polygon([(x1 - head * 1.25, cy - head), (x1 - head * 1.25, cy + head), (x1, cy)], fill=color)
def check(d, cx, cy, s, color, width=6, p=1.0):
    a = (cx - s, cy + s * .06); b = (cx - s * .3, cy + s * .7); c = (cx + s, cy - s * .72)
    if p < .5:
        q = p / .5
        d.line([a, (lerp(a[0], b[0], q), lerp(a[1], b[1], q))], fill=color, width=width)
    else:
        q = (p - .5) / .5
        d.line([a, b], fill=color, width=width)
        d.line([b, (lerp(b[0], c[0], q), lerp(b[1], c[1], q))], fill=color, width=width)
def typeon(s, t, s0, cps=34.0):
    n = int(max(0, t - s0) * cps); return s[:n], n >= len(s)
def caret(t): return (t * 2) % 2 < 1.15

def _typed_lines(code, f, maxw, nchars):
    full = wrap(code, f, maxw); out, used = [], 0
    for ln in full:
        if used >= nchars: break
        out.append(ln[:max(0, nchars - used)]); used += len(ln) + 1
    return out, len(full)
def code_panel(base, t, y, items, alpha, maxw=1580, size=26, x0=M, x1=W - M):
    if alpha <= .01: return y
    f = F("mono", size)
    total = sum(len(wrap(c, f, maxw)) for c, _ in items)
    lh = size + 12
    bot = y + 20 + total * lh
    surface(base, x0, y, x1, bot, alpha)
    yy = y + 16
    for code, t0 in items:
        shown, nl = _typed_lines(code, f, maxw, int(max(0, t - t0) * 55))
        for i, ln in enumerate(shown):
            ImageDraw.Draw(base).text((x0 + 26, yy + i * lh), ln, font=f,
                                      fill=mix(SURF, INK, alpha), anchor="la")
        yy += nl * lh
    return bot

def chip(base, d, cx, cy, label, font, alpha, fillc=None, txtc=INK, edge=INK, pad=30, mono=False):
    w = font.getlength(label) + pad * 2; h = font.size + 34
    if alpha <= .01:
        return cx - w / 2, cx + w / 2
    x0, y0 = cx - w / 2, cy - h / 2
    a = int(255 * clamp(alpha))
    ov = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    dd = ImageDraw.Draw(ov)
    dd.rounded_rectangle([1, 1, int(w) - 2, int(h) - 2], radius=12,
                         fill=(fillc + (a,)) if fillc else None,
                         outline=edge + (a,), width=2)
    dd.text((w / 2, h / 2), label, font=font, fill=txtc + (a,), anchor="mm")
    base.paste(ov, (int(x0), int(y0)), ov)
    return x0, x0 + w

def arrowhead(d, x, y, ang, color, size=13):
    tip = (x + math.cos(ang) * size, y + math.sin(ang) * size)
    l = (x + math.cos(ang + 2.5) * size, y + math.sin(ang + 2.5) * size)
    r = (x + math.cos(ang - 2.5) * size, y + math.sin(ang - 2.5) * size)
    d.polygon([tip, l, r], fill=color)

BASE_BG = Image.new("RGB", (W, H), BG)

# ── measured landmarks ────────────────────────────────────────────────────────
TOWEL_A  = (0.79, 0.35); DETER_B  = (0.43, 0.42)
DETER_BP = (0.425, 0.415); TOWEL_BP = (0.900, 0.550)
QUESTION = ("“When I am using the pink towel, where is the green "
            "laundry detergent located relative to me?”")
PW, PH = 435, 325
PXL, PXR, PYC = 1117, 1583, 540

CHAPTERS = [(0, 15.4, "I.  THE QUESTION"), (15.4, 24, "II.  THE LIMITATION"),
            (24, 43, "III.  REASONING WITH TOOLS"), (43, 53, "IV.  THE KEY INSIGHT"),
            (53, 86, "V.  REIMAGIN"), (86, 121.4, "VI.  MANY TASKS"),
            (121.4, 139, "VII.  STRATEGY DISCOVERY"), (139, 151, "VIII.  RESULTS"),
            (151, 157, "")]
TITLES = [(14, 15.4, "II.", "The Limitation"),
          (24, 25.4, "III.", "Reasoning with Tools"),
          (43, 44.4, "IV.", "The Key Insight"), (53, 54.4, "V.", "ReImaGin"),
          (86, 87.4, "VI.", "Many Tasks"),
          (121.4, 122.8, "VII.", "Strategy Discovery"),
          (139, 140.4, "VIII.", "Results")]
def in_title(t): return any(s <= t < e for s, e, *_ in TITLES)

# ── pacing: freeze the timeline briefly at the end of each slide (≈2–3s dwell) ──
#   Each (t_in, dwell) holds the last, fully-revealed frame of a beat for `dwell`
#   seconds, so every slide gets a consistent pause before it cuts. Scene internals
#   are untouched; only wall-clock is stretched. Freeze points sit inside a static
#   window (after the last reveal, before any fade-out).
HOLDS = sorted([
    (13.8, 0.7), (23.5, 0.4), (42.5, 0.6), (52.5, 0.8),   # hook · limit · menu · shift
    (85.5, 1.0), (120.8, 1.0),                            # reimagin answer · many-tasks payoff
    (127.3, 1.2), (134.0, 1.1), (138.6, 2.3),             # discovery: setup · loop · collision
    (14.9, 1.1), (24.9, 1.1), (43.9, 1.1), (53.9, 1.8),   # title cards (V held longest)
    (86.9, 1.1), (122.3, 1.1), (139.9, 1.1),
])
EXTRA = sum(d for _, d in HOLDS)
NEWDUR = DUR + EXTRA
def warp(to):
    ti = to
    for pt, d in HOLDS:
        if ti <= pt: return ti
        if ti <= pt + d: return pt
        ti -= d
    return ti

def chrome(base, d, t, tout):
    a = fade(t, .4, .8)
    if t >= 151: a *= 1 - prog(t, 151, .5)
    if in_title(t): a = 0
    if a > .01:
        tracked(base, "REIMAGIN", F("caps", 24), M, 78, mix(BG, INK, .8), a, tr=6)
        lab = next((c for s, e, c in CHAPTERS if s <= t < e), "")
        tracked(base, lab, F("caps", 24), W - M, 78, MUTED, a * .9, tr=6, anchor="r")
        rule(d, M, W - M, 118, a * .8)
        rule(d, M, W - M, H - 90, a * .8)
    d.rectangle([0, H - 4, int(W * tout / NEWDUR), H - 1], fill=mix(BG, TERRA, .85))

def title_card(base, d, t):
    for s, e, num, name in TITLES:
        if not (s <= t < e): continue
        p = prog(t, s + .06, .5); out = 1 - prog(t, e - .25, .25)
        tracked(base, num, F("caps", 30), W // 2, 448, TERRA, p * out, tr=9, anchor="m")
        rtext(base, name, F("display", 92), W // 2, 548, INK, p, anchor="mm")
        rule_grow(d, W // 2 - 130, W // 2 + 130, 628, prog(t, s + .3, .45), FAINT)
        if name == "ReImaGin":
            tracked(base, "REASONING WITH IMAGE GENERATION", F("caps", 34), W // 2, 698,
                    MUTED, prog(t, s + .35, .4) * out, tr=6, anchor="m")
        return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
def s_hook(base, d, t):                                          # 0 – 14
    rblock(base, QUESTION, F("display", 56), M, 300, INK, prog(t, .5, 1.7),
           maxw=760, lh=76, stagger=.17)
    pin = eo5(prog(t, 1.3, 1.1))
    card(base, "image25.png", int(lerp(W + 340, PXL, pin)), PYC, PW, PH)
    card(base, "image26.png", int(lerp(W + 900, PXR, pin)), PYC, PW, PH)
    for (nx, ny), lab, lx, s0 in ((TOWEL_A, "PINK TOWEL", PXL, 6.4),
                                  (DETER_B, "GREEN DETERGENT", PXR, 6.9)):
        a = fade(t, s0, .5)
        if a <= .01: continue
        ring(base, (lx - PW // 2) + nx * PW, (PYC - PH // 2) + ny * PH, 30, RED, a, 5)
        tracked(base, lab, F("caps", 26), lx, 312, RED, a, tr=5.5, anchor="m")
    rtext(base, "Try it.", F("italic", 60), M, 690, GOLD,
          prog(t, 3.9, .7) * (1 - prog(t, 8.3, .35)))
    rtext(base, "Neither photo shows both.", F("display", 60), M, 812, INK,
          prog(t, 8.6, .8) * (1 - prog(t, 10.9, .35)))
    rblock(base, "To answer, humans build a mental map of the scene.", F("display", 56), M, 782,
           INK, prog(t, 11.2, 1.0), maxw=900, lh=72)
    rtext(base, "But text-only reasoning cannot build one.", F("display", 54), M, 926, TERRA,
          prog(t, 13.4, .9))

def s_limit(base, d, t):                                         # 15.4 – 24
    card(base, "image25.png", 1300, 300, 340, 254)
    card(base, "image26.png", 1650, 300, 340, 254)
    tracked(base, "THE MODEL REASONS IN TEXT", F("caps", 24), M, 250, MUTED,
            fade(t, 15.8, .5), tr=5)
    lines = [("Image 1 has a sink, a mirror, and a pink towel.", MUTED),
             ("Image 2 has a shower, a vanity, and a green bottle.", MUTED),
             ("The towel and the bottle never appear in the same image,", MUTED),
             ("so I cannot tell where one is relative to the other.", TERRA)]
    f = F("mono", 27)
    for i, (ln, col) in enumerate(lines):
        rtext(base, ln, f, M, 344 + i * 52, col, prog(t, 16.0 + i * .55, .45))
    rblock(base, "The question needs a single spatial map of the scene.", F("display", 52),
           M, 648, INK, prog(t, 19.6, .9), maxw=1090, lh=64)
    rtext(base, "Text-only reasoning cannot build one.", F("display", 52), M, 800, TERRA,
          prog(t, 21.0, .9))

def s_prior(base, d, t):                                         # 25.4 – 34
    rblock(base, "Prior work goes beyond text-only reasoning", F("display", 54), M, 250, INK,
           prog(t, 25.6, .9), maxw=780, lh=66)
    rblock(base, "by adding specialist vision tools to the model.", F("serif", 40), M, 430,
           MUTED, prog(t, 26.6, .9), maxw=780, lh=52)
    for i, tool in enumerate(["depth estimation", "segmentation", "object detection"]):
        rtext(base, "·  " + tool, F("serif", 38), M, 600 + i * 62, GOLD,
              prog(t, 29.6 + i * .62, .5))
    # attribution sits with the image
    ax = 1360
    tracked(base, "VISUAL SKETCHPAD  ·  HU ET AL.  ·  NEURIPS 2024", F("caps", 22), ax, 232,
            MUTED, fade(t, 27.6, .5), tr=3.5, anchor="m")
    img_contain(base, "priorwork.png", ax, 630, 880, 600, fade(t, 27.9, .7))

MENU = ["segment()", "detect_objects()", "estimate_depth()", "crop()", "overlay()"]
ROW0, RGAP = 300, 74
def s_menu(base, d, t):                                          # 34 – 43
    tracked(base, "SPECIALIST TOOLS", F("caps", 28), M, 236, MUTED, fade(t, 34.1, .45), tr=6)
    rule_grow(d, M, 820, 272, prog(t, 34.25, .6))
    f = F("mono", 30)
    for i, m in enumerate(MENU):
        y = ROW0 + i * RGAP
        rtext(base, m, f, M + 8, y, mix(INK, MUTED, .2), prog(t, 34.6 + i * .3, .45))
        rule_grow(d, M, 820, y + 36, prog(t, 34.7 + i * .3, .5))
    y6 = ROW0 + 5 * RGAP + 16
    if t >= 36.4:
        typed, done = typeon("top_down_view()", t, 36.5, 22)
        a = fade(t, 36.4, .3)
        ImageDraw.Draw(base).text((M + 8, y6), typed, font=f, fill=mix(BG, GOLD, a), anchor="lm")
        if not done and caret(t):
            cx = M + 8 + f.getlength(typed)
            d.rectangle([cx + 3, y6 - 16, cx + 15, y6 + 16], fill=mix(BG, GOLD, .85))
    sp = prog(t, 38.0, .45)
    if sp > 0:
        x1 = M + 8 + f.getlength("top_down_view()")
        d.line([(M, y6), (lerp(M, x1 + 8, eo(sp)), y6)], fill=TERRA, width=4)
        tracked(base, "NO SUCH TOOL", F("caps", 24), M + 8, y6 + 52, TERRA,
                fade(t, 38.45, .35), tr=5)
    rtext(base, "Tools are rigid.", F("display", 60), 1000, 432, INK, prog(t, 39.2, .7))
    rblock(base, "The transformation a task needs often has no tool at all.",
           F("display", 46), 1000, 516, INK, prog(t, 40.2, .9), maxw=820, lh=62)

def s_shift(base, d, t):                                         # 44.4 – 53
    rblock(base, "Generative models change what a visual tool can be.", F("display", 56), M, 250,
           INK, prog(t, 44.6, .9), maxw=1680, lh=70)
    rblock(base, "Instruction-following image generators can perform any operation "
                 "that can be expressed in natural language.",
           F("serif", 40), M, 402, MUTED, prog(t, 45.7, 1.0), maxw=1600, lh=54)
    fa = fade(t, 47.4, .55)
    if fa > .01:
        done_t, fm = 49.3, F("mono", 34)
        tracked(base, "ONE INSTRUCTION", F("caps", 26), M, 604, MUTED, fa, tr=5.5)
        typed, done = typeon("show me this room from above", t, 47.7, 24)
        ImageDraw.Draw(base).text((M + 4, 680), typed, font=fm, fill=mix(BG, INK, fa), anchor="lm")
        if not done and caret(t):
            cx = M + 4 + fm.getlength(typed)
            d.rectangle([cx + 3, 680 - 19, cx + 17, 680 + 19], fill=mix(BG, GOLD, .9))
        col = GREEN if t >= done_t else GOLD
        d.line([(M, 724), (1200, 724)], fill=mix(BG, col, fa * .9), width=2)
        if t >= done_t: check(d, 1244, 680, 19, GREEN, 6, prog(t, done_t, .35))
    rtext(base, "The set of operations is open-ended,", F("display", 52), M, 876, INK,
          prog(t, 49.9, .8))
    rtext(base, "bounded only by natural language.", F("display", 52), M, 950, TERRA,
          prog(t, 50.5, .8))

# ── V. ReImaGin: definition beat, then the worked example ─────────────────────
def dlg_text(base, d, t, num, thought, code, t_th, t_ac):
    tracked(base, f"THOUGHT {num}", F("caps", 26), M, 452, TERRA, fade(t, t_th, .4), tr=5)
    rblock(base, thought, F("italic", 40), M, 516, INK, prog(t, t_th + .15, .9),
           maxw=740, lh=52)
    tracked(base, f"ACTION {num}", F("caps", 26), M, 690, TERRA, fade(t, t_ac, .4), tr=5)
    code_panel(base, t, 730, [(code, t_ac + .2)], fade(t, t_ac, .4), maxw=700, size=26,
               x0=M, x1=900)

def gen_arrow_v(base, d, t, cx, y0, y1, t0, a=1.0):
    arrow_down(d, cx, y0, y1, mix(BG, GOLD, .9 * a), prog(t, t0, .45))
    ImageDraw.Draw(base).text((cx + 26, (y0 + y1) / 2), "generate_image",
                              font=F("mono", 24), fill=mix(BG, GOLD, fade(t, t0 + .2, .4) * a),
                              anchor="lm")

def s_reimagin(base, d, t):                                      # 54.4 – 86
    if t < 62.5:                                                 # definition
        rblock(base, "We propose ReImaGin, a method that reasons by generating images.",
               F("display", 60), W // 2, 288, INK, prog(t, 54.6, 1.0), maxw=1600, lh=78,
               anchor="mm")
        rblock(base, "At any step, the agent can call generate_image with a natural-language "
                     "prompt, then reason over the result.", F("serif", 40), W // 2, 448,
               MUTED, prog(t, 55.9, 1.0), maxw=1400, lh=54, anchor="ma")
        cy = 700
        ea = fade(t, 57.2, .7)
        chips = [("Reason", F("display", 40), None, INK, INK, False),
                 ("generate_image", F("mono", 34), GOLD, BG, GOLD, True),
                 ("Observe", F("display", 40), None, INK, INK, False),
                 ("Answer", F("display", 40), None, GREEN, GREEN, True)]
        centers = [430, 830, 1220, 1560]
        edges = []
        for idx, ((lab, fn, fill, tx, eg, _), cx) in enumerate(zip(chips, centers)):
            ap = fade(t, 57.2 + idx * .25, .5) if idx < 3 else fade(t, 60.5, .5)
            edges.append(chip(base, d, cx, cy, lab, fn, ap, fill, tx, eg))
        for i in range(2):                       # Reason → generate_image → Observe
            ar = prog(t, 57.7 + i * .3, .4)
            arrow_right(d, edges[i][1] + 16, edges[i + 1][0] - 16, cy,
                        mix(BG, MUTED, .85 * ea), ar)
        # loop-back arc Observe -> Reason
        lp = prog(t, 59.4, .6)
        if lp > 0:
            ytop = cy - 92; col = mix(BG, GOLD, .85 * ea)
            ox, rx = centers[2], centers[0]
            xe = lerp(ox, rx, eo(lp))
            d.line([(ox, cy - 40), (ox, ytop)], fill=col, width=3)
            d.line([(ox, ytop), (xe, ytop)], fill=col, width=3)
            if lp >= 1:
                d.line([(rx, ytop), (rx, cy - 40)], fill=col, width=3)
                d.polygon([(rx - 12, cy - 56), (rx + 12, cy - 56), (rx, cy - 38)], fill=col)
                tracked(base, "REPEAT UNTIL SOLVED", F("caps", 22), (ox + rx) / 2, ytop - 26,
                        GOLD, fade(t, 60.1, .4), tr=4.5, anchor="m")
        # the arrow into Answer is drawn last, once the loop has converged
        arrow_right(d, edges[2][1] + 16, edges[3][0] - 16, cy, mix(BG, MUTED, .85 * ea),
                    prog(t, 60.7, .45))
        rtext(base, "How it answers the question:", F("italic", 40), W // 2, 940, MUTED,
              prog(t, 61.2, .7) * (1 - prog(t, 62.2, .3)), anchor="mm")
    elif t < 70.5:                                               # turn 1
        rblock(base, QUESTION, F("serif", 37), M, 166, INK, fade(t, 62.6, .6),
               maxw=1680, lh=47)
        dlg_text(base, d, t, 1, "First, I will create a unified view of the scene.",
                 'unified = generate_image("combine the two images into a '
                 'unified view", image_1, image_2)', 63.2, 64.5)
        a = fade(t, 62.8, .6)
        tracked(base, "INPUT", F("caps", 26), 1360, 288, MUTED, a, tr=5, anchor="m")
        card(base, "image25.png", 1197, 432, 306, 229, a)
        card(base, "image26.png", 1523, 432, 306, 229, a)
        gen_arrow_v(base, d, t, 1360, 552, 602, 66.4)
        ga = fade(t, 67.1, .7)
        tracked(base, "GENERATED", F("caps", 26), 1360, 634, GOLD, ga, tr=5.5, anchor="m")
        card(base, "image29.png", 1360, 829, 428, 320, ga, hi=True)
    elif t < 78.5:                                               # turn 2
        dlg_text(base, d, t, 2, "A top-down map will make the relative positions clear.",
                 'top_down = generate_image("create a top-down map of this scene", unified)',
                 70.9, 72.2)
        a = fade(t, 70.5, .5)
        tracked(base, "UNIFIED VIEW", F("caps", 26), 1360, 210, MUTED, a, tr=5, anchor="m")
        card(base, "image29.png", 1360, 372, 340, 254, a)
        gen_arrow_v(base, d, t, 1360, 512, 566, 74.1)
        ga = fade(t, 74.7, .7)
        tracked(base, "GENERATED", F("caps", 26), 1360, 612, GOLD, ga, tr=5.5, anchor="m")
        card(base, "image27.png", 1360, 826, 520, 388, ga, hi=True)
    else:                                                        # the answer
        a = fade(t, 78.7, .5)
        bw, bh, bcx, bcy = 720, 537, 540, 580
        card(base, "image27.png", bcx, bcy, bw, bh, a, hi=True)
        X0, Y0 = bcx - bw // 2, bcy - bh // 2
        for (nx, ny), s0 in ((DETER_BP, 79.5), (TOWEL_BP, 79.9)):
            ring(base, X0 + nx * bw, Y0 + ny * bh, 32, RED, fade(t, s0, .45), 5)
        tracked(base, "THOUGHT 3", F("caps", 26), 1010, 322, TERRA, fade(t, 80.6, .4), tr=5)
        rblock(base, "If I am facing the towel, I am facing the right wall. "
                     "From there, the detergent is to my back left.", F("italic", 40), 1010,
               392, INK, prog(t, 80.8, 1.1), maxw=790, lh=52)
        tracked(base, "ANSWER", F("caps", 26), 1010, 600, TERRA, fade(t, 83.2, .4), tr=5)
        rtext(base, "Back Left", F("display", 76), 1010, 682, GREEN, prog(t, 83.4, .8))
        if t >= 84.1:
            check(d, 1010 + F("display", 76).getlength("Back Left") + 56, 682, 24, GREEN, 7,
                  prog(t, 84.1, .4))

# ── VI. Many tasks ────────────────────────────────────────────────────────────
MONT = [
    dict(dur=7.0, label="COLLISION PREDICTION", q="If the minivan moves forward, what will it hit?",
         th="I will trace the direction the minivan is heading.",
         code='generate_image("add a straight line through the minivan, along the '
              'direction it faces", image_1)',
         src="image8.png", out="image16.png", cw=480, ch=360),
    dict(dur=7.0, label="OCCLUSION COUNTING", q="How many oranges are there, including hidden ones?",
         th="I will reveal what the black box hides.",
         code='generate_image("remove the black box and fill in the missing '
              'oranges from the surrounding pattern", image_1)',
         src="image10.png", out="image23.png", cw=520, ch=325),
    dict(dur=9.0, label="PUZZLE COMPLETION", q="Which piece fits perfectly in the hole?",
         th="I will fill the gap, then subtract to isolate the piece.",
         code='filled = generate_image("remove the white space to reveal the pattern", image_1)',
         code2='piece  = subtract_images(filled, image_1)',
         src="image5.png", out="image15.png", sub="image21.png", cw=430, ch=202),
    dict(dur=7.5, label="PATH TRACING", q="Which letter connects to each number?",
         th="Dashed lines are hard to follow, so I will make them solid.",
         code='generate_image("convert the dashed lines into solid lines, keep the '
              'layout unchanged", image_1)',
         src="image18.png", out="image17.png", cw=442, ch=360),
]
MSTART = 87.4
BOUNDS, _acc = [], MSTART
for _m in MONT:
    BOUNDS.append((_acc, _acc + _m["dur"])); _acc += _m["dur"]
TASKS_END = _acc                                                 # 117.9

def s_montage(base, d, t):                                       # 87.4 – 121.4
    if t >= TASKS_END:                                           # implication beat
        rtext(base, "One model. Many operations.", F("display", 56), W // 2, 468, INK,
              prog(t, TASKS_END + .2, .8), anchor="mm")
        rblock(base, "No new tool is engineered per task; the range grows as image "
                     "generators improve.", F("serif", 40), W // 2, 566, MUTED,
               prog(t, TASKS_END + 1.0, 1.0), maxw=1300, lh=54, anchor="ma")
        return
    i = next((k for k, (s, e) in enumerate(BOUNDS) if s <= t < e), 3)
    s0, e0 = BOUNDS[i]; m = MONT[i]
    a = prog(t, s0 + .05, .4) * (1 - prog(t, e0 - .4, .4))
    tracked(base, m["label"], F("caps", 28), M, 196, MUTED, a, tr=6)
    rule(d, M, W - M, 232, a * .7)
    rblock(base, m["q"], F("serif", 37), M, 288, MUTED, prog(t, s0 + .25, .6) * a,
           maxw=1500, lh=46)
    rblock(base, m["th"], F("italic", 39), M, 356, INK, prog(t, s0 + .7, .8) * a,
           maxw=1500, lh=48)
    cw, ch = m["cw"], m["ch"]; CY = 620; three = "sub" in m

    def slot(cx, label, colour, img, t0, hi=False):
        tracked(base, label, F("caps", 24), cx, CY - ch // 2 - 36, colour,
                fade(t, t0, .45) * a, tr=5, anchor="m")
        card(base, img, cx, CY, cw, ch, fade(t, t0 + .1, .5) * a, hi=hi)

    if three:
        xs = (360, 960, 1560)
        slot(xs[0], "INPUT", MUTED, m["src"], s0 + 1.4)
        slot(xs[1], "GENERATED", GOLD, m["out"], s0 + 3.6, hi=True)
        slot(xs[2], "THE MISSING PIECE", GREEN, m["sub"], s0 + 6.4)
        arrow_right(d, xs[0] + cw // 2 + 24, xs[1] - cw // 2 - 24, CY, mix(BG, GOLD, .9 * a),
                    prog(t, s0 + 2.4, .45))
        arrow_right(d, xs[1] + cw // 2 + 24, xs[2] - cw // 2 - 24, CY, mix(BG, MUTED, .9 * a),
                    prog(t, s0 + 5.2, .45))
        code_panel(base, t, 770, [(m["code"], s0 + 2.6), (m["code2"], s0 + 5.4)],
                   fade(t, s0 + 2.5, .4) * a, size=26)
    else:
        xi, xo = 560, 1360
        slot(xi, "INPUT", MUTED, m["src"], s0 + 1.4)
        slot(xo, "GENERATED", GOLD, m["out"], s0 + 4.0, hi=True)
        ax0, ax1 = xi + cw // 2 + 30, xo - cw // 2 - 30
        arrow_right(d, ax0, ax1, CY, mix(BG, GOLD, .9 * a), prog(t, s0 + 2.4, .45))
        ImageDraw.Draw(base).text(((ax0 + ax1) / 2, CY - 32), "generate_image",
                                  font=F("mono", 24),
                                  fill=mix(BG, GOLD, fade(t, s0 + 2.6, .4) * a), anchor="mm")
        code_panel(base, t, 828, [(m["code"], s0 + 2.6)], fade(t, s0 + 2.5, .4) * a, size=26)

# ── VII. Strategy discovery ───────────────────────────────────────────────────
def s_discovered(base, d, t):                                    # 122.8 – 139
    if t < 127.6:                                                # setup
        rblock(base, "Which visualization should the agent generate?", F("display", 54),
               W // 2, 320, INK, prog(t, 123.0, .9), maxw=1600, lh=70, anchor="mm")
        rblock(base, "Choosing which transformation to apply, and when, is itself a strategy. "
                     "Until now, these were written by hand for each task.", F("serif", 40),
               W // 2, 470, MUTED, prog(t, 124.2, 1.0), maxw=1400, lh=54, anchor="ma")
        rtext(base, "Can these strategies be discovered automatically?", F("display", 48),
              W // 2, 726, TERRA, prog(t, 125.8, .9), anchor="mm")
    elif t < 134.6:                                             # the discovery loop
        tracked(base, "AUTOMATIC STRATEGY DISCOVERY", F("caps", 28), W // 2, 208, MUTED,
                fade(t, 127.8, .5), tr=6, anchor="m")
        cx0, cy0, rx, ry = 960, 648, 452, 214
        nodes = [(-90, "1 · Propose strategies", 128.3), (0, "2 · Evaluate on a dev set", 129.2),
                 (90, "3 · Keep the best", 130.1), (180, "4 · Refine", 131.0)]
        # ring and arrows are drawn only after the four boxes are in place
        ea = fade(t, 131.9, .6)
        if ea > .01:
            ov = Image.new("RGBA", (rx * 2 + 40, ry * 2 + 40), (0, 0, 0, 0))
            ImageDraw.Draw(ov).ellipse([20, 20, 20 + rx * 2, 20 + ry * 2],
                                       outline=mix(BG, MUTED, .5) + (int(255 * ea),), width=3)
            base.paste(ov, (int(cx0 - rx - 20), int(cy0 - ry - 20)), ov)
        for k, deg in enumerate((-45, 45, 135, 225)):
            ah = fade(t, 132.3 + k * .12, .4)
            if ah <= .01: continue
            th = math.radians(deg)
            px, py = cx0 + rx * math.cos(th), cy0 + ry * math.sin(th)
            tang = math.atan2(ry * math.cos(th), -rx * math.sin(th))
            arrowhead(d, px, py, tang, mix(BG, GOLD, .9 * ah), 15)
        for deg, lab, t0 in nodes:
            th = math.radians(deg)
            px, py = cx0 + rx * math.cos(th), cy0 + ry * math.sin(th)
            chip(base, d, px, py, lab, F("display", 30), fade(t, t0, .5),
                 fillc=BG, txtc=INK, edge=INK)
        tracked(base, "REPEATED EACH ROUND", F("caps", 20), cx0, cy0, MUTED,
                fade(t, 132.9, .5), tr=4, anchor="m")
    else:                                                       # payoff
        a = fade(t, 134.9, .6)
        tracked(base, "DISCOVERED · SPATIAL REASONING", F("caps", 26), W // 2, 190,
                GOLD, a, tr=5, anchor="m")
        rblock(base, "When you enter the room through the white door, which way should you go "
                     "to reach the TV area?", F("serif", 37), W // 2, 256, MUTED,
               prog(t, 135.0, .7), maxw=1560, lh=46, anchor="ma")
        tracked(base, "A · GO STRAIGHT     B · GO LEFT     C · CANNOT BE DETERMINED     D · GO RIGHT",
                F("caps", 18), W // 2, 348, MUTED, fade(t, 135.15, .45), tr=3, anchor="m")

        tracked(base, "INPUT VIEWS", F("caps", 22), 470, 398, MUTED,
                fade(t, 135.2, .4), tr=5, anchor="m")
        card(base, "strategy_tv_input_1.png", 286, 565, 330, 264, fade(t, 135.3, .5))
        card(base, "strategy_tv_input_2.png", 654, 565, 330, 264, fade(t, 135.55, .5))

        ax0, ax1 = 844, 1030
        arrow_right(d, ax0, ax1, 565, mix(BG, GOLD, .9 * a), prog(t, 136.0, .5))
        ImageDraw.Draw(base).text(((ax0 + ax1) / 2, 525), "generate_image",
                                  font=F("mono", 22),
                                  fill=mix(BG, GOLD, fade(t, 136.0, .4) * a), anchor="mm")

        tracked(base, "GENERATED PANORAMA", F("caps", 22), 1420, 398, GOLD,
                fade(t, 136.35, .4), tr=5, anchor="m")
        card(base, "strategy_tv_panorama.png", 1420, 565, 720, 305,
             fade(t, 136.45, .55), hi=True)

        prompt = ('generate_image("Stitch these two overlapping images into a single continuous '
                  'wide-angle panorama, seamlessly blending the shared overlap area.")')
        code_panel(base, t, 776, [(prompt, 136.5)], fade(t, 136.4, .4) * a,
                   maxw=1540, size=22)
        chip(base, d, W // 2, 930, "D · GO RIGHT", F("display", 32),
             fade(t, 138.35, .45) * a, fillc=BG, txtc=GREEN, edge=GREEN)

# ── VIII. Results ─────────────────────────────────────────────────────────────
BARS = [("Collision", 44.7, 51.0, 54.0), ("Spatial", 36.0, 37.7, 43.7),
        ("Puzzle", 29.5, 16.7, 44.9), ("Tracing", 48.5, 41.7, 73.5),
        ("Depth", 83.9, 88.7, 89.2)]
B1, B2 = (190, 178, 158), (146, 158, 176)   # sand · dusty-blue (No tools · Fixed tools)
def s_results(base, d, t):                                       # 140.4 – 151
    a = fade(t, 140.5, .5)
    rtext(base, "Accuracy across tasks", F("display", 58), M, 224, INK, prog(t, 140.5, .8))
    tracked(base, "GPT-5", F("caps", 26), M, 286, MUTED, a, tr=5.5)
    lf, x = F("serif", 30), 1160
    for n, c in (("No tools", B1), ("Fixed tools", B2), ("ReImaGin", TERRA)):
        d.rectangle([x, 210, x + 22, 232], fill=mix(BG, c, a))
        ImageDraw.Draw(base).text((x + 32, 221), n, font=lf,
                                  fill=mix(BG, INK if c == TERRA else MUTED, a), anchor="lm")
        x += lf.getlength(n) + 74
    BASE_Y, TOP_Y = 790, 380
    rule_grow(d, M, W - M, BASE_Y, prog(t, 140.9, .7), MUTED, 1)
    gw = (W - 2 * M) / len(BARS); bw = 64
    vf, tf = F("serif", 28), F("serif", 32)
    for gi, (name, *vals) in enumerate(BARS):
        gx = M + gw * (gi + .5)
        for bi, (v, c) in enumerate(zip(vals, (B1, B2, TERRA))):
            gp = eo(prog(t, 141.3 + gi * .17 + bi * .06, .6))
            hgt = (v / 100) * (BASE_Y - TOP_Y) * gp
            bx = gx + (bi - 1) * (bw + 8)
            if hgt > 2:
                d.rectangle([bx - bw // 2, BASE_Y - hgt, bx + bw // 2, BASE_Y - 1], fill=mix(BG, c, a))
            if gp > .96:
                ImageDraw.Draw(base).text((bx, BASE_Y - hgt - 24), f"{v:.0f}", font=vf,
                                          fill=mix(BG, INK if c == TERRA else MUTED,
                                                   a * prog(t, 141.8 + gi * .17, .35)), anchor="mm")
        ImageDraw.Draw(base).text((gx, BASE_Y + 38), name, font=tf, fill=mix(BG, MUTED, a), anchor="mm")
    rtext(base, "Consistently outperforms both text-only reasoning and fixed tools.",
          F("display", 46), M, 888, INK, prog(t, 145.4, .9))
    rtext(base, "Across six tasks and three models.", F("serif", 34), M, 950, MUTED,
          prog(t, 147.8, .8))

def s_open(base, d, t):                                          # opening card (native 0–6.5)
    img_contain(base, "logos_strip.png", W // 2, 158, 1020, 150, fade(t, 0.2, .6))
    p = prog(t, 0.7, 1.0)
    rtext(base, "ReImaGin", F("display", 132), W // 2, 384, INK, p, anchor="mm")
    rule_grow(d, W // 2 - 180, W // 2 + 180, 476, prog(t, 1.2, .7), FAINT)
    tracked(base, "REASONING WITH IMAGE GENERATION", F("caps", 30), W // 2, 542, TERRA,
            fade(t, 1.5, .6), tr=6, anchor="m")
    a2 = fade(t, 2.3, .7)
    if a2 > .01:                                 # authors, with superscripted * and †
        fn, fs = F("serif", 32), F("serif", 21)
        toks = [("Nishad Singhi", 0), ("*†", 1), (",  ", 0),
                ("Hector Garcia Rodriguez", 0), ("*†", 1), (",  ", 0),
                ("Aditya Arora", 0), ("†", 1), (",  ", 0),
                ("Marcus Rohrbach", 0), (",  ", 0), ("Anna Rohrbach", 0)]
        total = sum((fs if s else fn).getlength(txt) for txt, s in toks)
        x = W // 2 - total / 2; col = mix(BG, INK, a2); dd = ImageDraw.Draw(base)
        for txt, s in toks:
            f = fs if s else fn
            dd.text((x, 690 - (14 if s else 0)), txt, font=f, fill=col, anchor="lm")
            x += f.getlength(txt)
    tracked(base, "* EQUAL CONTRIBUTION       † CORE CONTRIBUTORS", F("caps", 20), W // 2, 740,
            MUTED, a2, tr=3.5, anchor="m")
    a3 = fade(t, 3.0, .7)
    tracked(base, "TECHNICAL UNIVERSITY OF DARMSTADT  ·  HESSIAN.AI", F("caps", 22), W // 2, 822,
            MUTED, a3, tr=4.5, anchor="m")
    tracked(base, "COLM 2026", F("caps", 26), W // 2, 874, TERRA, a3, tr=7, anchor="m")

def s_tts(base, d, t):                                           # test-time scaling (native 0–9)
    rblock(base, "A new axis of test-time scaling.", F("display", 56), W // 2, 172, INK,
           prog(t, 0.3, .9), maxw=1600, lh=70, anchor="mm")
    rblock(base, "Sample many images for one prompt, then keep the most faithful.",
           F("serif", 40), W // 2, 248, MUTED, prog(t, 1.2, 1.0), maxw=1500, lh=54, anchor="ma")
    img_contain(base, "ttssch.png", W // 2, 520, 1140, 420, fade(t, 2.2, .8))
    a = fade(t, 4.8, .7)
    tracked(base, "SPATIAL REASONING ACCURACY  ·  SINGLE GENERATION vs. BEST OF 10",
            F("caps", 22), W // 2, 806, MUTED, a, tr=3.5, anchor="m")
    ga = fade(t, 5.0, .6)
    for (name, a0, a1), gx in zip([("GEMINI-3.1-PRO", "51", "59"), ("GPT-5", "39", "44"),
                                    ("QWEN-3.5-27B", "42", "54")],
                                   [W // 2 - 470, W // 2, W // 2 + 470]):
        tracked(base, name, F("caps", 22), gx, 864, MUTED, ga, tr=3, anchor="m")
        f = F("display", 46); gap = 68
        w0, w1 = f.getlength(a0), f.getlength(a1); tot = w0 + gap + w1; sx = gx - tot / 2
        rtext(base, a0, f, sx, 922, MUTED, ga, anchor="lm")
        col = mix(BG, MUTED, .9 * ga)
        ax0, ax1 = sx + w0 + 14, sx + w0 + gap - 16
        d.line([(ax0, 922), (ax1, 922)], fill=col, width=3)
        if ga > .5: d.polygon([(ax1, 914), (ax1, 930), (ax1 + 12, 922)], fill=col)
        rtext(base, a1, f, sx + w0 + gap, 922, GREEN, ga, anchor="lm")

def s_close(base, d, t):                                         # closing card (native 0–5)
    p = prog(t, 0.3, 1.0)
    rtext(base, "ReImaGin", F("display", 124), W // 2, 430, INK, p, anchor="mm")
    rule_grow(d, W // 2 - 160, W // 2 + 160, 520, prog(t, 0.8, .7), FAINT)
    tracked(base, "REASONING WITH IMAGE GENERATION", F("caps", 28), W // 2, 584, TERRA,
            fade(t, 1.1, .6), tr=6, anchor="m")
    tracked(base, "COLM 2026", F("caps", 24), W // 2, 660, MUTED, fade(t, 1.8, .6), tr=6, anchor="m")

# ── running order: each clip remaps global time into a scene's native window ──────
#   scene clip: fn drawn at native time  (T - clip_start + native_start)
#   title clip: chapter divider card
_CH = {"Q": "I.  THE QUESTION", "T": "II.  REASONING WITH TOOLS", "K": "III.  THE KEY INSIGHT",
       "R": "IV.  REIMAGIN", "M": "V.  MANY TASKS", "RES": "VI.  RESULTS",
       "TTS": "VII.  TEST-TIME SCALING", "D": "VIII.  STRATEGY DISCOVERY"}
_SEQ = [
    dict(k="s", fn=s_hook,       nat=0.0,   dur=16.0, chap=_CH["Q"]),
    dict(k="t", num="II.",   name="Reasoning with Tools", dur=1.4, chap=_CH["T"]),
    dict(k="s", fn=s_prior,      nat=25.4,  dur=8.6,  chap=_CH["T"]),
    dict(k="s", fn=s_menu,       nat=34.0,  dur=9.0,  chap=_CH["T"]),
    dict(k="t", num="III.",  name="The Key Insight",      dur=1.4, chap=_CH["K"]),
    dict(k="s", fn=s_shift,      nat=44.4,  dur=8.6,  chap=_CH["K"]),
    dict(k="t", num="IV.",   name="ReImaGin",             dur=1.4, chap=_CH["R"]),
    dict(k="s", fn=s_reimagin,   nat=54.4,  dur=31.6, chap=_CH["R"]),
    dict(k="t", num="V.",    name="Many Tasks",           dur=1.4, chap=_CH["M"]),
    dict(k="s", fn=s_montage,    nat=87.4,  dur=34.0, chap=_CH["M"]),
    dict(k="t", num="VI.",   name="Results",              dur=1.4, chap=_CH["RES"]),
    dict(k="s", fn=s_results,    nat=140.4, dur=10.6, chap=_CH["RES"]),
    dict(k="t", num="VII.",  name="Test-Time Scaling",    dur=1.4, chap=_CH["TTS"]),
    dict(k="s", fn=s_tts,        nat=0.0,   dur=9.0,  chap=_CH["TTS"]),
    dict(k="t", num="VIII.", name="Strategy Discovery",   dur=1.4, chap=_CH["D"]),
    dict(k="s", fn=s_discovered, nat=122.8, dur=17.8, chap=_CH["D"]),
    dict(k="s", fn=s_open,       nat=0.0,   dur=5.0,  chap=""),
]
_a = 0.0
for _c in _SEQ:
    _c["s0"], _c["s1"] = _a, _a + _c["dur"]; _a += _c["dur"]
TOTAL = _a

def draw_title(base, d, T, c):
    s, e = c["s0"], c["s1"]
    p = prog(T, s + .06, .5); out = 1 - prog(T, e - .25, .25)
    tracked(base, c["num"], F("caps", 30), W // 2, 452, TERRA, p * out, tr=9, anchor="m")
    rtext(base, c["name"], F("display", 92), W // 2, 552, INK, p, anchor="mm")
    rule_grow(d, W // 2 - 130, W // 2 + 130, 632, prog(T, s + .3, .45), FAINT)

def draw_chrome(base, d, T, c, tout):
    if c["k"] == "s" and c["chap"]:
        tracked(base, "REIMAGIN", F("caps", 24), M, 78, mix(BG, INK, .8), 1, tr=6)
        tracked(base, c["chap"], F("caps", 24), W - M, 78, MUTED, .9, tr=6, anchor="r")
        rule(d, M, W - M, 118, .8)
        rule(d, M, W - M, H - 90, .8)
    d.rectangle([0, H - 4, int(W * tout / TOTAL), H - 1], fill=mix(BG, TERRA, .85))

def render(T, tout=None):
    base = BASE_BG.copy(); d = ImageDraw.Draw(base)
    c = next((cl for cl in _SEQ if cl["s0"] <= T < cl["s1"]), _SEQ[-1])
    if c["k"] == "t":
        draw_title(base, d, T, c)
    else:
        c["fn"](base, d, T - c["s0"] + c["nat"])
    draw_chrome(base, d, T, c, T if tout is None else tout)
    return base

def main():
    n = int(TOTAL * FPS)
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
         "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE)
    for i in range(n):
        T = i / FPS
        p.stdin.write(render(T, T).tobytes())
        if i % 400 == 0: print(f"  {i}/{n}", flush=True)
    p.stdin.close(); p.wait()
    print("done ->", OUT, f"({TOTAL:.1f}s)")

if __name__ == "__main__":
    main()
