"""Draw the built-in logo (ftth_addrlist/assets/logo.png, packaging/app.ico). Needs Pillow; run once when
the design changes. A company logo can replace it without code changes: put logo.png in the assets
folder next to the program (see README)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024                      # drawn large, scaled down for smooth edges


def draw() -> Image.Image:
    """Map pin (the premise address) holding a short list in the fibre colour code (blue, orange, green):
    an address list for fibre. Blue-to-teal tile."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gp = grad.load()
    a, b = (11, 61, 145), (0, 150, 136)                 # deep blue -> teal, diagonal
    for y in range(S):
        for x in range(0, S, 4):
            t = (x + y) / (2 * S)
            c = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
            for k in range(4):
                gp[x + k, y] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # soft shadow under the pin
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([352, 838, 672, 898], fill=(0, 0, 0, 70))
    img.alpha_composite(shadow)
    # pin: circle head + point
    cx, cy, r = 512, 430, 300
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))
    d.polygon([(cx - 236, cy + 186), (cx + 236, cy + 186), (cx, 860)], fill=(255, 255, 255, 255))
    # list inside the head: bullet + bar per fibre colour
    colours = [(30, 136, 229), (251, 140, 0), (67, 160, 71)]
    for i, col in enumerate(colours):
        y = cy - 120 + i * 120
        d.ellipse([cx - 175, y - 34, cx - 107, y + 34], fill=col + (255,))
        d.rounded_rectangle([cx - 70, y - 30, cx + 185, y + 30], radius=30, fill=col + (255,))
    return img


if __name__ == "__main__":
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(ROOT / "ftth_addrlist" / "assets" / "logo.png")
    big.resize((256, 256), Image.LANCZOS).save(ROOT / "packaging" / "app.ico",
                                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("logo written")
