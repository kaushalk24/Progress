# -*- coding: utf-8 -*-
"""FiberCallout Studio logo, drawn with QPainter so it is crisp at every size (window icon, header, .ico)."""
from __future__ import annotations

from pathlib import Path
from typing import List

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)

NAVY = QColor("#0B2545")
TEAL = QColor("#13808C")
MAGENTA = QColor("#FF2BD6")
FIBERS = [QColor("#3D8BFD"), QColor("#FF8A3D"), QColor("#2ECC71")]


def render_logo(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    m = s * 0.04
    tile = QRectF(m, m, s - 2 * m, s - 2 * m)
    grad = QLinearGradient(tile.topLeft(), tile.bottomRight())
    grad.setColorAt(0.0, NAVY)
    grad.setColorAt(1.0, TEAL)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(tile, s * 0.22, s * 0.22)
    if size >= 48:
        p.setPen(QPen(QColor(255, 255, 255, 22), max(1.0, s * 0.006)))
        for f in (0.30, 0.55, 0.80):
            p.drawLine(QPointF(tile.left() + s * 0.06, s * f), QPointF(tile.right() - s * 0.06, s * f))
    cx, cy = s * 0.60, s * 0.64
    # fibre strands converging into the closure
    for i, col in enumerate(FIBERS):
        y0 = s * (0.40 + 0.13 * i)
        path = QPainterPath(QPointF(s * 0.15, y0))
        path.cubicTo(QPointF(s * 0.32, y0), QPointF(s * 0.38, cy), QPointF(cx - s * 0.06, cy))
        pen = QPen(col, s * 0.055)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    # splice closure (bow-tie, as drawn on the Fiber Splice layer)
    w, h = s * 0.30, s * 0.20
    p.setPen(QPen(QColor("white"), max(1.0, s * 0.012)))
    p.setBrush(QColor("white"))
    p.drawPolygon(QPolygonF([QPointF(cx - w / 2, cy - h / 2), QPointF(cx, cy), QPointF(cx - w / 2, cy + h / 2)]))
    p.drawPolygon(QPolygonF([QPointF(cx + w / 2, cy - h / 2), QPointF(cx, cy), QPointF(cx + w / 2, cy + h / 2)]))
    # magenta DES_FIBER_SPL callout: leader with arrowhead, landing underline, number
    tip = QPointF(cx + s * 0.05, cy - s * 0.08)
    land = QPointF(s * 0.66, s * 0.30)
    pen = QPen(MAGENTA, max(1.2, s * 0.03))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(land, tip)
    p.drawLine(land, QPointF(s * 0.86, s * 0.30))
    vx, vy = tip.x() - land.x(), tip.y() - land.y()
    ln = (vx * vx + vy * vy) ** 0.5
    ux, uy = vx / ln, vy / ln
    a = s * 0.11
    base = QPointF(tip.x() - ux * a, tip.y() - uy * a)
    nx, ny = -uy * a * 0.38, ux * a * 0.38
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(MAGENTA)
    p.drawPolygon(QPolygonF([tip, QPointF(base.x() + nx, base.y() + ny), QPointF(base.x() - nx, base.y() - ny)]))
    if size >= 40:
        f = QFont("Arial")
        f.setBold(True)
        f.setPixelSize(int(s * 0.19))
        p.setFont(f)
        p.setPen(MAGENTA)
        p.drawText(QRectF(s * 0.64, s * 0.08, s * 0.28, s * 0.22), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom), "72")
    else:
        p.setBrush(MAGENTA)
        p.drawRoundedRect(QRectF(s * 0.66, s * 0.16, s * 0.20, s * 0.09), s * 0.03, s * 0.03)
    p.end()
    return img


def logo_pixmap(size: int) -> QPixmap:
    return QPixmap.fromImage(render_logo(size))


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(sz))
    return icon


def export_assets(folder: str) -> List[str]:
    """Write logo PNGs and a multi-resolution Windows .ico (used by the PyInstaller build)."""
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for sz in (256, 512):
        p = out / f"logo_{sz}.png"
        render_logo(sz).save(str(p))
        written.append(str(p))
    ico = out / "app.ico"
    try:
        from PIL import Image
        imgs = []
        for sz in (16, 24, 32, 48, 64, 128, 256):
            tmp = out / f"_ico_{sz}.png"
            render_logo(sz).save(str(tmp))
            imgs.append(Image.open(tmp).convert("RGBA"))
        imgs[-1].save(ico, format="ICO", sizes=[(i.width, i.height) for i in imgs], append_images=imgs[:-1])
        for sz in (16, 24, 32, 48, 64, 128, 256):
            (out / f"_ico_{sz}.png").unlink(missing_ok=True)
    except ImportError:
        render_logo(256).save(str(ico))
    written.append(str(ico))
    return written
