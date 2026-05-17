"""
Генератор іконок для AXIS OS.
Запусти: python create_icons.py
Створює іконки в папці data/
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path("data")
OUT.mkdir(exist_ok=True)

SIZES = [16, 32, 48, 64, 128, 256]


def make_canvas(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def hex_points(cx, cy, r, rotate=0):
    pts = []
    for i in range(6):
        a = math.radians(60 * i + rotate)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def save_ico(frames, path):
    frames[0].save(
        path, format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"  OK {path}")


# ═══════════════════════════════════════════════════════════
# 1. AXIS OS  — шестикутник з літерою A (зелений)
# ═══════════════════════════════════════════════════════════
def make_axis_icon():
    frames = []
    for size in SIZES:
        img, draw = make_canvas(size)
        cx = cy = size / 2
        r  = size * 0.44
        pad = size * 0.04

        # Фон — темний
        draw.rounded_rectangle([pad, pad, size-pad, size-pad],
                                radius=size*0.18, fill=(8, 9, 15, 255))

        # Шестикутник — зелений градієнт (два трикутники)
        pts = hex_points(cx, cy, r * 0.82, rotate=-30)
        draw.polygon(pts, fill=(16, 185, 129, 255))

        # Внутрішній шестикутник темніший
        pts2 = hex_points(cx, cy, r * 0.55, rotate=-30)
        draw.polygon(pts2, fill=(8, 9, 15, 230))

        # Літера "A"
        fs = max(8, int(size * 0.38))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", fs)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "A", font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cx - tw / 2 - bbox[0]
        ty = cy - th / 2 - bbox[1]
        draw.text((tx, ty), "A", font=font, fill=(16, 185, 129, 255))

        frames.append(img)
    save_ico(frames, OUT / "icon.ico")
    save_ico(frames, OUT / "icon_panel.ico")


# ═══════════════════════════════════════════════════════════
# 2. AIVON Sphere — куля з ореолом (фіолетово-синій)
# ═══════════════════════════════════════════════════════════
def make_sphere_icon():
    frames = []
    for size in SIZES:
        img, draw = make_canvas(size)
        cx = cy = size / 2
        pad = size * 0.04

        # Фон
        draw.rounded_rectangle([pad, pad, size-pad, size-pad],
                                radius=size*0.18, fill=(8, 9, 15, 255))

        # Ореол / glow
        glow_r = size * 0.40
        for i in range(8, 0, -1):
            alpha = int(18 * i / 8)
            gr = glow_r + i * size * 0.025
            draw.ellipse([cx-gr, cy-gr, cx+gr, cy+gr],
                         fill=(139, 92, 246, alpha))

        # Куля
        r = size * 0.32
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(99, 102, 241, 255))

        # Highlight
        hr = r * 0.45
        draw.ellipse([cx - hr*0.9, cy - hr*1.1,
                      cx + hr*0.1, cy + hr*0.1],
                     fill=(200, 195, 255, 120))

        # Хвильки (3 горизонтальні лінії)
        lw = max(1, int(size * 0.05))
        lc = (255, 255, 255, 180)
        for yi, amp in [(-1, 0.14), (0, 0.09), (1, 0.14)]:
            y = cy + yi * r * 0.35
            x0 = cx - r * 0.55
            x1 = cx + r * 0.55
            draw.line([(x0, y), (x1, y)], fill=lc, width=lw)

        frames.append(img)
    save_ico(frames, OUT / "icon_sphere.ico")


# ═══════════════════════════════════════════════════════════
# 3. AXIS IDE — кутові дужки </> (синій)
# ═══════════════════════════════════════════════════════════
def make_ide_icon():
    frames = []
    for size in SIZES:
        img, draw = make_canvas(size)
        cx = cy = size / 2
        pad = size * 0.04

        # Фон
        draw.rounded_rectangle([pad, pad, size-pad, size-pad],
                                radius=size*0.18, fill=(8, 9, 15, 255))

        # Акцентний квадрат
        aw = size * 0.72
        ap = (size - aw) / 2
        draw.rounded_rectangle([ap, ap, ap+aw, ap+aw],
                                radius=size*0.12, fill=(14, 165, 233, 30))

        # </> символ
        fs = max(7, int(size * 0.40))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", fs)
        except Exception:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", fs)
            except Exception:
                font = ImageFont.load_default()

        text = "</>"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cx - tw / 2 - bbox[0]
        ty = cy - th / 2 - bbox[1]

        # Тінь
        draw.text((tx+1, ty+1), text, font=font, fill=(0, 0, 0, 120))
        draw.text((tx, ty), text, font=font, fill=(56, 189, 248, 255))

        frames.append(img)
    save_ico(frames, OUT / "icon_ide.ico")


if __name__ == "__main__":
    print("Generating icons...")
    make_axis_icon()
    make_sphere_icon()
    make_ide_icon()
    print("\nDone!")
    print("  data/icon.ico        -- AXIS Panel (main)")
    print("  data/icon_panel.ico  -- AXIS Panel")
    print("  data/icon_sphere.ico -- AXIS Sphere")
    print("  data/icon_ide.ico    -- AXIS IDE")
