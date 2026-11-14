# Run from the repo: uv run packaging/store/make_banner.py
"""Snap Store banner (1920 x 640, 3:1): logo, name, tagline, OTB's own board."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)

import chess
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QApplication

import otb

W, H = 1920, 640
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.png")

app = QApplication(sys.argv)

# Najdorf Sicilian; engine arrow Be3 (blue), book move Be2 (yellow, as on hover)
board = chess.Board()
for san in "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6".split():
    board.push_san(san)
widget = otb.BoardWidget(lambda: board, lambda: "VIEW", lambda move: None)
widget.set_coordinates("inside")
widget.set_engine_arrow((chess.C1, chess.E3))
widget.set_hover_arrow((chess.F1, chess.E2))
BOARD = 528  # multiple of 8: crisp squares
widget.resize(BOARD, BOARD)
widget.redraw()
board_image = widget.grab().toImage()

img = QImage(W, H, QImage.Format.Format_ARGB32)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

# dark, slightly metallic background
bg = QLinearGradient(0, 0, 0, H)
bg.setColorAt(0, QColor("#2b2e33"))
bg.setColorAt(1, QColor("#141518"))
p.fillRect(0, 0, W, H, bg)
glow = QRadialGradient(QPointF(W * 0.74, H * 0.5), 620)
glow.setColorAt(0, QColor(123, 148, 157, 70))
glow.setColorAt(1, QColor(123, 148, 157, 0))
p.fillRect(0, 0, W, H, glow)

# board on the right, with a soft shadow
bx, by = W - 160 - BOARD, (H - BOARD) // 2
for i in range(18, 0, -1):
    p.fillRect(QRectF(bx - i, by - i + 10, BOARD + 2 * i, BOARD + 2 * i), QColor(0, 0, 0, 7))
p.drawImage(bx, by, board_image)

# logo, name, tagline on the left
logo = QImage(os.path.join(ROOT, "otb_icon.png"))
LOGO = 230
lx = 150
p.drawImage(QRectF(lx, (H - LOGO) / 2, LOGO, LOGO), logo)
tx = lx + LOGO + 56

title = QFont("Noto Sans", 1)
title.setPixelSize(76)
title.setWeight(QFont.Weight.Bold)
p.setFont(title)
p.setPen(QColor("#f2f2f2"))
p.drawText(QPointF(tx, H / 2 - 22), "Opening Tree")
p.drawText(QPointF(tx, H / 2 + 62), "Builder")

sub = QFont("Noto Sans", 1)
sub.setPixelSize(34)
p.setFont(sub)
p.setPen(QColor("#aab4b9"))
p.drawText(QPointF(tx, H / 2 + 140), "Your chess opening repertoire. Offline.")

p.setPen(QPen(QColor("#7b949d"), 3))
p.drawLine(QPointF(tx, H / 2 + 92), QPointF(tx + 120, H / 2 + 92))
p.end()

img.save(OUT)
print(OUT, img.width(), img.height(), os.path.getsize(OUT))
