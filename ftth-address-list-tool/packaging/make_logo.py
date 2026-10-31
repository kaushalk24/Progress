"""Draw the built-in logo (ftth_addrlist/assets/logo.png, packaging/app.ico). Needs Pillow; run once when
the design changes. A company logo can replace it without code changes: put logo.png in the assets
folder next to the program (see README)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024                      # drawn large, scaled down for smooth edges


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # rounded tile with a vertical navy gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)], fill=(int(14 + 16 * t), int(42 + 30 * t), int(74 + 40 * t), 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=210, fill=255)
    img.paste(grad, (0, 0), mask)
    hub = (270, 512)
    ends = [(800, 250), (840, 512), (800, 774)]
    colours = [(30, 136, 229), (251, 140, 0), (67, 160, 71)]      # fibre colour code: blue, orange, green
    for (ex, ey), col in zip(ends, colours):
        # quadratic curve hub -> premise
        cx, cy = (hub[0] + ex) / 2, ey
        pts = [((1 - t) ** 2 * hub[0] + 2 * (1 - t) * t * cx + t * t * ex,
                (1 - t) ** 2 * hub[1] + 2 * (1 - t) * t * cy + t * t * ey) for t in [i / 400 for i in range(401)]]
        for x, y in pts:                      # round brush: an even stroke without joint artefacts
            d.ellipse([x - 23, y - 23, x + 23, y + 23], fill=col + (255,))
        d.ellipse([ex - 62, ey - 62, ex + 62, ey + 62], fill=(255, 255, 255, 255))
        d.ellipse([ex - 30, ey - 30, ex + 30, ey + 30], fill=col + (255,))
    d.ellipse([hub[0] - 120, hub[1] - 120, hub[0] + 120, hub[1] + 120], fill=(255, 255, 255, 255))
    d.ellipse([hub[0] - 62, hub[1] - 62, hub[0] + 62, hub[1] + 62], fill=(14, 42, 74, 255))
    return img


if __name__ == "__main__":
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(ROOT / "ftth_addrlist" / "assets" / "logo.png")
    big.resize((256, 256), Image.LANCZOS).save(ROOT / "packaging" / "app.ico",
                                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("logo written")
