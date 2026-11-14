#!/usr/bin/env python3


# Copyright (C) 2026 [www.gambitgear.ch]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import base64
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn
import chess.polyglot
import chess.svg

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSettings,
    QStandardPaths,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QTransform,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

MIN_BOARD_SIZE = 320   # smallest the board will shrink to
# "Autoplay from here": time per move for each View > Autoplay Speed setting
PLAY_SPEEDS_MS = {"Slow": 2000, "Medium": 1000, "Fast": 500}
DEFAULT_PLAY_SPEED = "Medium"
# View > Coordinates: setting value -> menu text
COORDINATE_MODES = {"inside": "Inside the Board", "outside": "Outside the Board", "off": "None"}
DEFAULT_COORDINATES = "off"
# How long a piece glides to its square, for each View > Animation Speed
# setting; the same as Lichess' slow / normal / fast.
ANIMATION_SPEEDS_MS = {"Slow": 500, "Medium": 250, "Fast": 120}
DEFAULT_ANIMATION_SPEED = "Medium"
RIGHT_PANEL_WIDTH = 280  # constant width for the nav+list panel
LINE_PANEL_WIDTH = RIGHT_PANEL_WIDTH  # current-line score sheet + nav buttons, same width as the right panel
DRAG_THRESHOLD = 6  # px of mouse movement before a press counts as a drag

# Book move under the mouse: a thin, solid yellow arrow. Sizes in squares:
# the tip stops 0.1 before the target square's center.
HOVER_ARROW_COLOR = QColor("#ffcc00")
HOVER_ARROW_WIDTH = 0.1
HOVER_ARROW_HEAD = 0.375   # length and width of the head
HOVER_ARROW_MARGIN = 0.1
# Engine best move, drawn like Lichess' pale blue engine arrow (#003088 at 24%).
# Sizes in squares: a shaft of 15/512 of the board with round ends, a head 4
# shaft widths wide and 3 long, the shaft stopping 10/64 before the target
# square's center so that the tip ends just past it.
ENGINE_ARROW_COLOR = QColor(0, 48, 136, 61)
ENGINE_ARROW_WIDTH = 15 / 512 * 8
ENGINE_ARROW_MARGIN = 10 / 64
# Arrows and circles drawn by hand with the right mouse button, as on Lichess:
# its green (#15781b; Lichess shows all its shapes at 60%), a thinner shaft,
# and a ring just inside the square. They live only in memory and only while
# the position they were drawn on is shown.
USER_SHAPE_COLOR = QColor(0x15, 0x78, 0x1B, 153)
USER_ARROW_WIDTH = 10 / 512 * 8
USER_CIRCLE_WIDTH = 4 / 64
DRAG_SOURCE_COLOR = "#ffff0088"       # semi-transparent yellow for start square (hovering)
SELECTED_SQUARE_COLOR = "#14551e80"   # clicked start square: Lichess' translucent green, rgba(20, 85, 30, 0.5)
APP_VERSION = "1.2"
APP_ORG = "GambitGear"  # shared by all GambitGear apps: data/settings live under GambitGear/<app>
APP_NAME = "OTB"
USER_GUIDE_URL = "https://github.com/malo1972/otb#readme"

HOVER_ROW_COLOR = QColor(0x88, 0x88, 0x88, 90)  # same mid-grey as button hover
                                        # (#888888); translucent because the delegate
                                        # paints this over the already-drawn move text,
                                        # not behind it like a button's own background
TRANSPOSITION_ROW_COLOR = QColor(255, 0, 0, 55)  # translucent red overlay for moves
                                                  # whose resulting position is also
                                                  # reachable via a different move order
# Where the selected piece can go, marked as on Lichess: a small dot on an
# empty square, more faintly shaded corners (a circle cut out of the square) on a capture.
TARGET_MARK_COLOR = QColor(20, 85, 30, 128)  # Lichess' translucent green, as the selected square
TARGET_CAPTURE_COLOR = QColor(20, 85, 0, 77)   # Lichess: rgba(20, 85, 0, 0.3)
TARGET_DOT_RADIUS = 0.135       # of the square's side
TARGET_CAPTURE_RADIUS = 0.565   # of the square's side: wider than the square, only the corners stay shaded

NAV_BUTTON_ICON_COLOR = QColor("#d9dcdf")  # soft silver, for the symbols on the black MetalButtons
NAV_BUTTON_STYLE = "QPushButton { padding: 10px 18px; font-size: 12pt; }"  # size only, MetalButton paints itself
NAV_ICON_SIZE = 22


def _icon_color() -> QColor:
    """Current theme's text color, so hand-drawn icons stay visible in
    both light and dark mode instead of using a fixed color. Also used
    for the move-list text, so button symbols and move text match."""
    return QApplication.palette().color(QPalette.ColorRole.WindowText)


def _build_dual_icon(draw_fn, size: int, color: QColor | None) -> QIcon:
    """Build a QIcon with an explicit, faint ('shallow') Disabled-mode
    pixmap alongside the normal one. Qt's automatic disabled-icon
    generation doesn't fade a solid custom silhouette very noticeably, so
    a disabled nav button doesn't read as clearly inactive without this."""
    color = color or _icon_color()
    icon = QIcon()
    icon.addPixmap(draw_fn(size, color), QIcon.Mode.Normal)
    faint = QColor(color)
    faint.setAlpha(60)
    icon.addPixmap(draw_fn(size, faint), QIcon.Mode.Disabled)
    return icon


def _draw_flip_pixmap(size: int, color: QColor) -> QPixmap:
    """Two antidromic (opposite-direction) arrows: one up on the left, one
    down on the right -- reads as 'swap top and bottom', i.e. flip."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(color, max(1.5, size * 0.09), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(color)

    margin = size * 0.12
    head = size * 0.22

    x1 = size * 0.32  # left shaft: arrow points UP
    painter.drawLine(QPointF(x1, size - margin), QPointF(x1, margin + head * 0.5))
    painter.drawPolygon(QPolygonF([
        QPointF(x1 - head / 2, margin + head),
        QPointF(x1 + head / 2, margin + head),
        QPointF(x1, margin),
    ]))

    x2 = size * 0.68  # right shaft: arrow points DOWN
    painter.drawLine(QPointF(x2, margin), QPointF(x2, size - margin - head * 0.5))
    painter.drawPolygon(QPolygonF([
        QPointF(x2 - head / 2, size - margin - head),
        QPointF(x2 + head / 2, size - margin - head),
        QPointF(x2, size - margin),
    ]))

    painter.end()
    return pixmap


def _make_flip_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    return _build_dual_icon(_draw_flip_pixmap, size, color)


def _draw_step_back_pixmap(size: int, color: QColor) -> QPixmap:
    """A single triangle pointing left -- a play button rotated 180
    degrees -- for 'step back one move'."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    margin = size * 0.18
    painter.drawPolygon(QPolygonF([
        QPointF(size - margin, margin),
        QPointF(size - margin, size - margin),
        QPointF(margin, size / 2),
    ]))

    painter.end()
    return pixmap


def _make_step_back_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    return _build_dual_icon(_draw_step_back_pixmap, size, color)


def _draw_skip_start_pixmap(size: int, color: QColor) -> QPixmap:
    """A vertical bar plus a left-pointing triangle -- 'skip to start' --
    hand-drawn like the other nav icons so all three share the exact same
    color, rather than mixing in the OS-native icon's own shade."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    margin = size * 0.16
    bar_width = size * 0.14
    painter.drawRect(QRectF(margin, margin, bar_width, size - 2 * margin))
    tri_left = margin + bar_width + size * 0.08
    painter.drawPolygon(QPolygonF([
        QPointF(size - margin, margin),
        QPointF(size - margin, size - margin),
        QPointF(tri_left, size / 2),
    ]))

    painter.end()
    return pixmap


def _make_skip_start_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    return _build_dual_icon(_draw_skip_start_pixmap, size, color)


def _mirrored(draw_fn):
    """Horizontally mirrored variant of a nav pixmap draw function, so the
    forward icons are exact mirror images of the back ones."""
    def draw(size: int, color: QColor) -> QPixmap:
        return draw_fn(size, color).transformed(QTransform().scale(-1, 1))
    return draw


def _make_step_forward_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    return _build_dual_icon(_mirrored(_draw_step_back_pixmap), size, color)


def _make_skip_end_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    return _build_dual_icon(_mirrored(_draw_skip_start_pixmap), size, color)


ENGINE_ICON_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAALh0lEQVR42u2da6wdVRXHfzP33Hvb2pbU0tZnsRFFFKxUAq3G+kBB"
    "Mcb4aPwgMQr4RNEgQYyJoomRggYLxlSMgn4wKorvCCQqgomIYqUIjRKUKJSH0tLWFs6958z4Ya+dszud95k558zc9U927j33nnnt"
    "9d/rtfesDQqFQqFQKBQKhUKhUCgUCoVCoVAoFIrWwlvg168KYVNvfGrM1w1bNJCmVAPkv6YV/HRLtMCcmoD81wqBc4CzgGc0deRE"
    "1P+jwA+AK4F+hOQKgS8/t0vntLH9COjIs3oq8iNt/pnSUXNAT0ZLG1oP6MqznSvP2lGxD2A74xrpsPkWjv55ebYbIxqvEWp5VGHS"
    "8harRk/asiZFOP4IOwfgTvk9aCEBrPP31zGH2BMZBfgyIp4uJDha7GbV3nKeeLxfwzVDMXNdYANwj9xHX63/kdrmVODuFvoA94uT"
    "2xj7P45EkC/qfxHwKmBtRZ1lzcpq4DMZWuBy4D75TlWm6CHgZmCf84yKMfgdqyTEDEUI7gi1n09sgU9VeXg2SgQy+jo1aJZVOb67"
    "EpitwUb3mmjzO2PSAP2aOuuxHN/ZI85anSZOCZDRQccDW4BjKgqXrA9wlHM+L8HfuRR4xIlMqshxPIhJA9+hPkC2fXw38EQLo4A+"
    "cJFGAekj/8XADvk8X8P1x5EHwEn8eMBrgV9pHiDe1FzBYDKojXMBAXCdQ4gFHZJF7STAOvndbyHJ7VzAWifaaZwT6EUEVpUpsZ2z"
    "EObJG/V8HUcTeI7N8pxwLUuDeDm+18s5KsIGjByvTRqsEwlbngLMAHtFqGkhjTurt0Sal+IgzWNSwMM6cYqKCRAAzwE+B7waWAzs"
    "BC4DbkgggZ0BW+sctzxjZIRCsDgHKZRz3g/8qcIYveqRHwAvkjxG2BZztk46Ps6zfUeMwKzaf1bKcWU86BD4agP665ORe7atJz9v"
    "b5Iv0AG+hMnIzWGWaVubPQ1sEy2w3xn1diR8Vo7ritmowkGaYTBP0JvAvurlMGONMwGvE8G6QpwWIa/BLHD4DYPp07589zXyucq1"
    "/TajlsexHIcJqCuJNFYCLE0RRgisiPnfIrHnVdrqgPomadqAoiF0roiqk4P1o2B8IPfy+5YJKyzw/GnnCoYIj1Mnpzo1CzVPB3hi"
    "Uv4IXJ8z/zDJKCMsj/jFsq7wNgBPyxkm94HdwF/k+EQSdGoeBeS82Z8C78fMEjb1tSrPyaW8MOdzeOJg/5tBijyICP9E4GvAphL3"
    "dBvwQSFCLAk6NY0AH9iKWSc3nTIievLw94zY5NRJ+BOAuwoc94Rov4uBPzh+VYh5d/ImGflBwb7xgI2YF1VOAh5OIkFSbG7j2rc4"
    "uQDL8uWYFyLj1t7Z495UQgVOusMMcElCHmDYdlDUPE5E9nn5X7fkObuR/MpUWTVdBkvlgja2T2ou49uCooKaw6TSvxBxCk+V/5dN"
    "j1vt+05Hi/ijIoDNGWS1pi2f8gpotLxtWgT9UtGuPUcTeEPeayDnfA8xU/FtnJevG/+rSVvZaGjxENomyTcJxclezCDRpgQoodEA"
    "bnU6cBK0l6tJwpQ8wDHAW6MmRQlQPLq5DbiWwVQ6Tscn2fi60MVM3e8DDmSYixA4n0iaXQlQXN36wHslzH0k4hck2fgisJNhnZRj"
    "rY9wNfBc4Djg+RJ+xqWAp+TvpwCb3YhAq1iUs7eBxO1bRbV2SF8fYLObm4Cr4rxx5/x7HAHPZ9zPQdEAdgXyVUKKIEWDfRT4rdVM"
    "SoDydteXzt9bMDQmxixY4iySmP2QfOcFGZra5mbsCP8eZpo+LuSzJH2jaIy/A74SoLwm6Mc4YFkaYEnGeWckXMsberoayceklb8J"
    "fIrBkj4Xdir/PPEHptQHGJ4IgZPPSMt15J0k6jmtiAMZCFGuFg0yFXO8/dtZmJdk+0qAyUMnhxOYFqX8C/gh8Ytq7N9WAO8CQiXA"
    "eLRGlQ5pnLm4kuQUsk0MvQ+YVQKMVui7qW7iy8PMpEZtvIdZWX1zghbwHQdzixJgtEmkuzGZRB8zAVSmKOW8mIcDwI8dwUdzO9ty"
    "OJAfhuzp4LfLBWcxkxYd4KlkTwfHLSlfyLCCeR5wL8NNHR9iME3vJ2iHaWCXE7HEThfnCQP3OV6pxR60GHIZLeCJ8E/BlJTdyOBl"
    "mTzoYRbPfEu0SdJSL/sm1nbgyymJp5lODsZ+BDjDSSSEog2WZagYRbzatQmkyyvQKEGGz/GPLBl1MpwMKLayR5FfE0yV1KJegZzC"
    "dJ6YMwtJL0NoFnE4TdAb0XWGJoA6cQvAM1UoARQLEXlMQNJ6dDUNC4QAqiUWKAHs/PZdwH9jRv+mPGGGorkEsEWdPwH8MoYAuzHl"
    "2VtTKkUJEI8lYgamHH9gmQp9YTmBNntlCaDFkDUMVCgBFEoAhRJAoQRQKAEUSgCFEkChBFAoARRKAEUzoAs7x4syE2phUwhgiygU"
    "rSjetpqBSZq3bEn8Isd64yTAHOWrXFvTFLRU+O5zzVCsqng/4Txxwp8fJwGejSlg1CnAdFs82RZfatvum24B6I9javguIXtRTegI"
    "9D5M8eifp5DAVizZkMdsVF0r2D2+K5ogb+sCjwO/wGwz2yY/xWq1V2De7B22tvAFjlyiwvcw9YgeIP3l0IN1EmDYth94W8y1m+zw"
    "zTJ4Y7dL+dfD7e9xRaTsgDk7Isc42d5YNwGCks2txH1RxKlsIuwoPTljRBbdZe3CGC1p+2mH9GUvQS4h8PqsDk2yTV4B1pdpHedG"
    "twJfZ7AmscnvI6ysMMoJgVUxRAuB04CXEF8mxvpUtwM3+cCTKTfkWTsRQZfDa9jXpTI9YfC5mO3rVssDNNkv8Go8j5XFxzKiKA/4"
    "ChD4wB0xIYNlySHgzoizOCWk+bMjoDo7y+7XdxrwO2C9fG5rEqtPuTJxdvSfAJwuv3diwsgpcQ6vtyTaxKAyZdSmXxzjaVpf4KSY"
    "44ZpvQx/wtq9x4E3O7avCc6h7b8zUhyzMj7AVqcf7DW2k7yjif3bp6O+wysxlaXsjT3ghBl+SkizWWxJldun9HP+74IGOYd5CfCk"
    "DLoPYTZ7ujehT2x/XybnXiQ/18gACWIGk/3bfsxeRB5SKtbHFA8+GbMx8mLgbwzKj6cVHr4FU+/meOI3mCySHFmPqWczIw+cVuMu"
    "xGx5eyymhE2/4Ukj62x3gSsYbKC5RZ4xTMm29p3nPhs4KsFEWt/p+5i3ug7rLz+FtXmSG1VhM/Ag2ZsyueHNDcDRE540ytIAgZP7"
    "eCaDSqG3Jnzffv62DNyNwMswm3kHCVrU9tl6BiVqjnC4/BJJF/e4YZp90XQdZhu1PDtz2f/vEu01qSQoQoA1znG3VOQzuIOljoFb"
    "GazwlgLXOTefxzncgymFPonOYZ0EiDrTab7TGwpo97HnzMFsoxamqLUowwNMGXR7ns6EtFn5eeYYNIAdQDsbFDUd5tmfI85OVkf0"
    "HZJsm9AHffmYCGCLQx9hIifVaQqd+/sG8E/gO9I5SUkg33ng8zF76PyE7HnzUWm1vuOn5CXnoSHv3b7V/TDwXcovQpkIv+BYzARH"
    "HudwWKdp1M3VAKudZ7/QyQ+USa7ZNP8lTbD9eUiwHFMh25IgyCDB/IS1XgEC+PK8O4Yk105MQQ+fhk+pu87hF3M6h03WAHa0rsbs"
    "U/gfh0RZbQ4zXX+t41N4Sc5Wk+A52ckPYGa0plIyh03LBB4QU/eoIxvrD63ETP/mkVkg59jr9FtrFtp6jkk4XUZGHdu5j7LZCOYh"
    "BjuLuZtRliV3G1ZSZfoFxzHYMdOqyH7DmnXWrklx1txl9nnagijiZUmwAvhZw/2AXZgNH0c6u9kGlrhx/nmYrWrWUN3mTHXnOg4A"
    "vwYuBR4btb1ui5qIdtp0g+57LuU5FAU7s6lOz9ju22sxGZoUAioUCoVCoVAoFAqFQqFQKBQKhUKhUCgU1eP/+W52OWpkmYoAAAAA"
    "SUVORK5CYII="
)


def _make_engine_icon(size: int = NAV_ICON_SIZE, color: QColor | None = None) -> QIcon:
    """The standard automotive 'check engine' dashboard warning light
    glyph (embedded PNG artwork, recolored at paint time), rather than a
    hand-drawn approximation. Recoloring uses CompositionMode_SourceIn:
    draw the source artwork, then fill with the target color -- the fill
    only lands where the artwork's own alpha is non-zero, so its exact
    silhouette (including antialiased edges) is preserved, just tinted
    to whatever _icon_color() says for the current light/dark theme."""
    color = color or _icon_color()

    src = QPixmap()
    src.loadFromData(base64.b64decode(ENGINE_ICON_PNG_B64), "PNG")
    src = src.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )

    result = QPixmap(src.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, src)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), color)
    painter.end()

    return QIcon(result)


class ToggleSwitch(QAbstractButton):
    """A real sliding toggle switch: grey track/knob when off, green track
    with the knob animated to the right when on. Qt's QSS has no distinct
    'knob' subcontrol for QCheckBox, so this is custom-painted rather than
    style-sheet based."""

    TRACK_OFF_COLOR = QColor("#bbbbbb")
    TRACK_ON_COLOR = QColor("#4cd964")
    BORDER_COLOR = QColor("#999999")
    KNOB_COLOR = QColor("#ffffff")
    SYMBOL_OFF_COLOR = QColor("#999999")  # grey X
    SYMBOL_ON_COLOR = QColor("#4cd964")   # green check

    # Emitted instead of toggling while the switch is unavailable. Not done
    # via setEnabled(False): a disabled widget gets no clicks, so it could
    # not explain why it can't be switched on.
    unavailableClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(58, 32)
        self.unavailable = False

        self._knob_pos = 0.0  # 0.0 = left/off, 1.0 = right/on
        self._hovered = False
        self._animation = QPropertyAnimation(self, b"knobPos", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate_to_state)

    def set_unavailable(self, unavailable: bool):
        self.unavailable = unavailable
        self.setCursor(Qt.CursorShape.ArrowCursor if unavailable else Qt.CursorShape.PointingHandCursor)
        self.update()

    def mousePressEvent(self, event):
        if self.unavailable:
            event.accept()  # swallow; the release reports it
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.unavailable:
            if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
                self.unavailableClicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _animate_to_state(self, checked: bool):
        self._animation.stop()
        self._animation.setStartValue(self._knob_pos)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, value: float):
        self._knob_pos = value
        self.update()

    knobPos = pyqtProperty(float, _get_knob_pos, _set_knob_pos)

    @staticmethod
    def _blend(c1: QColor, c2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.unavailable:
            painter.setOpacity(0.4)  # looks disabled, but still gets clicks/tooltips

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2

        hovered = self._hovered and not self.unavailable
        track_off = self.TRACK_OFF_COLOR.darker(120) if hovered else self.TRACK_OFF_COLOR
        painter.setPen(self.BORDER_COLOR)
        painter.setBrush(self._blend(track_off, self.TRACK_ON_COLOR, self._knob_pos))
        painter.drawRoundedRect(rect, radius, radius)

        knob_diameter = rect.height() - 4
        travel = rect.width() - knob_diameter - 4
        knob_x = rect.left() + 2 + self._knob_pos * travel
        knob_y = rect.top() + 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.KNOB_COLOR)
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_diameter, knob_diameter))

        center_x = knob_x + knob_diameter / 2
        center_y = knob_y + knob_diameter / 2
        symbol_size = knob_diameter * 0.5
        pen_width = max(1.5, knob_diameter * 0.14)

        if self._knob_pos < 1.0:
            color = QColor(self.SYMBOL_OFF_COLOR)
            color.setAlpha(int(255 * (1.0 - self._knob_pos)))
            painter.setPen(QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            half = symbol_size / 2
            painter.drawLine(
                QPointF(center_x - half, center_y - half), QPointF(center_x + half, center_y + half)
            )
            painter.drawLine(
                QPointF(center_x - half, center_y + half), QPointF(center_x + half, center_y - half)
            )

        if self._knob_pos > 0.0:
            color = QColor(self.SYMBOL_ON_COLOR)
            color.setAlpha(int(255 * self._knob_pos))
            pen = QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(center_x - symbol_size * 0.45, center_y + symbol_size * 0.05)
            path.lineTo(center_x - symbol_size * 0.1, center_y + symbol_size * 0.4)
            path.lineTo(center_x + symbol_size * 0.45, center_y - symbol_size * 0.35)
            painter.drawPath(path)


class ModeSwitch(QAbstractButton):
    """Wide View/Build switch: grey track (inactive background); the
    knob itself is the colored element, sliding between green (View,
    the default) and red (Build). Both labels are always visible, with
    only font weight (bold vs light) distinguishing the selected side,
    per spec. Sized to fill whatever width its layout slot gives it (see
    MainWindow: it spans the same two grid columns as the start/back
    buttons), not a fixed pixel width."""

    TRACK_COLOR = QColor("#bbbbbb")       # grey: inactive background
    KNOB_OFF_COLOR = QColor("#40a040")    # green: View
    KNOB_ON_COLOR = QColor("#a04040")     # red: Build

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._knob_pos = 0.0  # 0.0 = left/View, 1.0 = right/Build
        self._hovered = False
        self._animation = QPropertyAnimation(self, b"knobPos", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate_to_state)

    def _animate_to_state(self, checked: bool):
        self._animation.stop()
        self._animation.setStartValue(self._knob_pos)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, value: float):
        self._knob_pos = value
        self.update()

    knobPos = pyqtProperty(float, _get_knob_pos, _set_knob_pos)

    @staticmethod
    def _blend(c1: QColor, c2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2

        track_color = self.TRACK_COLOR.darker(120) if self._hovered else self.TRACK_COLOR
        painter.setPen(track_color.darker(115))
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        half_w = rect.width() / 2
        margin = 3.0
        knob_rect = QRectF(
            rect.left() + margin + self._knob_pos * half_w,
            rect.top() + margin,
            half_w - 2 * margin,
            rect.height() - 2 * margin,
        )
        knob_color = self._blend(self.KNOB_OFF_COLOR, self.KNOB_ON_COLOR, self._knob_pos)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawRoundedRect(knob_rect, knob_rect.height() / 2, knob_rect.height() / 2)

        bold_font = QFont(self.font())
        bold_font.setPixelSize(NAV_ICON_SIZE)
        bold_font.setBold(True)
        light_font = QFont(self.font())
        light_font.setPixelSize(NAV_ICON_SIZE)
        light_font.setBold(False)
        light_font.setWeight(QFont.Weight.Light)

        view_rect = QRectF(rect.left(), rect.top(), half_w, rect.height())
        build_rect = QRectF(rect.left() + half_w, rect.top(), half_w, rect.height())
        view_selected = self._knob_pos < 0.5

        painter.setPen(_icon_color())
        painter.setFont(bold_font if view_selected else light_font)
        painter.drawText(view_rect, Qt.AlignmentFlag.AlignCenter, "View")
        painter.setFont(light_font if view_selected else bold_font)
        painter.drawText(build_rect, Qt.AlignmentFlag.AlignCenter, "Build")


# Mode board color schemes: {"square light": ..., "square dark": ...}
BOARD_COLORS = {
    "BUILD": {"square light": "#f2a4a4", "square dark": "#a04040"},    # light / dark red
    # Lichess' blue-grey board; the previous move is its translucent
    # yellow-green (rgba(155, 199, 0, 0.41)) laid over the square color
    "VIEW": {
        "square light": "#d2d7db",
        "square dark": "#7b949d",
        "square light lastmove": "#bbd081",
        "square dark lastmove": "#88a95d",
    },
}

PROMO_TO_CODE = {None: 0, chess.KNIGHT: 1, chess.BISHOP: 2, chess.ROOK: 3, chess.QUEEN: 4}
CODE_TO_PROMO = {v: k for k, v in PROMO_TO_CODE.items()}


# --------------------------------------------------------------------------
# Polyglot book: minimal self-contained reader/writer keyed on Zobrist hash.
# --------------------------------------------------------------------------

@dataclass
class BookEntry:
    key: int
    from_square: int
    to_square: int
    promotion: int  # polyglot code 0-4
    weight: int
    learn: int
    resulting_key: int | None = None  # cache: hash of the position after this move.
        # Not part of the Polyglot file format -- computed once, either at
        # creation time (we already have a real board then) or backfilled
        # by walking the book once after loading from disk.


def encode_move(board: chess.Board, move: chess.Move) -> tuple[int, int, int]:
    """Move -> (from_square, to_square, promotion_code) in Polyglot's own
    encoding, where castling is king-captures-own-rook."""
    to_square = move.to_square
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        to_square = chess.square(7 if board.is_kingside_castling(move) else 0, rank)
    return move.from_square, to_square, PROMO_TO_CODE[move.promotion]


def decode_move(board: chess.Board, entry: BookEntry) -> chess.Move | None:
    """BookEntry -> legal chess.Move on the given board, or None if it no
    longer applies. Undoes Polyglot's king-captures-rook castling quirk."""
    promo = CODE_TO_PROMO.get(entry.promotion)
    move = chess.Move(entry.from_square, entry.to_square, promotion=promo)
    if move in board.legal_moves:
        return move
    piece = board.piece_at(entry.from_square)
    if piece and piece.piece_type == chess.KING:
        rank = chess.square_rank(entry.from_square)
        if entry.to_square == chess.square(7, rank):
            alt = chess.Move(entry.from_square, chess.square(6, rank))
            if alt in board.legal_moves:
                return alt
        if entry.to_square == chess.square(0, rank):
            alt = chess.Move(entry.from_square, chess.square(2, rank))
            if alt in board.legal_moves:
                return alt
    return None


def _settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def _default_book_path() -> str:
    """book.bin in the per-user data folder, which is always writable (an
    installed copy's own folder, e.g. under Program Files, is not):
    Linux ~/.local/share/GambitGear/OTB, Windows %APPDATA%\\GambitGear\\OTB,
    macOS ~/Library/Application Support/GambitGear/OTB.
    Inside a Snap or Flatpak that folder is a private one of the sandbox,
    hidden from the user, so books go to Documents/OTB there instead."""
    folder = _sandbox_documents_dir()
    if folder is not None:
        folder = os.path.join(folder, "OTB")
    else:
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "book.bin")


def _sandbox_documents_dir() -> str | None:
    """The user's real Documents folder when running inside a Snap or a
    Flatpak, None otherwise. A Snap replaces HOME with a folder of its own
    (the real one is in SNAP_REAL_HOME); a Flatpak keeps it. The folder's
    name depends on the language (e.g. "Dokumente"): it is read from
    ~/.config/user-dirs.dirs if the sandbox lets OTB read that file."""
    if os.environ.get("SNAP"):
        home = os.environ.get("SNAP_REAL_HOME") or os.path.expanduser("~")
    elif os.environ.get("FLATPAK_ID"):
        home = os.path.expanduser("~")
    else:
        return None
    name = "Documents"
    try:
        with open(os.path.join(home, ".config", "user-dirs.dirs"), encoding="utf-8") as f:
            for line in f:
                match = re.match(r'\s*XDG_DOCUMENTS_DIR="\$HOME/([^"]+)"', line)
                if match:
                    name = match.group(1)
    except OSError:
        pass
    return os.path.join(home, name)


def _desktop_file_name() -> str:
    """Name of the launcher (desktop file, without .desktop) that belongs to
    this OTB. The desktop uses it to connect the window to that launcher, so
    a pinned OTB icon is the one that lights up instead of a second, generic
    one appearing next to it."""
    if os.environ.get("FLATPAK_ID"):
        return os.environ["FLATPAK_ID"]  # ch.gambitgear.OTB
    if os.environ.get("SNAP_NAME"):
        # snapd installs the launcher as <snap>_<app>.desktop; the app is named like the snap
        return f"{os.environ['SNAP_NAME']}_{os.environ['SNAP_NAME']}"
    return "otb"  # running from source: a launcher made by hand (otb.desktop)


def _migrate_old_settings() -> None:
    """One-time copy of the settings stored under the app's former name
    (ChessRepertoire/ChessRepertoireApp). Before the data folder existed,
    the default book was ./book.bin -- keep using it if it is there, so an
    existing book doesn't seem to vanish."""
    new = _settings()
    if new.value("migrated_old_settings", False, type=bool):
        return
    old = QSettings("ChessRepertoire", "ChessRepertoireApp")
    for key in old.allKeys():
        if not new.contains(key):
            new.setValue(key, old.value(key))
    if not new.contains("book_path") and os.path.exists("book.bin"):
        new.setValue("book_path", os.path.abspath("book.bin"))
    new.setValue("migrated_old_settings", True)


# The Polyglot format has no header, so the repertoire color is stored in a
# marker entry with key 0. Engines and GUIs look entries up by the hash of a
# real position, which is never 0, so they ignore it; sorted by key it is the
# first entry of the file. Its weight field holds the color, its learn field
# a magic value telling it apart from other tools' key-0 entries.
COLOR_MARKER_MAGIC = 0x4F544231  # "OTB1"
BOOK_COLORS = {1: "White", 2: "Black", 3: "Both"}  # marker weight -> color
BOOK_COLOR_PREFIXES = {"White": "W_", "Black": "B_", "Both": "WB_"}  # file name prefix of new books


def load_book(path: str) -> tuple[list[BookEntry], str | None]:
    """Returns the entries and the repertoire color ("White", "Black",
    "Both"), or None if the book has no color marker."""
    entries: list[BookEntry] = []
    color = None
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return entries, color
    for offset in range(0, len(data) - 15, 16):
        key, mv, weight, learn = struct.unpack_from(">QHHI", data, offset)
        if key == 0 and learn == COLOR_MARKER_MAGIC:
            color = BOOK_COLORS.get(weight)
            continue
        to_sq = mv & 0x3F
        from_sq = (mv >> 6) & 0x3F
        promo = (mv >> 12) & 0x7
        entries.append(BookEntry(key, from_sq, to_sq, promo, weight, learn))
    return entries, color


def _pack_entry(e: BookEntry) -> bytes:
    return struct.pack(">QHHI", e.key, (e.promotion << 12) | (e.from_square << 6) | e.to_square, e.weight, e.learn)


def save_book(path: str, entries: list[BookEntry], color: str | None = None) -> None:
    ordered = sorted(entries, key=lambda e: e.key)
    marker = b""
    if color is not None:
        weight = next(w for w, name in BOOK_COLORS.items() if name == color)
        marker = struct.pack(">QHHI", 0, 0, weight, COLOR_MARKER_MAGIC)
    data = marker + b"".join(map(_pack_entry, ordered))
    with open(path, "wb") as f:
        f.write(data)


def patch_book(path: str, entry: BookEntry, is_new: bool, records_before: int) -> bool:
    """Writes one new entry or one changed weight into the book file without
    re-packing the whole book, leaving the file exactly as save_book would.
    records_before is the number of 16-byte records the file must hold; if
    it doesn't, or the file isn't sorted as expected, nothing is written and
    False is returned -- the caller then falls back to save_book."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    if len(data) != records_before * 16:
        return False

    def key_at(i: int) -> int:
        return struct.unpack_from(">Q", data, i * 16)[0]

    def bisect(after_equal: bool) -> int:
        lo, hi = 0, records_before
        while lo < hi:
            mid = (lo + hi) // 2
            if key_at(mid) < entry.key or (after_equal and key_at(mid) == entry.key):
                lo = mid + 1
            else:
                hi = mid
        return lo

    record = _pack_entry(entry)
    end = bisect(after_equal=True)  # a stable sort puts a new entry last among its key
    if is_new:
        with open(path, "wb") as f:
            f.write(data[:end * 16] + record + data[end * 16:])
        return True
    for i in range(bisect(after_equal=False), end):
        if data[i * 16:i * 16 + 10] == record[:10]:  # same key and move
            with open(path, "r+b") as f:
                f.seek(i * 16)
                f.write(record)
            return True
    return False


# --------------------------------------------------------------------------
# Engine analysis: runs on a background thread, capped to a few seconds
# and 1 thread/light hash per position to keep system load down.
# --------------------------------------------------------------------------

class EngineWorker(QObject):
    best_move_found = pyqtSignal(int, int)  # from_square, to_square
    evaluation_updated = pyqtSignal(str)    # e.g. "+0.35 (18)", "-1.20 (22)", "+M3 (30)" -- (search depth)
    error = pyqtSignal(str)

    def __init__(self, engine_path: str):
        super().__init__()
        self.engine_path = engine_path
        self._engine: chess.engine.SimpleEngine | None = None
        self._analysis = None
        self._thread: threading.Thread | None = None

    def start(self, board: chess.Board):
        """Stop any running analysis and start analysing `board` forever."""
        self.stop()
        self._thread = threading.Thread(target=self._run, args=(board.copy(),), daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the current analysis (if any) and wait for the thread to exit."""
        if self._analysis is not None:
            try:
                self._analysis.stop()
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def quit_engine(self):
        self.stop()
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    ANALYSIS_TIME_LIMIT = 4.0  # seconds of thinking per position
    THREADS = 1                # keep CPU load light
    HASH_MB = 32                # keep memory footprint light

    @staticmethod
    def _format_score(score: chess.engine.PovScore) -> str:
        """Evaluation from White's point of view, always with an explicit
        sign: '+0.35' / '-1.20' in pawns, or '+M3' / '-M3' for forced mate."""
        white = score.white()
        if white.is_mate():
            mate = white.mate()
            if mate == 0:
                return "M0"
            return f"{'+' if mate > 0 else '-'}M{abs(mate)}"
        return f"{white.score() / 100:+.2f}"

    def _run(self, board: chess.Board):
        try:
            if self._engine is None:
                # Windows: the engine is a console program; without this flag
                # it opens its own console window next to OTB (a --windowed
                # app has no console to share). No-op elsewhere.
                popen_args = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
                self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path, **popen_args)
                self._engine.configure({"Threads": self.THREADS, "Hash": self.HASH_MB})
            limit = chess.engine.Limit(time=self.ANALYSIS_TIME_LIMIT)
            with self._engine.analysis(board, limit) as analysis:
                self._analysis = analysis
                for info in analysis:
                    score = info.get("score")
                    if score is not None:
                        text = self._format_score(score)
                        depth = info.get("depth")
                        if depth is not None:
                            text += f" ({depth})"
                        self.evaluation_updated.emit(text)
                    pv = info.get("pv")
                    if pv:
                        move = pv[0]
                        self.best_move_found.emit(move.from_square, move.to_square)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self._analysis = None


# --------------------------------------------------------------------------
# Board widget: drag-and-drop, legal-squares-only, square highlights.
# --------------------------------------------------------------------------

class BoardWidget(QWidget):
    def __init__(self, get_board, get_mode, on_move):
        super().__init__()
        self.get_board = get_board
        self.get_mode = get_mode
        self.on_move = on_move

        self.hover_arrow: tuple[int, int] | None = None
        self.engine_arrow: tuple[int, int] | None = None
        self.orientation: bool = chess.WHITE

        self.selected: int | None = None
        self.hover_square: int | None = None
        self.dragging = False
        self.press_pos: QPoint | None = None
        self.drag_label: QSvgWidget | None = None
        self._drag_label_size = 0

        # Piece animation: while it runs, the gliding pieces are left out of
        # the board image and painted on top of it at their current spot.
        self._shown_pieces: dict[int, chess.Piece] | None = None  # position last handed to animate_to_position
        self._gliding: list[tuple[chess.Piece, int, int]] = []    # piece, from square, to square
        self._glide_cover: dict[int, chess.Piece | None] = {}     # what the target squares show meanwhile
        self._glide_progress = 1.0
        self._dropped_square: int | None = None  # a piece dragged here is already in place
        self._piece_renderers: dict[str, QSvgRenderer] = {}
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(ANIMATION_SPEEDS_MS[DEFAULT_ANIMATION_SPEED])
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)  # as Lichess (chessground)
        self._animation.valueChanged.connect(self._on_glide_step)
        self._animation.finished.connect(self._end_glide)

        self._target_marks: dict[int, bool] = {}  # see redraw
        # drawn with the right mouse button: (from square, to square); the
        # same square twice is a circle
        self._user_shapes: list[tuple[int, int]] = []
        self._drawing_shape: tuple[int, int] | None = None  # while the button is held
        self.coordinates = DEFAULT_COORDINATES  # a COORDINATE_MODES key
        self.renderer = QSvgRenderer()
        self.setMinimumSize(MIN_BOARD_SIZE, MIN_BOARD_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.redraw()

    def set_hover_arrow(self, arrow: tuple[int, int] | None):
        if arrow == self.hover_arrow:
            return
        self.hover_arrow = arrow
        self.redraw()

    def set_engine_arrow(self, arrow: tuple[int, int] | None):
        if arrow == self.engine_arrow:
            return
        self.engine_arrow = arrow
        self.redraw()

    def flip(self):
        self.orientation = not self.orientation
        self.redraw()

    def animate_to_position(self):
        """Call when the position on the board has changed, before anything
        redraws: lets the pieces glide from where they were shown to their
        new squares. Works out what moved by comparing the two positions (as
        Lichess does), so it covers single moves in both directions, castling
        and jumps over several moves alike."""
        old, new = self._shown_pieces, self.get_board().piece_map()
        self._shown_pieces = new
        dropped, self._dropped_square = self._dropped_square, None
        self._end_glide(redraw=False)
        if old is None or old == new:
            return
        self._user_shapes = []  # hand-drawn arrows belong to the position they were drawn on
        self._drawing_shape = None
        # pieces that left their square, and squares that got a different piece
        left = {sq: piece for sq, piece in old.items() if new.get(sq) != piece}
        for sq, piece in new.items():
            if old.get(sq) == piece or sq == dropped:
                continue
            origins = [origin for origin, other in left.items() if other == piece]
            if not origins:
                continue  # no such piece left a square (e.g. a promotion): it just appears
            origin = min(origins, key=lambda o: chess.square_distance(o, sq))
            del left[origin]
            self._gliding.append((piece, origin, sq))
            # until the piece arrives, its square shows what stood there (a captured piece)
            self._glide_cover[sq] = old.get(sq)
        if self._gliding:
            self._glide_progress = 0.0
            self._animation.start()

    def _on_glide_step(self, progress):
        self._glide_progress = float(progress)
        self.update()

    def _end_glide(self, redraw: bool = True):
        self._animation.stop()
        if self._gliding:
            self._gliding = []
            self._glide_cover = {}
            if redraw:
                self.redraw()

    def _square_rect(self, file: float, rank: float) -> QRectF:
        """Screen rectangle of a (possibly fractional) square position."""
        rect = self.board_rect()
        size = rect.width() / 8.0
        col, row = (file, 7 - rank) if self.orientation == chess.WHITE else (7 - file, rank)
        return QRectF(rect.left() + col * size, rect.top() + row * size, size, size)

    def set_animation_speed(self, speed: str):
        self._animation.setDuration(ANIMATION_SPEEDS_MS[speed])

    def set_coordinates(self, mode: str):
        self.coordinates = mode
        self.update()

    def _coordinate_margin(self) -> float:
        """Width of the strip left of and below the squares that holds the
        coordinates in "outside" mode."""
        if self.coordinates != "outside":
            return 0.0
        ratio = self.devicePixelRatioF()
        return round(max(14.0, min(self.width(), self.height()) * 0.04) * ratio) / ratio  # whole pixels

    def board_rect(self) -> QRectF:
        """The area covered by the 64 squares. Its side is a multiple of 8
        screen pixels, so every square edge falls exactly between two pixels:
        on a half-covered pixel the renderer blends in the dark background,
        which shows as dark lines between the squares, most of all around a
        highlighted one."""
        w = float(self.width())
        h = float(self.height())
        margin = self._coordinate_margin()
        ratio = self.devicePixelRatioF()
        side = math.floor((min(w, h) - margin) * ratio / 8) * 8 / ratio
        return QRectF(margin, 0.0, side, side)

    def _paint_arrow(self, painter: QPainter, arrow: tuple[int, int], color: QColor, width: float):
        """Arrow in Lichess' proportions; width: of the shaft, in squares."""
        side = self.board_rect().width() / 8.0
        start, end = (
            self._square_rect(chess.square_file(square), chess.square_rank(square)).center()
            for square in arrow
        )
        length = math.hypot(end.x() - start.x(), end.y() - start.y())
        if length == 0:
            return
        along = QPointF((end.x() - start.x()) / length, (end.y() - start.y()) / length)
        across = QPointF(-along.y(), along.x())
        width *= side
        shaft_end = end - along * (side * ENGINE_ARROW_MARGIN)
        # the head's base lies 2.05 shaft widths before the shaft's end, its tip 0.95 after it
        base = shaft_end - along * (2.05 * width)
        tip = shaft_end + along * (0.95 * width)

        shaft = QPainterPath(start)
        shaft.lineTo(shaft_end)
        stroker = QPainterPathStroker()
        stroker.setWidth(width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        head = QPainterPath()
        head.addPolygon(QPolygonF([base + across * (2 * width), tip, base - across * (2 * width)]))
        head.closeSubpath()
        # united, so that a translucent color isn't doubled where shaft and head overlap
        painter.fillPath(stroker.createStroke(shaft).united(head), color)

    def _paint_hover_arrow(self, painter: QPainter):
        side = self.board_rect().width() / 8.0
        start, end = (
            self._square_rect(chess.square_file(square), chess.square_rank(square)).center()
            for square in self.hover_arrow
        )
        length = math.hypot(end.x() - start.x(), end.y() - start.y())
        if length == 0:
            return
        along = QPointF((end.x() - start.x()) / length, (end.y() - start.y()) / length)
        across = QPointF(-along.y(), along.x())
        tip = end - along * (side * HOVER_ARROW_MARGIN)
        base = tip - along * (side * HOVER_ARROW_HEAD)
        painter.setPen(QPen(HOVER_ARROW_COLOR, side * HOVER_ARROW_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(start, base)
        half = across * (side * HOVER_ARROW_HEAD / 2)
        head = QPainterPath()
        head.addPolygon(QPolygonF([tip, base + half, base - half]))
        head.closeSubpath()
        painter.fillPath(head, HOVER_ARROW_COLOR)

    def _paint_user_shapes(self, painter: QPainter):
        side = self.board_rect().width() / 8.0
        shapes = [(shape, False) for shape in self._user_shapes]
        if self._drawing_shape is not None:
            shapes.append((self._drawing_shape, True))
        for (origin, target), in_progress in shapes:
            painter.setOpacity(0.9 if in_progress else 1.0)
            scale = 0.85 if in_progress else 1.0  # slightly lighter while the button is held, as on Lichess
            if origin == target:
                ring = side * USER_CIRCLE_WIDTH * scale
                rect = self._square_rect(chess.square_file(origin), chess.square_rank(origin))
                painter.setPen(QPen(USER_SHAPE_COLOR, ring))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                radius = side / 2 - ring / 2
                painter.drawEllipse(rect.center(), radius, radius)
            else:
                self._paint_arrow(painter, (origin, target), USER_SHAPE_COLOR, USER_ARROW_WIDTH * scale)
        painter.setOpacity(1.0)

    def _paint_coordinates(self, painter: QPainter):
        if self.coordinates == "off":
            return
        rect = self.board_rect()
        side = rect.width() / 8.0
        white_down = self.orientation == chess.WHITE
        files = "abcdefgh" if white_down else "hgfedcba"
        ranks = "87654321" if white_down else "12345678"
        font = QFont(self.font())
        font.setBold(self.coordinates == "inside")  # the small corner letters need the weight
        painter.save()
        if self.coordinates == "outside":
            margin = self._coordinate_margin()
            font.setPixelSize(max(9, round(margin * 0.7)))
            painter.setFont(font)
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            for i in range(8):
                painter.drawText(QRectF(0, rect.top() + i * side, margin, side), Qt.AlignmentFlag.AlignCenter, ranks[i])
                painter.drawText(
                    QRectF(rect.left() + i * side, rect.bottom(), side, margin), Qt.AlignmentFlag.AlignCenter, files[i]
                )
        else:
            # as on Lichess: ranks in the top right corner of the right-hand
            # squares, files in the bottom left corner of the bottom squares,
            # each in the color of the other kind of square
            colors = BOARD_COLORS.get(self.get_mode(), BOARD_COLORS["VIEW"])
            light, dark = QColor(colors["square light"]), QColor(colors["square dark"])
            # sizes and distances measured on a Lichess board, as fractions of a square
            font.setPixelSize(max(8, round(side * 0.22)))
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            for i in range(8):
                # the top right and the bottom left square are dark whichever
                # side is at the bottom; from there the colors alternate
                painter.setPen(dark if i % 2 == 1 else light)
                # rank: top of the digit 0.09 below the square's top, 0.05 from its right edge
                painter.drawText(
                    QPointF(
                        rect.right() - side * 0.05 - metrics.horizontalAdvance(ranks[i]),
                        rect.top() + i * side + side * 0.09 + metrics.capHeight(),
                    ),
                    ranks[i],
                )
                # file: the letter stands 0.06 above the square's bottom, 0.07 from its left edge
                painter.drawText(QPointF(rect.left() + i * side + side * 0.07, rect.bottom() - side * 0.06), files[i])
        painter.restore()

    def redraw(self):
        board = self.get_board()
        mode = self.get_mode()
        colors = BOARD_COLORS.get(mode, BOARD_COLORS["VIEW"])
        display_board = board
        fill = {}
        self._target_marks = {}

        if self.selected is not None:
            # a piece is actually selected (clicked): show it and where it can go
            piece = board.piece_at(self.selected)
            if piece is not None and piece.color == board.turn:
                fill[self.selected] = SELECTED_SQUARE_COLOR
                # painted over the board in paintEvent; True = capture
                self._target_marks = {
                    target: board.piece_at(target) is not None
                    for target in self._legal_targets(board, self.selected)
                }
        elif self.hover_square is not None:
            # merely hovering: highlight the start square only, no targets
            piece = board.piece_at(self.hover_square)
            if piece is not None and piece.color == board.turn:
                fill[self.hover_square] = DRAG_SOURCE_COLOR

        if self.selected is not None and self.dragging:
            display_board = board.copy()
            display_board.remove_piece_at(self.selected)
        if self._gliding:
            display_board = display_board.copy()
            for square, piece in self._glide_cover.items():
                display_board.set_piece_at(square, piece)  # None removes

        # the arrows are painted over the board in paintEvent

        lastmove = board.move_stack[-1] if board.move_stack else None
        svg_data = chess.svg.board(
            board=display_board,
            lastmove=lastmove,
            fill=fill,
            colors=colors,
            orientation=self.orientation,
            coordinates=False,
            check=board.king(board.turn) if board.is_check() else None,
        )

        self.renderer.load(svg_data.encode("utf-8"))
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.renderer.render(painter, self.board_rect())
        self._paint_coordinates(painter)
        for square, is_capture in self._target_marks.items():
            rect = self._square_rect(chess.square_file(square), chess.square_rank(square))
            side = rect.width()
            mark = QPainterPath()
            if is_capture:
                circle = QPainterPath()
                circle.addEllipse(rect.center(), side * TARGET_CAPTURE_RADIUS, side * TARGET_CAPTURE_RADIUS)
                mark.addRect(rect)
                mark = mark.subtracted(circle)
            else:
                mark.addEllipse(rect.center(), side * TARGET_DOT_RADIUS, side * TARGET_DOT_RADIUS)
            painter.fillPath(mark, TARGET_CAPTURE_COLOR if is_capture else TARGET_MARK_COLOR)
        # the thin hover arrow goes on top, so both stay visible when the
        # hovered book move is the engine's move
        if self.engine_arrow is not None:
            self._paint_arrow(painter, self.engine_arrow, ENGINE_ARROW_COLOR, ENGINE_ARROW_WIDTH)
        if self.hover_arrow is not None:
            self._paint_hover_arrow(painter)
        self._paint_user_shapes(painter)
        t = self._glide_progress
        for piece, origin, target in self._gliding:
            renderer = self._piece_renderers.get(piece.symbol())
            if renderer is None:
                renderer = QSvgRenderer(chess.svg.piece(piece).encode("utf-8"))
                self._piece_renderers[piece.symbol()] = renderer
            file = chess.square_file(origin) + (chess.square_file(target) - chess.square_file(origin)) * t
            rank = chess.square_rank(origin) + (chess.square_rank(target) - chess.square_rank(origin)) * t
            renderer.render(painter, self._square_rect(file, rank))

    def resizeEvent(self, event):
        self.update()
        super().resizeEvent(event)

    @staticmethod
    def _legal_targets(board: chess.Board, from_square: int) -> list[int]:
        return [m.to_square for m in board.legal_moves if m.from_square == from_square]

    def _square_at(self, pos: QPoint) -> int | None:
        rect = self.board_rect()
        px, py = float(pos.x()), float(pos.y())
        if not (rect.left() <= px <= rect.right() and rect.top() <= py <= rect.bottom()):
            return None
        sq_size = rect.width() / 8.0
        col = int((px - rect.left()) / sq_size)
        row = int((py - rect.top()) / sq_size)

        col = min(7, max(0, col))
        row = min(7, max(0, row))

        if self.orientation == chess.WHITE:
            file, rank = col, 7 - row
        else:
            file, rank = 7 - col, row
        return chess.square(file, rank)

    @staticmethod
    def _build_move(board, from_sq, to_sq):
        piece = board.piece_at(from_sq)
        promotion = None
        if piece is not None and piece.piece_type == chess.PAWN:
            to_rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and to_rank == 7) or (
                piece.color == chess.BLACK and to_rank == 0
            ):
                promotion = chess.QUEEN
        return chess.Move(from_sq, to_sq, promotion=promotion)

    def _start_drag_label(self):
        board = self.get_board()
        piece = board.piece_at(self.selected)
        if piece is None:
            return
        size = max(1, int(self.board_rect().width() / 8.0))
        self._drag_label_size = size
        self.drag_label = QSvgWidget(self)
        self.drag_label.setFixedSize(size, size)
        self.drag_label.load(chess.svg.piece(piece, size=size).encode("utf-8"))
        self.drag_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.drag_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drag_label.show()
        self.drag_label.raise_()

    def _move_drag_label(self, pos: QPoint):
        if self.drag_label is not None:
            half = self._drag_label_size // 2
            self.drag_label.move(pos.x() - half, pos.y() - half)

    def _end_drag_label(self):
        if self.drag_label is not None:
            self.drag_label.deleteLater()
            self.drag_label = None

    def clear_selection(self):
        """Drops a clicked/dragged piece selection. Called whenever the shown
        position changes from outside the board (move list, book list,
        keys, buttons): otherwise the old start square and its targets
        reappear as soon as the same side is to move again."""
        if self.drag_label is not None:
            self._end_drag_label()
        self.selected = None
        self.dragging = False
        self.press_pos = None

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        square = self._square_at(pos)
        if event.button() == Qt.MouseButton.RightButton:
            # start drawing: an arrow if dragged to another square, else a circle
            if square is not None:
                self._drawing_shape = (square, square)
                self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._user_shapes:  # a left-click wipes the drawings, as on Lichess
            self._user_shapes = []
            self.update()
        if square is None:
            return
        board = self.get_board()

        if self.selected is not None:
            if square == self.selected:
                self.selected = None
                self.press_pos = None
                self.redraw()
                return
            move = self._build_move(board, self.selected, square)
            if move in board.legal_moves:
                self.selected = None
                self.press_pos = None
                self.on_move(move)
                return

        piece = board.piece_at(square)
        if piece is not None and piece.color == board.turn:
            self.selected = square
            self.dragging = False
            self.press_pos = pos
            self.redraw()
        else:
            self.selected = None
            self.redraw()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        sq = self._square_at(pos)
        if self._drawing_shape is not None:
            if sq is not None and sq != self._drawing_shape[1]:
                self._drawing_shape = (self._drawing_shape[0], sq)
                self.update()
            return
        if sq != self.hover_square:
            self.hover_square = sq
            if self.selected is None:
                self.redraw()

        if self.selected is None or self.press_pos is None:
            return
        if not self.dragging:
            if (pos - self.press_pos).manhattanLength() < DRAG_THRESHOLD:
                return
            self.dragging = True
            self._start_drag_label()
            self.redraw()
        self._move_drag_label(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            shape, self._drawing_shape = self._drawing_shape, None
            if shape is not None:
                if shape in self._user_shapes:
                    self._user_shapes.remove(shape)  # drawing a shape again removes it
                else:
                    self._user_shapes.append(shape)
                self.update()
            return
        if self.selected is None:
            return
        pos = event.position().toPoint()
        target = self._square_at(pos)
        from_sq = self.selected
        was_dragging = self.dragging
        self.press_pos = None

        if not was_dragging:
            return

        self._end_drag_label()
        self.dragging = False

        if target is not None and target != from_sq:
            move = self._build_move(self.get_board(), from_sq, target)
            if move in self.get_board().legal_moves:
                self.selected = None
                self._dropped_square = target  # dropped by hand: nothing left to glide
                self.on_move(move)
                return
        self.redraw()

    def leaveEvent(self, event):
        if self.hover_square is not None:
            self.hover_square = None
            if self.selected is None:
                self.redraw()
        super().leaveEvent(event)


# --------------------------------------------------------------------------
# Move list with hover tracking
# --------------------------------------------------------------------------

DARK_SEPARATOR_COLOR = QColor("#808080")  # light grey: visible on dark list backgrounds

# Dark mode only: lighter track + clearly lighter handle, since many dark
# themes draw both almost in the list's background color. Applied to the
# scroll bars themselves, so the lists' own look (fonts, headers) is untouched.
DARK_SCROLLBAR_STYLE = """
QScrollBar:vertical { background: #3c3c3c; width: 14px; margin: 0; }
QScrollBar:horizontal { background: #3c3c3c; height: 14px; margin: 0; }
QScrollBar::handle:vertical { background: #8c8c8c; min-height: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:horizontal { background: #8c8c8c; min-width: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:hover { background: #b0b0b0; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


def _separator_color(widget: QWidget, option=None) -> QColor:
    """Row/grid separator color shared by the score sheet and the book list:
    light grey in dark mode (the style's own grid color is barely visible
    there), the style's table grid color otherwise."""
    if widget.palette().color(QPalette.ColorRole.Base).lightness() < 128:
        return DARK_SEPARATOR_COLOR
    if option is None:  # the style answers only with an option (else 0 = transparent)
        option = QStyleOption()
        option.initFrom(widget)
    rgb = widget.style().styleHint(QStyle.StyleHint.SH_Table_GridLineColor, option, widget)
    return QColor.fromRgba(rgb & 0xFFFFFFFF)


class SeparatorFrame(QFrame):
    """1 px outer border around a list, in the same _separator_color() as
    the lines between its rows; replaces the list's own style frame."""

    def __init__(self, inner: QAbstractScrollArea):
        super().__init__()
        self.inner = inner
        inner.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(inner)
        self._style_scrollbars()

    def _style_scrollbars(self):
        dark = self.inner.palette().color(QPalette.ColorRole.Base).lightness() < 128
        sheet = DARK_SCROLLBAR_STYLE if dark else ""
        for bar in (self.inner.verticalScrollBar(), self.inner.horizontalScrollBar()):
            if bar.styleSheet() != sheet:  # avoid restyling loops via PaletteChange
                bar.setStyleSheet(sheet)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:  # light/dark switch at runtime
            self._style_scrollbars()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(_separator_color(self.inner))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


def _draw_item_background(painter, opt: QStyleOptionViewItem):
    """Plain selection background for our list delegates. Deliberately not
    style.drawControl(CE_ItemViewItem): the Windows 11 style adds its own
    decorations there (an accent-colored bar at the item's left edge, focus
    markers) that don't fit the lists' look."""
    if opt.state & QStyle.StateFlag.State_Selected:
        painter.fillRect(opt.rect, opt.palette.color(QPalette.ColorRole.Highlight))


def _draw_item_text(painter, opt: QStyleOptionViewItem, index, indent: int, text: str):
    """Draws an item's text left-aligned at `indent` px from the cell's left
    edge, in the item's foreground color (or the selected-text color)."""
    if opt.state & QStyle.StateFlag.State_Selected:
        color = opt.palette.color(QPalette.ColorRole.HighlightedText)
    else:
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        color = brush.color() if brush is not None else opt.palette.color(QPalette.ColorRole.Text)
    painter.save()
    painter.setFont(opt.font)
    painter.setPen(color)
    painter.drawText(
        opt.rect.adjusted(indent, 0, 0, 0),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        text,
    )
    painter.restore()


class MoveItemDelegate(QStyledItemDelegate):
    """Paints the transposition and hover backgrounds, the row separator and
    the text by hand. The text starts at list_widget.text_indent_fn() px,
    so it can line up with the score sheet's moves.
    Deliberately not done via QSS (QListWidget::item { ... }) -- applying
    any stylesheet to ::item makes Qt's CSS engine take over painting for
    that sub-control, which silently stops respecting a background set via
    item.setBackground()/Qt::BackgroundRole. Painting both ourselves avoids
    that conflict entirely."""

    TRANSPOSITION_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, list_widget: "HoverListWidget"):
        super().__init__(list_widget)
        self.list_widget = list_widget

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(_move_row_height(self.list_widget.fontMetrics()))
        return size

    def paint(self, painter, option, index):
        item = self.list_widget.item(index.row())
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        _draw_item_background(painter, opt)  # text comes last
        if index.data(self.TRANSPOSITION_ROLE):
            painter.fillRect(option.rect, TRANSPOSITION_ROW_COLOR)
        if item is not None and item is self.list_widget.hovered_item:
            painter.fillRect(option.rect, HOVER_ROW_COLOR)  # translucent: blends on top
        # same color as the score sheet's grid, light/dark aware
        painter.save()
        painter.setPen(_separator_color(self.list_widget, option))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()
        indent_fn = self.list_widget.text_indent_fn
        _draw_item_text(painter, opt, index, indent_fn() if indent_fn else 4, text)


class HoverListWidget(QListWidget):
    hoverChanged = pyqtSignal(object)

    POLL_INTERVAL_MS = 80

    def __init__(self):
        super().__init__()
        self.hovered_item: QListWidgetItem | None = None
        self.text_indent_fn = None  # () -> px from cell's left edge to the text; see MoveItemDelegate
        self.setItemDelegate(MoveItemDelegate(self))
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_hover)
        self._poll_timer.start()

    def _poll_hover(self):
        viewport = self.viewport()
        local_pos = viewport.mapFromGlobal(QCursor.pos())
        item = self.itemAt(local_pos) if viewport.rect().contains(local_pos) else None
        if item is not self.hovered_item:
            self.hovered_item = item
            viewport.update()  # repaint so the delegate reflects the new hover state
            self.hoverChanged.emit(item)

    def reset_hover(self):
        """Call after clear()/repopulating items: the old hovered item is
        gone, so drop the reference before the next poll touches it."""
        self.hovered_item = None


# --------------------------------------------------------------------------
# Manual size grip: QSizeGrip hands the actual resize off to the window
# manager (QPlatformWindow::startSystemResize()) on platforms that support
# it -- most Linux compositors do. Once that starts, Qt steps aside
# entirely, so if the WM has a bug leaving its own resize cursor stuck
# after the handoff, there's no Qt-level fix (we never get control back
# during the drag). This implements the resize by hand instead -- plain
# mouse events, plain QWidget::resize() calls -- so it never leaves Qt's
# control and can't be left in that stuck state.
# --------------------------------------------------------------------------

class MetalButton(QPushButton):
    """Icon button that looks like a half-round bar of polished black metal
    with a matt finish: shaded like a cylinder seen from the front (a soft
    light band above the middle, falling off to dark at the bottom) without
    glossy reflections, very fine brush marks running across it and a thin
    worn edge. Same in light and dark mode."""
    RADIUS = 6.0
    #          top edge, light band (at 30%), middle, bottom edge
    SURFACES = {
        "normal": ("#2f3134", "#505358", "#333538", "#0e0e0f"),
        "hover": ("#505358", "#858a92", "#5a5e63", "#262829"),
        "pressed": ("#0c0c0d", "#1f2022", "#2c2e31", "#3c3e42"),
        "disabled": ("#303133", "#3b3c3e", "#323335", "#262728"),
    }
    BRUSH_MARKS_SCALE = 5  # drawn this much larger, then scaled down: hair-fine lines

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # repaint on enter/leave
        self._brush_marks: QPixmap | None = None

    def _brush_marks_pixmap(self) -> QPixmap:
        """Fine horizontal scratches, lighter and darker than the surface.
        Seeded, so every button of a size shows the same, stable pattern."""
        ratio = self.devicePixelRatioF()
        size = self.size() * ratio
        if self._brush_marks is None or self._brush_marks.size() != size:
            large = size * self.BRUSH_MARKS_SCALE
            pixmap = QPixmap(large)
            pixmap.fill(Qt.GlobalColor.transparent)
            rng = random.Random(7)
            painter = QPainter(pixmap)
            for _ in range(large.height() * 12):
                y = rng.randrange(large.height())
                x = rng.randrange(-large.width() // 2, large.width())
                shade = 255 if rng.random() < 0.55 else 0
                painter.setPen(QColor(shade, shade, shade, rng.randint(5, 20)))
                painter.drawLine(x, y, x + rng.randint(large.width() // 10, large.width() // 3), y)
            painter.end()
            pixmap = pixmap.scaled(
                size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            pixmap.setDevicePixelRatio(ratio)
            self._brush_marks = pixmap
        return self._brush_marks

    def paintEvent(self, event):
        if not self.isEnabled():
            state = "disabled"
        elif self.isDown():
            state = "pressed"
        elif self.underMouse():
            state = "hover"
        else:
            state = "normal"
        top, band, middle, bottom = self.SURFACES[state]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(top))
        gradient.setColorAt(0.3, QColor(band))
        gradient.setColorAt(0.6, QColor(middle))
        gradient.setColorAt(1.0, QColor(bottom))
        painter.fillPath(shape, gradient)

        painter.save()
        painter.setClipPath(shape)
        painter.setOpacity(0.45 if state == "disabled" else 1.0)
        painter.drawPixmap(0, 0, self._brush_marks_pixmap())
        painter.restore()

        # worn edge: a dull light line inside the top (bottom when pressed in), dark outline
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if state != "disabled":
            inner = rect.adjusted(1, 1, -1, -1)
            edge = QLinearGradient(inner.topLeft(), inner.bottomLeft())
            light, none = QColor(255, 255, 255, 38), QColor(255, 255, 255, 0)
            edge.setColorAt(0.0, none if state == "pressed" else light)
            edge.setColorAt(0.5, none)
            edge.setColorAt(1.0, light if state == "pressed" else none)
            painter.setPen(QPen(QBrush(edge), 1.0))
            painter.drawRoundedRect(inner, self.RADIUS - 1, self.RADIUS - 1)
        outline = {"disabled": "#1a1a1b", "hover": "#b9bec6"}.get(state, "#0b0b0c")  # hover: bright rim
        painter.setPen(QPen(QColor(outline), 1.0))
        painter.drawPath(shape)

        icon_size = self.iconSize()
        icon_rect = QRectF(0, 0, icon_size.width(), icon_size.height())
        icon_rect.moveCenter(rect.center() + (QPointF(0, 1) if state == "pressed" else QPointF(0, 0)))
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self.icon().paint(painter, icon_rect.toRect(), Qt.AlignmentFlag.AlignCenter, mode)


class ManualSizeGrip(QWidget):
    """left=True: the grip for the bottom left corner. Dragging it moves the
    window's left edge, so the window has to be moved along with the resize.
    A Wayland client can't move its own window; there the left grip has to
    hand the resize to the compositor after all."""
    GRIP_SIZE = 28

    def __init__(self, parent=None, left: bool = False):
        super().__init__(parent)
        self.left = left
        self.setFixedSize(self.GRIP_SIZE, self.GRIP_SIZE)
        self.setCursor(Qt.CursorShape.SizeBDiagCursor if left else Qt.CursorShape.SizeFDiagCursor)
        self._dragging = False
        self._drag_start_pos: QPoint | None = None
        self._start_size = None
        self._start_geometry = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = painter.pen()
        pen.setColor(self.palette().color(self.foregroundRole()))
        pen.setWidth(2)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        for offset in (6, 13, 20):
            if self.left:
                painter.drawLine(offset, h - 2, 2, h - offset)
            else:
                painter.drawLine(w - offset, h - 2, w - 2, h - offset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.left and QApplication.platformName().startswith("wayland"):
                handle = self.window().windowHandle()
                if handle is not None:
                    handle.startSystemResize(Qt.Edge.BottomEdge | Qt.Edge.LeftEdge)
                event.accept()
                return
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._start_size = self.window().size()
            self._start_geometry = self.window().geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.globalPosition().toPoint() - self._drag_start_pos
        window = self.window()
        new_height = max(window.minimumHeight(), self._start_size.height() + delta.y())
        if self.left:
            # minimumSizeHint too: if the layout refused a smaller width, the right edge would wander
            min_width = max(window.minimumWidth(), window.minimumSizeHint().width())
            new_width = max(min_width, self._start_size.width() - delta.x())
            start = self._start_geometry
            window.setGeometry(start.x() + start.width() - new_width, start.y(), new_width, new_height)
        else:
            new_width = max(window.minimumWidth(), self._start_size.width() + delta.x())
            window.resize(new_width, new_height)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()


def _move_row_height(metrics) -> int:
    """Row height shared by the score sheet and the book list: the font's
    full height (ascent + descent, so the tail of g/p/y fits) plus about a
    third of it as breathing room."""
    return round(metrics.height() * 1.35)


def _move_list_font(base: QFont) -> QFont:
    """The font shared by all move lists: twice the default size."""
    font = QFont(base)
    if font.pointSize() > 0:
        font.setPointSize(font.pointSize() * 2)
    else:
        font.setPixelSize(font.pixelSize() * 2)
    return font


class SeparatorLineDelegate(QStyledItemDelegate):
    """Item painting for the Transpositions list like the move lists: plain
    selection, grey hover, text and the shared thin line below each row."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        _draw_item_background(painter, opt)
        if getattr(opt.widget, "hovered_row", None) == index.row():
            painter.fillRect(opt.rect, HOVER_ROW_COLOR)
        _draw_item_text(painter, opt, index, 6, opt.text)
        painter.save()
        painter.setPen(_separator_color(option.widget, option))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class TranspositionsDialog(QDialog):
    """Lists every move order from the starting position to a transposition,
    one PGN movetext line per row. Left-click or the up/down keys load a
    line via on_select(moves), right-click copies its PGN. current: the move
    order that is on the board right now, shown selected if it is listed."""

    def __init__(
        self,
        lines: list[tuple[str, list[chess.Move]]],
        truncated: bool,
        on_select,
        parent=None,
        current: list[chess.Move] | None = None,
    ):
        super().__init__(parent)
        # No window title: the window manager decides its alignment (GNOME
        # centers it), so a left-aligned heading is shown inside instead.
        self.setWindowTitle(" ")  # " " not "": Qt replaces an empty title with the app name (otb.py)

        self.list_widget = QListWidget()
        self.list_widget.setFont(_move_list_font(self.list_widget.font()))  # same as the move lists
        metrics = self.list_widget.fontMetrics()
        for pgn, moves in lines:
            item = QListWidgetItem(pgn)
            item.setData(Qt.ItemDataRole.UserRole, moves)
            # same row height as the move lists (room for the tail of g/p/y)
            item.setSizeHint(QSize(metrics.horizontalAdvance(pgn) + 12, _move_row_height(metrics)))
            self.list_widget.addItem(item)
        self.list_widget.itemClicked.connect(
            lambda item: on_select(item.data(Qt.ItemDataRole.UserRole))
        )

        # Keyboard only (see eventFilter): a click is handled above, and
        # neither a right-click nor the list getting the focus -- both move
        # the current row as well -- may load a line.
        self._key_navigation = False

        def on_current_changed(item, _previous):
            if item is not None and self._key_navigation:
                on_select(item.data(Qt.ItemDataRole.UserRole))

        self.list_widget.currentItemChanged.connect(on_current_changed)
        self.list_widget.installEventFilter(self)
        for row, (_pgn, moves) in enumerate(lines):
            if moves == current:
                self.list_widget.setCurrentRow(row)
        # hover tracked by hand (painted by SeparatorLineDelegate), like the move lists
        self.list_widget.hovered_row = None
        self.list_widget.setMouseTracking(True)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.setItemDelegate(SeparatorLineDelegate(self.list_widget))

        layout = QVBoxLayout(self)
        heading = QLabel("Transpositions")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.4)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        caption = f"{len(lines)} move orders lead to the subsequent position"
        if truncated:
            caption += f" (only the first {len(lines)} shown)"
        layout.addWidget(QLabel(
            caption + ".\nLeft-click a line or use the arrow keys to load it, right-click to copy the PGN."
        ))
        layout.addWidget(SeparatorFrame(self.list_widget))  # same outer frame as the move lists
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.list_widget.setFocus()  # arrow keys work right away

        # Big enough for the longest line and all lines (plus margins, a
        # scrollbar and the heading/buttons), capped at 90% of the screen
        # width and 70% of its height; beyond that the list scrolls.
        lw = self.list_widget
        content_width = lw.sizeHintForColumn(0) + 2 * lw.frameWidth()
        content_width += lw.verticalScrollBar().sizeHint().width() + 40
        rows = max(lw.count(), 1)
        # +1 row of slack, so the last row never needs a scroll bar
        list_height = (rows + 1) * lw.sizeHintForRow(0) + 2 * lw.frameWidth()
        content_height = list_height + self.sizeHint().height() - lw.sizeHint().height() + 8
        screen = self.screen().availableGeometry() if self.screen() else None
        max_width = int(screen.width() * 0.9) if screen else content_width
        max_height = int(screen.height() * 0.7) if screen else content_height
        self.resize(max(560, min(content_width, max_width)), max(300, min(content_height, max_height)))

    def _set_hovered_row(self, row: int | None):
        if row != self.list_widget.hovered_row:
            self.list_widget.hovered_row = row
            self.list_widget.viewport().update()

    def eventFilter(self, obj, event):
        if obj is self.list_widget:
            if event.type() == QEvent.Type.KeyPress:
                self._key_navigation = True
                if event.key() == Qt.Key.Key_Down and not self.list_widget.selectedItems():
                    self.list_widget.setCurrentRow(-1)  # nothing selected yet: start at the first line
                    self.list_widget.setCurrentRow(0)
                    return True
            elif event.type() in (QEvent.Type.KeyRelease, QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self._key_navigation = False
        if obj is self.list_widget.viewport():
            if event.type() == QEvent.Type.MouseMove:
                index = self.list_widget.indexAt(event.position().toPoint())
                self._set_hovered_row(index.row() if index.isValid() else None)
            elif event.type() == QEvent.Type.Leave:
                self._set_hovered_row(None)
        return super().eventFilter(obj, event)

    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Copy PGN")
        if menu.exec(self.list_widget.mapToGlobal(pos)) == copy_action:
            # '*' = PGN result terminator (unknown)
            QApplication.clipboard().setText(f"{item.text()} *\n")


class FenSearchDialog(QDialog):
    """Asks for a FEN and shows the result of search(fen) -> message below
    the input; the dialog stays open so another FEN can be tried."""

    def __init__(self, search, parent=None):
        super().__init__(parent)
        self.setWindowTitle(" ")
        self.resize(560, 220)
        self.search = search

        heading = QLabel("Search for Position by FEN")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.4)
        heading.setFont(heading_font)

        self.fen_edit = QLineEdit()
        self.fen_edit.setPlaceholderText("e.g. rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        self.fen_edit.setClearButtonEnabled(True)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        buttons = QDialogButtonBox()
        search_button = buttons.addButton("Search", QDialogButtonBox.ButtonRole.AcceptRole)
        search_button.setDefault(True)  # Enter in the FEN field searches
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self._on_search)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.fen_edit)
        layout.addWidget(self.result_label, 1)
        layout.addWidget(buttons)

    def _on_search(self):
        fen = self.fen_edit.text().strip()
        if fen:
            self.result_label.setText(self.search(fen))


_PLAYER_TAG = re.compile(r'^\[(White|Black)\s+"(.*)"\]\s*$')


def scan_pgn_players(path: str) -> dict[str, list[int]]:
    """Player name -> [games as White, games as Black] for a PGN file. Reads
    only the tag lines, so it is much faster than parsing the games."""
    players: dict[str, list[int]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith(("[White ", "[Black ")):
                continue
            match = _PLAYER_TAG.match(line)
            if match is None:
                continue
            name = match.group(2).replace('\\"', '"').replace("\\\\", "\\")  # as python-chess reads it
            players.setdefault(name, [0, 0])[match.group(1) == "Black"] += 1
    return players


def _choose_folder(parent, title: str, start: str) -> str | None:
    """Folder chooser whose confirm button says "Select Folder": the stock
    one (QFileDialog.getExistingDirectory) labels it "Open" on some desktops,
    as if a file were to be opened. Returns None if cancelled."""
    dialog = QFileDialog(parent, title, start)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Select Folder")
    if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selectedFiles():
        return None
    return dialog.selectedFiles()[0]


class BookFolderDialog(QDialog):
    """Shows the book folder setting; the "…" button behind the path opens
    the folder chooser. The new folder counts only when confirmed with OK."""

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(" ")
        self.setMinimumWidth(520)
        self.folder = folder

        heading = QLabel("Book Folder")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.4)
        heading.setFont(heading_font)
        caption = QLabel("New books are created in this folder, and Open Book starts there.")

        self.path_edit = QLineEdit(folder)
        self.path_edit.setReadOnly(True)
        choose_button = QPushButton("…")
        choose_button.setToolTip("Select another folder")
        choose_button.setAutoDefault(False)
        choose_button.setFixedWidth(choose_button.fontMetrics().horizontalAdvance("…") + 24)
        choose_button.clicked.connect(self._choose)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(choose_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(caption)
        layout.addLayout(path_row)
        layout.addWidget(buttons)

    def _choose(self):
        folder = _choose_folder(self, "Set Book Folder", self.folder)
        if folder:
            self.folder = folder
            self.path_edit.setText(folder)


class NewBookDialog(QDialog):
    """Asks for the name and the repertoire color of a new book. The color
    is mandatory and also shows in the file name as a W_, B_ or WB_ prefix.
    The book goes into `folder` (the book folder setting), which is shown
    and can be changed. color: preset that can't be changed (the caller
    needs that color)."""

    def __init__(self, folder: str, color: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(" ")
        self.setMinimumWidth(460)
        self.folder = folder

        heading = QLabel("New Book")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.4)
        heading.setFont(heading_font)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name, e.g. sicilian")
        self.name_edit.textChanged.connect(self._update)

        self.color_buttons = {name: QRadioButton(name) for name in BOOK_COLORS.values()}
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Repertoire for:"))
        for name, button in self.color_buttons.items():
            button.setChecked(name == color)
            button.setEnabled(color is None)
            button.toggled.connect(self._update)
            color_row.addWidget(button)
        color_row.addStretch(1)

        # the book folder setting (File > Set Book Folder); changing it here
        # changes the setting once the book is created
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_button = QPushButton("Change…")
        folder_button.setAutoDefault(False)
        folder_button.clicked.connect(self._choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(folder_button)
        self.path_label = QLabel()

        buttons = QDialogButtonBox()
        self.create_button = buttons.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        self.create_button.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.name_edit)
        layout.addLayout(color_row)
        layout.addLayout(folder_row)
        layout.addWidget(self.path_label)
        layout.addWidget(buttons)
        self._update()

    def color(self) -> str | None:
        return next((name for name, button in self.color_buttons.items() if button.isChecked()), None)

    def path(self) -> str | None:
        """Full path of the book file, or None while name or color is missing
        or the name can't be a file name."""
        name = self.name_edit.text().strip()
        if name.lower().endswith(".bin"):
            name = name[:-4].strip()
        color = self.color()
        if not name or color is None or re.search(r'[\\/:*?"<>|]', name):
            return None
        prefix = BOOK_COLOR_PREFIXES[color]
        if not name.upper().startswith(prefix):  # typed with the prefix already
            name = prefix + name
        return os.path.join(self.folder, name + ".bin")

    def _choose_folder(self):
        folder = _choose_folder(self, "Set Book Folder", self.folder)
        if folder:
            self.folder = folder
            self._update()

    def _update(self):
        path = self.path()
        self.create_button.setEnabled(path is not None)
        self.folder_label.setText(f"Book folder: {self.folder}")
        if path is not None:
            self.path_label.setText(f"File name: {os.path.basename(path)}")
        elif self.color() is None:
            self.path_label.setText("Enter a name and choose a color.")
        else:
            self.path_label.setText("Enter a name (without / \\ : * ? \" < > |).")


class ImportPgnDialog(QDialog):
    """Chooses which games of a PGN file to import: all of them, or only the
    games the ticked players had White / Black / either color in."""

    def __init__(self, players: dict[str, list[int]], book_color: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(" ")
        self.resize(460, 520)

        heading = QLabel("Import PGN")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.4)
        heading.setFont(heading_font)

        caption = QLabel(
            "Tick players to import only their games.\n"
            "With no player ticked, all games are imported."
        )

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search player…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.player_list = QListWidget()
        by_games = sorted(players.items(), key=lambda item: (-sum(item[1]), item[0]))
        for name, (as_white, as_black) in by_games:
            item = QListWidgetItem(f"{name}   ({as_white} White, {as_black} Black)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.player_list.addItem(item)
        self.player_list.itemChanged.connect(self._update_color_enabled)

        self.color_label = QLabel("Import the games they played as:")
        self.color_combo = QComboBox()
        self.color_combo.addItems(BOOK_COLORS.values())
        self.color_combo.setCurrentText(book_color or "Both")
        color_row = QHBoxLayout()
        color_row.addWidget(self.color_label)
        color_row.addWidget(self.color_combo)
        color_row.addStretch(1)

        buttons = QDialogButtonBox()
        import_button = buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
        import_button.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(caption)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.player_list, 1)
        layout.addLayout(color_row)
        layout.addWidget(buttons)
        self._update_color_enabled()

    def _apply_filter(self, text: str):
        needle = text.strip().lower()
        for row in range(self.player_list.count()):
            item = self.player_list.item(row)
            item.setHidden(needle not in item.data(Qt.ItemDataRole.UserRole).lower())

    def _update_color_enabled(self):
        enabled = bool(self.players())  # the color only matters with a player filter
        self.color_label.setEnabled(enabled)
        self.color_combo.setEnabled(enabled)

    def players(self) -> set[str]:
        """The ticked players; empty = import all games."""
        items = (self.player_list.item(row) for row in range(self.player_list.count()))
        return {item.data(Qt.ItemDataRole.UserRole) for item in items if item.checkState() == Qt.CheckState.Checked}

    def color(self) -> str:
        return self.color_combo.currentText()


class LineMoveDelegate(QStyledItemDelegate):
    """Left-aligns all moves at a common indent, chosen so that a long
    reference move (REFERENCE_SAN) would sit centered in the cell. Short
    moves like e4 then line up with long ones instead of each being
    centered on its own."""

    REFERENCE_SAN = "Naxd4"

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        _draw_item_background(painter, opt)
        if getattr(opt.widget, "hovered_cell", None) == (index.row(), index.column()):
            painter.fillRect(option.rect, HOVER_ROW_COLOR)  # same grey as the book list's hover

        _draw_item_text(painter, opt, index, self.indent(opt.rect.width(), opt.fontMetrics), text)
        painter.save()
        painter.setPen(_separator_color(opt.widget, option))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
        painter.restore()

    @classmethod
    def indent(cls, cell_width: int, metrics) -> int:
        return max(4, (cell_width - metrics.horizontalAdvance(cls.REFERENCE_SAN)) // 2)


class MoveNumberHeader(QHeaderView):
    """Row-number header of the score sheet: draws the same separator line
    under each move number as LineMoveDelegate draws under the moves."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        painter.save()
        painter.setPen(_separator_color(self))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        # Divider to White's moves, drawn over the style's own section border
        # (a second line in the first cell would sit next to it and look 2 px)
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()


class LineTable(QTableWidget):
    """The current line as a two-column score sheet (White | Black, move
    numbers as row headers). The move leading to the current position is
    selected, moves after it are greyed out; clicking a move emits the ply
    to jump to."""

    plyClicked = pyqtSignal(int)
    AHEAD_COLOR = QColor("#888888")

    def __init__(self):
        super().__init__(0, 2)
        self.setVerticalHeader(MoveNumberHeader(self))
        self.horizontalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.horizontalHeader().setHighlightSections(False)  # no bold "Black" on selection
        self.verticalHeader().setHighlightSections(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWordWrap(False)
        self.setItemDelegate(LineMoveDelegate(self))
        self.cellClicked.connect(self._on_cell_clicked)
        self.hovered_cell: tuple[int, int] | None = None  # painted by LineMoveDelegate
        self.setMouseTracking(True)
        # Grid drawn by LineMoveDelegate instead, in _separator_color() --
        # QTableView's own grid color can only be changed via a stylesheet,
        # which also restyles (and shrinks) the row-number header.
        self.setShowGrid(False)

    def set_line(self, sans: list[str], current_ply: int):
        self.blockSignals(True)
        self.hovered_cell = None  # rows are rebuilt; the next mouse move re-detects it
        self.clearSelection()
        self.setRowCount((len(sans) + 1) // 2)
        self.clearContents()
        for i, san in enumerate(sans):
            item = QTableWidgetItem(san)  # alignment: see LineMoveDelegate
            if i >= current_ply:
                item.setForeground(QBrush(self.AHEAD_COLOR))
            self.setItem(i // 2, i % 2, item)
        self.setVerticalHeaderLabels([str(n) for n in range(1, self.rowCount() + 1)])
        if current_ply > 0:
            row, col = divmod(current_ply - 1, 2)
            self.setCurrentCell(row, col)
            self.scrollToItem(self.item(row, col))
        else:
            self.scrollToTop()
        self.blockSignals(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.verticalHeader().setMinimumSectionSize(1)
            self.verticalHeader().setDefaultSectionSize(_move_row_height(self.fontMetrics()))

    def _set_hovered_cell(self, cell: tuple[int, int] | None):
        if cell != self.hovered_cell:
            self.hovered_cell = cell
            self.viewport().update()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        index = self.indexAt(event.position().toPoint())
        on_move = index.isValid() and self.item(index.row(), index.column()) is not None
        self._set_hovered_cell((index.row(), index.column()) if on_move else None)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Leave:
            self._set_hovered_cell(None)
        return super().viewportEvent(event)

    def _on_cell_clicked(self, row: int, col: int):
        if self.item(row, col) is not None:  # empty Black cell after White's last move
            self.plyClicked.emit(row * 2 + col + 1)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, book_path: str | None):
        super().__init__()

        if book_path:
            self.book_path = book_path
        else:
            stored_path = _settings().value("book_path", type=str)
            if stored_path and os.path.exists(stored_path):
                self.book_path = stored_path
            else:
                self.book_path = _default_book_path()
        self._transposition_cache: set[int] | None = None
        self._key_index: dict[int, list[BookEntry]] | None = None  # see _index_entries_by_key
        self._autoplay_timer = QTimer(self)  # "Autoplay from here" in the line's context menu
        speed = _settings().value("play_speed", DEFAULT_PLAY_SPEED, type=str)
        self.play_speed = speed if speed in PLAY_SPEEDS_MS else DEFAULT_PLAY_SPEED
        self._autoplay_timer.setInterval(PLAY_SPEEDS_MS[self.play_speed])
        self._autoplay_timer.timeout.connect(self._autoplay_step)
        self._load_book(self.book_path)
        self.setWindowTitle("Opening Tree Builder")

        self.game_moves: list[chess.Move] = []
        self.ply = 0
        self.board = chess.Board()

        self.mode = "VIEW"

        self.engine_worker: EngineWorker | None = None
        self.engine_active = False

        self.board_widget = BoardWidget(lambda: self.board, lambda: self.mode, self.play_move)

        self.move_list = HoverListWidget()
        list_font = _move_list_font(self.move_list.font())
        self.move_list.setFont(list_font)
        self.move_list.itemClicked.connect(self._on_item_clicked)
        self.move_list.hoverChanged.connect(self._on_item_hover_changed)
        self.move_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.move_list.customContextMenuRequested.connect(self._on_context_menu)

        self.line_table = LineTable()
        self.line_table.setFont(list_font)  # same size as the book move list
        # book moves keep the same gap from their cell's left border as the
        # score sheet's moves do inside their cells
        self.move_list.text_indent_fn = lambda: LineMoveDelegate.indent(
            self.line_table.columnWidth(0), self.line_table.fontMetrics()
        )
        self.line_table.plyClicked.connect(self.goto_ply)
        self.line_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.line_table.customContextMenuRequested.connect(self._on_line_context_menu)

        self.btn_start = MetalButton()
        self.btn_start.setIcon(_make_skip_start_icon(color=NAV_BUTTON_ICON_COLOR))
        self.btn_start.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_start.setToolTip("Go to start (Home)")

        self.btn_back = MetalButton()
        self.btn_back.setIcon(_make_step_back_icon(color=NAV_BUTTON_ICON_COLOR))
        self.btn_back.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_back.setToolTip("Step back (←)")

        self.btn_forward = MetalButton()
        self.btn_forward.setIcon(_make_step_forward_icon(color=NAV_BUTTON_ICON_COLOR))
        self.btn_forward.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_forward.setToolTip("Step forward (→)")

        self.btn_end = MetalButton()
        self.btn_end.setIcon(_make_skip_end_icon(color=NAV_BUTTON_ICON_COLOR))
        self.btn_end.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_end.setToolTip("Go to end (End)")

        self.btn_flip = MetalButton()
        self.btn_flip.setIcon(_make_flip_icon(color=NAV_BUTTON_ICON_COLOR))
        self.btn_flip.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_flip.setToolTip("Flip board (F)")

        for btn in (self.btn_start, self.btn_back, self.btn_forward, self.btn_end, self.btn_flip):
            btn.setStyleSheet(NAV_BUTTON_STYLE)
            # no keyboard focus: avoids the dotted focus frame some styles
            # (Windows) draw; the keys work through window-wide shortcuts
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.engine_label = QLabel()
        self.engine_toggle = ToggleSwitch()
        # no keyboard focus: Space on a focused switch would toggle it past
        # the "no engine" check; E is the keyboard shortcut instead
        self.engine_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.mode_switch = ModeSwitch()
        self.mode_switch.setToolTip("View / Build mode")

        nav_button_height = self.btn_start.sizeHint().height()
        self.mode_switch.setFixedHeight(nav_button_height)
        engine_size = int(nav_button_height * 0.8)  # scaled down to 80% of the button height
        self.engine_toggle.setFixedSize(int(engine_size * 1.9), engine_size)
        self.engine_label.setPixmap(_make_engine_icon(engine_size).pixmap(engine_size, engine_size))
        # self.mode == "VIEW" is the default; knob starts unchecked/left (green)

        self.btn_start.clicked.connect(self.goto_start)
        self.btn_back.clicked.connect(self.step_back)
        self.btn_forward.clicked.connect(self.step_forward)
        self.btn_end.clicked.connect(self.goto_end)
        self.btn_flip.clicked.connect(self.board_widget.flip)
        self.engine_toggle.toggled.connect(self._on_engine_toggle_changed)
        self.engine_toggle.unavailableClicked.connect(self._explain_no_engine)
        self.mode_switch.toggled.connect(lambda checked: self._set_mode("BUILD" if checked else "VIEW"))

        nav_grid = QGridLayout()
        nav_grid.setHorizontalSpacing(6)
        nav_grid.setVerticalSpacing(6)
        # spans both columns, so it's exactly as wide as start+back combined
        nav_grid.addWidget(self.mode_switch, 0, 0, 1, 2)
        nav_grid.addWidget(self.btn_flip, 1, 0)
        engine_group = QHBoxLayout()
        engine_group.addStretch()  # icon centered in the free space left of the toggle
        engine_group.addWidget(self.engine_label)
        engine_group.addStretch()  # switch stays pinned right
        engine_group.addWidget(self.engine_toggle)
        nav_grid.addLayout(engine_group, 1, 1, alignment=Qt.AlignmentFlag.AlignVCenter)  # fills width, centered vertically with btn_flip

        # Without this, column 1 (engine_group) would size itself wider than
        # column 0 (btn_flip alone), since the engine group needs more room
        # than a single icon-only button.
        # Forcing both columns to the same explicit minimum keeps every
        # button identical while still giving the engine group enough room.
        # Uses the full-size (pre-shrink) engine footprint deliberately: the
        # actual displayed engine toggle is smaller (see engine_size above),
        # but the column width itself must stay independent of that, or
        # shrinking the toggle would shrink the buttons back down too.
        full_engine_width = nav_button_height + 6 + int(nav_button_height * 1.9)
        column_width = max(self.btn_flip.sizeHint().width(), full_engine_width)
        nav_grid.setColumnMinimumWidth(0, column_width)
        nav_grid.setColumnMinimumWidth(1, column_width)
        # equal stretch: both columns split the panel width exactly in half,
        # like the two-column navigation grid below the score sheet
        nav_grid.setColumnStretch(0, 1)
        nav_grid.setColumnStretch(1, 1)

        # Navigation below the score sheet: backward left, forward right
        # |<  >|  (start, end)
        # <   >   (back, forward)
        line_nav = QGridLayout()
        line_nav.setHorizontalSpacing(6)
        line_nav.setVerticalSpacing(6)
        line_nav.addWidget(self.btn_start, 0, 0)
        line_nav.addWidget(self.btn_end, 0, 1)
        line_nav.addWidget(self.btn_back, 1, 0)
        line_nav.addWidget(self.btn_forward, 1, 1)
        line_nav.setColumnStretch(0, 1)
        line_nav.setColumnStretch(1, 1)
        line_panel = QVBoxLayout()
        line_panel.setContentsMargins(0, 0, 0, 0)
        line_panel.addWidget(SeparatorFrame(self.line_table))
        line_panel.addLayout(line_nav)
        line_widget = QWidget()
        line_widget.setLayout(line_panel)
        line_widget.setFixedWidth(LINE_PANEL_WIDTH)

        # Controls below the lists in both panels: the lists start level with
        # the board's top edge, the controls form one strip along its bottom.
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(SeparatorFrame(self.move_list))
        right.addLayout(nav_grid)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(RIGHT_PANEL_WIDTH)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.board_widget)
        layout.addWidget(line_widget)
        layout.addWidget(right_widget)
        self.setCentralWidget(central)

        # Keyboard navigation along the current line (window-wide, so it
        # works whichever list has focus).
        for key, slot in (
            (Qt.Key.Key_Left, self.step_back),
            (Qt.Key.Key_Right, self.step_forward),
            (Qt.Key.Key_Home, self.goto_start),
            (Qt.Key.Key_End, self.goto_end),
        ):
            QShortcut(QKeySequence(key), self, activated=slot)
        # f = flip board, e = engine on/off; Shift variants so caps lock /
        # uppercase works too
        for letter, slot in (("F", self.board_widget.flip), ("E", self._on_engine_key)):
            for seq in (letter, f"Shift+{letter}"):
                QShortcut(QKeySequence(seq), self, activated=slot)

        self._build_menu()
        _settings().remove("engine_path")  # from versions that let the user choose the engine
        self._update_engine_availability()
        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(False)
        # Windows styles frame every status bar section (vertical lines
        # between eval, message and book path); the sections need none.
        self.statusBar().setStyleSheet("QStatusBar::item { border: none; }")
        # showMessage() puts text in the *temporary* slot, which Qt clears
        # whenever a menu opens/closes (the menu pushes its own status tip).
        # A permanent widget is untouched by that, so the status text stays.
        self.eval_label = QLabel()
        eval_font = self.eval_label.font()
        eval_font.setBold(True)
        self.eval_label.setFont(eval_font)
        self.eval_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eval_label.setMinimumWidth(self.eval_label.fontMetrics().horizontalAdvance("-99.99 (99)") + 12)
        self.eval_label.setToolTip("Engine evaluation from White's point of view (search depth)")
        self.statusBar().addWidget(ManualSizeGrip(self, left=True))
        self.statusBar().addWidget(self.eval_label)  # leftmost, before the status text
        # size grip | eval | check/mate message ............ book path | size grip
        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusBar().addWidget(self.status_label, 1)
        # Ignored size policy: a long path is cut off instead of widening the window
        self.book_label = QLabel()
        self.book_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.book_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addWidget(self.book_label, 2)
        size_grip = ManualSizeGrip(self)
        self.statusBar().addPermanentWidget(size_grip)

        self._orient_board_to_book()
        self.refresh()
        size = _settings().value("window_size")  # as it was when OTB was last closed
        if isinstance(size, QSize) and size.isValid():
            self.resize(size)

    def _orient_board_to_book(self):
        """Puts the book's repertoire color at the bottom. Books for both
        colors or without a color marker leave the board as it is."""
        if self.book_color in ("White", "Black"):
            self.board_widget.orientation = chess.WHITE if self.book_color == "White" else chess.BLACK
            self.board_widget.redraw()

    def _set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        self.import_pgn_action.setEnabled(self.mode == "BUILD")
        self.board_widget.redraw()
        self._update_status()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")

        self.import_pgn_action = QAction("Import PGN", self)
        self.import_pgn_action.triggered.connect(self._import_pgn_dialog)
        self.import_pgn_action.setEnabled(self.mode == "BUILD")  # View mode: read-only
        file_menu.addAction(self.import_pgn_action)

        new_action = QAction("New Book", self)
        new_action.triggered.connect(lambda: self._new_book_dialog())
        file_menu.addAction(new_action)

        open_action = QAction("Open Book", self)
        open_action.triggered.connect(self._open_book_dialog)
        file_menu.addAction(open_action)

        book_color_action = QAction("Set Book Color", self)
        book_color_action.triggered.connect(self._book_color_dialog)
        file_menu.addAction(book_color_action)

        book_folder_action = QAction("Set Book Folder", self)
        book_folder_action.triggered.connect(self._book_folder_dialog)
        file_menu.addAction(book_folder_action)


        view_menu = self.menuBar().addMenu("View")
        speed_menu = view_menu.addMenu("Autoplay Speed")
        speed_group = QActionGroup(self)  # exclusive: exactly one speed is ticked
        for speed in PLAY_SPEEDS_MS:
            action = speed_menu.addAction(speed)
            action.setCheckable(True)
            action.setChecked(speed == self.play_speed)
            action.triggered.connect(lambda _checked, speed=speed: self._set_play_speed(speed))
            speed_group.addAction(action)

        animation_menu = view_menu.addMenu("Animation Speed")
        animation_group = QActionGroup(self)
        current = _settings().value("animation_speed", DEFAULT_ANIMATION_SPEED, type=str)
        if current not in ANIMATION_SPEEDS_MS:
            current = DEFAULT_ANIMATION_SPEED
        self.board_widget.set_animation_speed(current)
        for speed in ANIMATION_SPEEDS_MS:
            action = animation_menu.addAction(speed)
            action.setCheckable(True)
            action.setChecked(speed == current)
            action.triggered.connect(lambda _checked, speed=speed: self._set_animation_speed(speed))
            animation_group.addAction(action)

        coordinates_menu = view_menu.addMenu("Coordinates")
        coordinates_group = QActionGroup(self)
        current = _settings().value("coordinates", DEFAULT_COORDINATES, type=str)
        if current not in COORDINATE_MODES:
            current = DEFAULT_COORDINATES
        self.board_widget.set_coordinates(current)
        for mode, text in COORDINATE_MODES.items():
            action = coordinates_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(lambda _checked, mode=mode: self._set_coordinates(mode))
            coordinates_group.addAction(action)

        search_menu = self.menuBar().addMenu("Search")
        search_fen_action = QAction("by FEN", self)
        search_fen_action.triggered.connect(lambda: FenSearchDialog(self._search_fen, self).exec())
        search_menu.addAction(search_fen_action)

        help_menu = self.menuBar().addMenu("Help")
        getting_started_action = QAction("Getting Started", self)
        getting_started_action.triggered.connect(self._show_getting_started)
        help_menu.addAction(getting_started_action)
        help_menu.addSeparator()
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_getting_started(self):
        box = QMessageBox(self)
        box.setWindowTitle(" ")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.setText(
            "<h3>Getting Started</h3>"
            "<p><b style='color:#40a040'>View mode (green)</b>: explore your book, "
            "moves are <b>not</b> saved.</p>"
            "<p><b style='color:#a04040'>Build mode (red)</b>: every move you play is "
            "saved to the book immediately.</p>"
            "<p>Play moves on the board, or click a move in the list.</p>"
            "<p>Right-click a move (build mode) to edit its weight or delete it "
            "together with all following moves.</p>"
            "<p><b>Move List:</b> <span style='color:#c00000'>Red</span> moves lead to a transposition. "
            "Right-click and select <i>Transpositions</i> to see every move order as PGN.</p>"
            "<p>Turn on the engine switch for a blue best-move arrow and the "
            "evaluation in the status bar.</p>"
            "<p><i>File > Import PGN</i> adds whole games (build mode).</p>"
            f'<p>See verbose documentation: <a href="{USER_GUIDE_URL}"><b>README (GitHub)</b></a></p>'
        )
        box.exec()

    def _show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.setText(
            f"<h3>Opening Tree Builder</h3>"
            f"<p>Version {APP_VERSION}</p>"
            "<p>Free and open-source software, licensed under the "
            '<a href="https://www.gnu.org/licenses/gpl-3.0.html">GNU&nbsp;GPL&nbsp;v3</a>.<br>'
            "You may use, share and modify it free of charge.</p>"
            '<p>Engine evaluation by <a href="https://stockfishchess.org">Stockfish</a>, '
            "also licensed under the GNU&nbsp;GPL&nbsp;v3.</p>"
            "<hr>"
            "<p>For open-source chess broadcasting hard- and software, tournaments and more visit:</p>"
            '<p style="font-size: x-large;">'
            '<a href="https://www.gambitgear.ch">www.gambitgear.ch</a></p>'
        )
        box.exec()

    NO_ENGINE_HINT = "Stockfish was not found."

    @staticmethod
    def _engine_path() -> str | None:
        """The engine is always Stockfish; there is no choice of engine. The
        installers bundle it in engines/ next to otb.py (PyInstaller: in
        _internal/). Running from source, a Stockfish installed on the system
        is used: on PATH, or in the usual places, since an app started from
        the desktop may not get the terminal's PATH."""
        bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engines",
                               "stockfish.exe" if sys.platform == "win32" else "stockfish")
        candidates = [bundled, shutil.which("stockfish"),
                      "/usr/games/stockfish", "/usr/local/bin/stockfish", "/opt/homebrew/bin/stockfish"]
        return next((path for path in candidates if path and os.access(path, os.X_OK)), None)

    def _update_engine_availability(self):
        """Engine switch is unavailable (faded, explains itself) if no
        Stockfish can be found, e.g. running from source without one."""
        available = self._engine_path() is not None
        self.engine_toggle.set_unavailable(not available)
        tip = "Engine (E)" if available else self.NO_ENGINE_HINT
        self.engine_toggle.setToolTip(tip)
        self.engine_label.setToolTip(tip)

    def _on_engine_key(self):
        if self.engine_toggle.unavailable:
            self._explain_no_engine()
        else:
            self.engine_toggle.toggle()

    def _explain_no_engine(self):
        box = QMessageBox(self)
        box.setWindowTitle(" ")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(self.NO_ENGINE_HINT)
        if sys.platform == "win32":
            how = "It comes with the installer: please reinstall OTB."
        elif sys.platform == "darwin":
            how = "Install it with Homebrew (brew install stockfish), then restart OTB."
        else:
            how = ("Install it with your package manager, e.g. sudo apt install stockfish,\n"
                   "then restart OTB.")
        box.setInformativeText(how)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()

    def _book_folder(self) -> str:
        """Where new books are created and the Open Book dialog starts:
        the book folder setting, or the current book's folder as long as
        none was chosen (or the chosen one is gone)."""
        folder = _settings().value("book_folder", "", type=str)
        return folder if folder and os.path.isdir(folder) else os.path.dirname(self.book_path)

    def _book_folder_dialog(self):
        dialog = BookFolderDialog(self._book_folder(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.folder != self._book_folder():
            _settings().setValue("book_folder", dialog.folder)

    def _open_book_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Polyglot book", self._book_folder(), "Polyglot books (*.bin);;All files (*)"
        )
        if path:
            self.book_path = path
            self._load_book(path)
            _settings().setValue("book_path", path)
            self._orient_board_to_book()
            self.refresh()
            if self.book_color is None:
                self._book_color_dialog()

    def _book_color_dialog(self):
        """Asks which side the book is a repertoire for and stores the answer
        in the book file (see COLOR_MARKER_MAGIC)."""
        box = QMessageBox(self)
        box.setWindowTitle("Book Color")
        box.setIcon(QMessageBox.Icon.Question)
        if self.book_color is None:
            box.setText("This book has no repertoire color yet.")
        else:
            box.setText(f"This book is marked as a {self.book_color} repertoire.")
        box.setInformativeText(
            "Is it a repertoire for White, for Black or for both colors?\n"
            "The answer is saved as a marker in the book file."
        )
        buttons = {box.addButton(name, QMessageBox.ButtonRole.AcceptRole): name for name in BOOK_COLORS.values()}
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        color = buttons.get(box.clickedButton())
        if color is None or color == self.book_color:
            return
        try:
            save_book(self.book_path, self.book_entries, color)
        except OSError as error:
            QMessageBox.warning(self, "Book Color", f"Could not write {self.book_path}:\n{error}")
            return
        self.book_color = color
        self._orient_board_to_book()
        self._update_status()

    def _new_book_dialog(self, color: str | None = None) -> bool:
        """Creates an empty book and makes it the current one. color: the
        book must have this color (not offered for choice). Returns False if
        cancelled."""
        dialog = NewBookDialog(self._book_folder(), color, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if dialog.folder != self._book_folder():
            _settings().setValue("book_folder", dialog.folder)
        path, color = dialog.path(), dialog.color()
        if os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "New Book",
                f"{os.path.basename(path)} already exists.\nReplace it with an empty book?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        try:
            save_book(path, [], color)
        except OSError as error:
            QMessageBox.warning(self, "New Book", f"Could not create {path}:\n{error}")
            return False
        self.book_path = path
        self.book_entries = []
        self._key_index = None
        self.book_color = color
        self._transposition_cache = None
        _settings().setValue("book_path", path)
        self._orient_board_to_book()
        self._load_line([])  # an empty book starts from the initial position
        return True

    def _confirm_color_mismatch(self, color: str) -> bool:
        """The book is a one-color repertoire and the import would add games
        of another color: offers a new book for them instead. Returns False
        if the import is to be dropped."""
        box = QMessageBox(self)
        box.setWindowTitle("Import PGN")
        box.setIcon(QMessageBox.Icon.Warning)
        games = "games of both colors" if color == "Both" else f"{color} games"
        box.setText(f"This is a {self.book_color} book.")
        box.setInformativeText(
            f"Importing {games} mixes both colors in one book.\n"
            f"Create a new {color} book for them instead?"
        )
        new_button = box.addButton("Create new book…", QMessageBox.ButtonRole.AcceptRole)
        anyway_button = box.addButton("Import anyway", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(new_button)
        box.exec()
        if box.clickedButton() == new_button:
            return self._new_book_dialog(color)
        if box.clickedButton() == anyway_button:
            self.book_color = "Both"  # written with the import; keeps the marker truthful
            return True
        return False

    def _import_pgn_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PGN", "", "PGN files (*.pgn);;All files (*)"
        )
        if not path:
            return
        try:
            dialog = ImportPgnDialog(scan_pgn_players(path), self.book_color, self)
        except OSError as error:
            QMessageBox.warning(self, "Import failed", str(error))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        players, color = dialog.players(), dialog.color()
        if players and self.book_color in ("White", "Black") and color != self.book_color:
            if not self._confirm_color_mismatch(color):
                return

        progress = self._make_progress("Importing PGN…", cancellable=True)

        def report(fraction: float, game_count: int) -> bool:
            progress.setValue(int(fraction * 1000))
            progress.setLabelText(f"Importing PGN… {game_count} games")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            result = self._import_pgn_file(path, report, players, color)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            self._load_book(self.book_path)  # drop the partial in-memory import
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        if result is None:  # cancelled: nothing was saved, restore the book
            progress.close()
            self._load_book(self.book_path)
            return
        imported, game_count, move_count = result
        progress.setLabelText("Updating view…")
        QApplication.processEvents()
        self.refresh()
        progress.close()
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {imported} of {game_count} game(s) from the PGN file, "
            f"adding/updating {move_count} move(s) in the book.",
        )

    def _import_pgn_file(
        self, path: str, report=None, players: set[str] | None = None, color: str = "Both"
    ) -> tuple[int, int, int] | None:
        """Returns (games imported, games in the file, moves added/updated).

        players: if given and not empty, only games in which one of them
        had `color` ("White", "Black", "Both" = either) are imported.
        report(fraction_done, game_count) -> keep_going is called every
        few games; returns None (book left unsaved) if it asks to stop."""
        def wanted(headers) -> bool:
            return (color != "Black" and headers.get("White") in players) or (
                color != "White" and headers.get("Black") in players)

        imported = 0
        game_count = 0
        move_count = 0
        total_size = os.path.getsize(path) or 1
        index = {(e.key, e.from_square, e.to_square, e.promotion): e for e in self.book_entries}
        with open(path, encoding="utf-8", errors="replace") as f:
            while True:
                if report is not None and game_count % 20 == 0 and game_count:
                    if not report(min(f.tell() / total_size, 1.0), game_count):
                        return None
                if players:
                    # headers first: skipping a game is much cheaper than parsing it
                    offset = f.tell()
                    headers = chess.pgn.read_headers(f)
                    if headers is None:
                        break
                    if not wanted(headers):
                        game_count += 1
                        continue
                    f.seek(offset)
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                game_count += 1
                imported += 1
                move_count += self._import_game_tree(game, game.board(), index)
        save_book(self.book_path, self.book_entries, self.book_color)
        return imported, game_count, move_count

    def _make_progress(self, label: str, cancellable: bool) -> QProgressDialog:
        """Window-modal progress dialog: keeps the UI responsive (no "not
        responding") while blocking clicks that would change the book."""
        progress = QProgressDialog(label, "Cancel" if cancellable else None, 0, 1000, self)
        if not cancellable:
            progress.setCancelButton(None)
        progress.setWindowTitle(" ")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        return progress

    def _load_book(self, path: str):
        progress = self._make_progress(f"Opening {os.path.basename(path)}…", cancellable=False)

        def report(fraction: float):
            progress.setValue(int(fraction * 1000))
            QApplication.processEvents()

        self.book_entries, self.book_color = load_book(path)
        self._key_index = None
        self._backfill_resulting_keys(report)
        self._transposition_cache = None
        progress.close()

    def _import_game_tree(
        self, node: chess.pgn.GameNode, board: chess.Board, index: dict[tuple[int, int, int, int], BookEntry]
    ) -> int:
        count = 0
        for child in node.variations:
            move = child.move
            self._record_book_move(board, move, save=False, index=index)
            count += 1
            board.push(move)
            count += self._import_game_tree(child, board, index)
            board.pop()
        return count

    def _path_to_key(self, target_key: int) -> list[chess.Move] | None:
        """The most weighted line in the book from the starting position to
        the position with target_key, or None if the book never reaches it.

        Among all shortest move orders (transpositions have equal length;
        restricting to shortest also keeps cycles like Nf3 Nf6 Ng1 Ng8 out),
        picks the one with the highest total weight. Breadth-first over the
        cached resulting_key edges gives the distances, then one pass in BFS
        order keeps the best-scoring incoming edge per position."""
        start_key = chess.polyglot.zobrist_hash(chess.Board())
        entries_by_key = self._index_entries_by_key()
        dist: dict[int, int] = {start_key: 0}
        order: list[int] = []
        queue: deque[int] = deque([start_key])
        while queue:
            key = queue.popleft()
            if target_key in dist and dist[key] >= dist[target_key]:
                break  # every predecessor of the target is already expanded
            order.append(key)
            for e in entries_by_key.get(key, []):
                child_key = e.resulting_key
                if child_key is not None and child_key not in dist:
                    dist[child_key] = dist[key] + 1
                    queue.append(child_key)
        if target_key not in dist:
            return None

        best: dict[int, int] = {start_key: 0}
        parent: dict[int, tuple[int, BookEntry] | None] = {start_key: None}
        for key in order:
            for e in entries_by_key.get(key, []):
                child_key = e.resulting_key
                if child_key is None or dist.get(child_key) != dist[key] + 1:
                    continue
                score = best[key] + e.weight
                if score > best.get(child_key, -1):
                    best[child_key] = score
                    parent[child_key] = (key, e)

        path: list[BookEntry] = []
        key = target_key
        while parent[key] is not None:
            key, e = parent[key]
            path.append(e)
        board = chess.Board()
        moves: list[chess.Move] = []
        for e in reversed(path):
            move = decode_move(board, e)
            if move is None:
                return None  # stale/colliding entry
            moves.append(move)
            board.push(move)
        return moves

    def _search_fen(self, fen: str) -> str:
        """FenSearchDialog callback: jumps the board to the position if the
        book contains it and returns the message to show."""
        try:
            target = chess.Board(fen)
        except ValueError as exc:
            return f"Invalid FEN: {exc}"
        moves = self._path_to_key(chess.polyglot.zobrist_hash(target))
        if moves is None:
            return "Position not found in the book."
        self._load_line(moves)
        if not moves:
            return "Found: this is the starting position."
        return f"Found. Path to this position:\n\n{chess.Board().variation_san(moves)}"

    def goto_start(self):
        self.ply = 0
        self._rebuild_board()
        self.refresh()

    def step_back(self):
        if self.ply > 0:
            self.ply -= 1
            self._rebuild_board()
            self.refresh()

    def goto_ply(self, ply: int):
        self.ply = max(0, min(ply, len(self.game_moves)))
        self._rebuild_board()
        self.refresh()

    def goto_end(self):
        self.goto_ply(len(self.game_moves))

    def step_forward(self):
        if self.ply < len(self.game_moves):
            self.ply += 1
            self._rebuild_board()
            self.refresh()

    def _rebuild_board(self):
        self.board = chess.Board()
        for move in self.game_moves[: self.ply]:
            self.board.push(move)

    def _on_engine_toggle_changed(self, checked: bool):
        if checked:
            self._start_engine()
        else:
            self._stop_engine()

    def _sync_engine_toggle(self):
        if self.engine_toggle.isChecked() != self.engine_active:
            self.engine_toggle.blockSignals(True)
            self.engine_toggle.setChecked(self.engine_active)
            self.engine_toggle.blockSignals(False)

    def _start_engine(self):
        if self.engine_worker is None:
            path = self._engine_path()
            if path is None:
                # No Stockfish (e.g. running from source without one): switch
                # back off and explain, whatever turned the switch on.
                self._update_engine_availability()
                self._sync_engine_toggle()
                self._explain_no_engine()
                return

            self.engine_worker = EngineWorker(path)
            self.engine_worker.best_move_found.connect(self._on_engine_best_move)
            self.engine_worker.evaluation_updated.connect(self._on_engine_evaluation)
            self.engine_worker.error.connect(self._on_engine_error)

        self.engine_active = True
        self._sync_engine_toggle()
        self.engine_worker.start(self.board)

    def _stop_engine(self):
        self.engine_active = False
        self._sync_engine_toggle()
        if self.engine_worker is not None:
            try:
                self.engine_worker.best_move_found.disconnect(self._on_engine_best_move)
                self.engine_worker.evaluation_updated.disconnect(self._on_engine_evaluation)
            except (TypeError, RuntimeError):
                pass
            self.engine_worker.stop()
            self.engine_worker = None

        self.board_widget.set_engine_arrow(None)
        self.refresh()

    def _on_engine_best_move(self, from_square: int, to_square: int):
        self.board_widget.set_engine_arrow((from_square, to_square))

    def _on_engine_evaluation(self, text: str):
        if self.engine_active:  # ignore late signals queued before the engine was stopped
            self.eval_label.setText(text)

    def _on_engine_error(self, message: str):
        self._stop_engine()
        QMessageBox.warning(self, "Engine error", message)

    def closeEvent(self, event):
        if not (self.isMaximized() or self.isFullScreen()):
            _settings().setValue("window_size", self.size())
        if self.engine_worker is not None:
            self.engine_worker.quit_engine()
        super().closeEvent(event)

    def play_move(self, move: chess.Move):
        if self.mode == "BUILD":
            self._record_book_move(self.board, move)
        if self.ply < len(self.game_moves) and move == self.game_moves[self.ply]:
            self.ply += 1
        else:
            self.game_moves = self.game_moves[: self.ply] + [move]
            self.ply += 1
        self._rebuild_board()
        self.refresh()

    def _record_book_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        save: bool = True,
        index: dict[tuple[int, int, int, int], BookEntry] | None = None,
    ):
        """index: optional (key, from, to, promo) -> entry lookup for bulk
        imports, which saves building the per-move candidate list."""
        key = chess.polyglot.zobrist_hash(board_before)
        from_sq, to_sq, promo = encode_move(board_before, move)
        if index is not None:
            existing = index.get((key, from_sq, to_sq, promo))
        else:
            existing = next(
                (e for e in self._index_entries_by_key().get(key, [])
                 if e.from_square == from_sq and e.to_square == to_sq and e.promotion == promo),
                None,
            )
        records_before = len(self.book_entries) + (self.book_color is not None)
        if existing is not None:
            existing.weight = min(existing.weight + 1, 0xFFFF)  # polyglot weight is 16-bit
        else:
            # push/pop instead of copy(): copy() duplicates the whole move stack
            board_before.push(move)
            resulting_key = chess.polyglot.zobrist_hash(board_before)
            board_before.pop()
            entry = BookEntry(key, from_sq, to_sq, promo, 1, 0, resulting_key)
            self.book_entries.append(entry)
            if self._key_index is not None:
                self._key_index.setdefault(key, []).append(entry)
            if index is not None:
                index[(key, from_sq, to_sq, promo)] = entry
                self._transposition_cache = None  # bulk import: recompute once afterwards
            else:
                self._add_to_transposition_cache(entry)
        if save and not patch_book(self.book_path, existing or entry, existing is None, records_before):
            save_book(self.book_path, self.book_entries, self.book_color)

    def _current_entries(self) -> list[BookEntry]:
        key = chess.polyglot.zobrist_hash(self.board)
        return list(self._index_entries_by_key().get(key, []))

    def _on_item_clicked(self, item: QListWidgetItem):
        entry: BookEntry = item.data(Qt.ItemDataRole.UserRole)
        move = decode_move(self.board, entry)
        if move is not None:
            self.play_move(move)

    def _on_item_hover_changed(self, item: QListWidgetItem | None):
        if item is None:
            self.board_widget.set_hover_arrow(None)
            return
        entry: BookEntry = item.data(Qt.ItemDataRole.UserRole)
        move = decode_move(self.board, entry)
        self.board_widget.set_hover_arrow((move.from_square, move.to_square) if move is not None else None)

    def _index_entries_by_key(self) -> dict[int, list[BookEntry]]:
        """Position key -> its entries. Built once and kept, so looking up a
        position doesn't scan the whole book; whoever replaces book_entries
        resets _key_index, appending an entry updates it in place."""
        if self._key_index is None:
            index: dict[int, list[BookEntry]] = {}
            for e in self.book_entries:
                index.setdefault(e.key, []).append(e)
            self._key_index = index
        return self._key_index

    def _backfill_resulting_keys(self, report=None):
        """Entries created this session (played moves, PGN import) already
        have resulting_key cached at creation time. Entries just loaded
        from a .bin file don't -- the Polyglot format has no such field --
        so walk the book once from the starting position to fill them in.
        Call this once per load, not on every refresh.

        report(fraction_done) is called periodically for progress display.
        Zobrist hashing dominates the cost, so each position's key travels
        with its board through the queue instead of being hashed twice."""
        if all(e.resulting_key is not None for e in self.book_entries):
            return  # nothing to backfill

        entries_by_key = self._index_entries_by_key()
        total = len(self.book_entries) or 1
        processed = 0
        start = chess.Board()
        start_key = chess.polyglot.zobrist_hash(start)
        visited: set[int] = {start_key}
        queue: deque[tuple[chess.Board, int]] = deque([(start, start_key)])

        while queue:
            board, key = queue.popleft()
            for e in entries_by_key.get(key, []):
                processed += 1
                if report is not None and processed % 2000 == 0:
                    report(min(processed / total, 1.0))
                move = decode_move(board, e)
                if move is None:
                    continue
                board.push(move)
                child_key = chess.polyglot.zobrist_hash(board)
                if e.resulting_key is None:
                    e.resulting_key = child_key
                if child_key not in visited:
                    visited.add(child_key)
                    queue.append((board.copy(stack=False), child_key))  # history not needed, copying it is slow
                board.pop()

    def _transposition_resulting_keys(self) -> set[int]:
        """Positions reached by more than one distinct edge -- i.e. the
        actual merge point where two move orders first converge.

        Deliberately in-degree, not path count: once two lines converge,
        every entry AFTER that merge point gets deduplicated down to a
        single stored edge by _record_book_move (same key + same move =
        same entry, just a higher weight). A cumulative path count would
        treat that single shared edge as "reachable 2 ways" and keep
        marking every move for the rest of the shared line; in-degree
        instead only flags the specific node where the convergence
        actually happens, which is what should be marked red -- not its
        downstream continuation.

        Walks the cached resulting_key edges instead of replaying moves on
        a board -- no move generation or hashing, so it stays fast for
        books with hundreds of thousands of entries."""
        entries_by_key = self._index_entries_by_key()

        in_degree: dict[int, int] = {}
        start_key = chess.polyglot.zobrist_hash(chess.Board())
        expanded: set[int] = {start_key}
        queue: deque[int] = deque([start_key])
        self._transposition_state = (in_degree, expanded)  # for _add_to_transposition_cache

        while queue:
            key = queue.popleft()
            for e in entries_by_key.get(key, []):
                child_key = e.resulting_key
                if child_key is None:
                    continue  # not reachable from the start position
                in_degree[child_key] = in_degree.get(child_key, 0) + 1
                if child_key not in expanded:
                    expanded.add(child_key)
                    queue.append(child_key)

        return {key for key, count in in_degree.items() if count > 1}

    def _add_to_transposition_cache(self, entry: BookEntry):
        """Updates the transposition cache for one newly added entry, so
        entering a move doesn't recompute the whole book: the same walk as
        _transposition_resulting_keys, continued from the new edge."""
        if self._transposition_cache is None:
            return  # will be computed from scratch on the next refresh
        in_degree, expanded = self._transposition_state
        if entry.key not in expanded:
            return  # not reachable from the start position
        entries_by_key = self._index_entries_by_key()
        pending = [entry]
        while pending:
            child_key = pending.pop().resulting_key
            if child_key is None:
                continue
            in_degree[child_key] = in_degree.get(child_key, 0) + 1
            if in_degree[child_key] > 1:
                self._transposition_cache.add(child_key)
            if child_key not in expanded:
                expanded.add(child_key)
                pending.extend(entries_by_key.get(child_key, []))

    def _reachable_keys(self, entries_by_key: dict[int, list[BookEntry]],
                        roots: set[int], skip: BookEntry | None = None) -> set[int]:
        """Positions reachable from `roots` via cached resulting_key edges,
        ignoring the entry `skip`."""
        reached = set(roots)
        queue: deque[int] = deque(roots)
        while queue:
            key = queue.popleft()
            for e in entries_by_key.get(key, []):
                if e is skip or e.resulting_key is None or e.resulting_key in reached:
                    continue
                reached.add(e.resulting_key)
                queue.append(e.resulting_key)
        return reached

    def _entries_orphaned_by(self, entry: BookEntry) -> list[BookEntry]:
        """entry plus every entry that can no longer be reached once entry is
        gone. Positions still reachable by another move order (transpositions)
        are kept. The current position counts as a root, so its subtree is
        found even if the start position does not lead there."""
        entries_by_key = self._index_entries_by_key()
        roots = {chess.polyglot.zobrist_hash(chess.Board()), entry.key}
        before = self._reachable_keys(entries_by_key, roots)
        after = self._reachable_keys(entries_by_key, roots, skip=entry)
        lost = before - after
        return [entry] + [e for e in self.book_entries if e.key in lost]

    def _remove_entries(self, doomed: list[BookEntry]):
        doomed_ids = {id(e) for e in doomed}  # list.remove per entry would be quadratic
        self.book_entries = [e for e in self.book_entries if id(e) not in doomed_ids]
        self._key_index = None

    def _move_lists_to(self, target_key: int, limit: int = 500) -> tuple[list[list[chess.Move]], bool]:
        """All move sequences from the starting position to target_key,
        found by walking resulting_key edges backwards. Returns at most
        `limit` lines (path counts can explode combinatorially) plus a flag
        telling whether the result was truncated."""
        start_key = chess.polyglot.zobrist_hash(chess.Board())
        entries_by_result: dict[int, list[BookEntry]] = {}
        for e in self.book_entries:
            if e.resulting_key is not None:
                entries_by_result.setdefault(e.resulting_key, []).append(e)

        paths: list[list[BookEntry]] = []
        on_path: set[int] = set()
        reversed_path: list[BookEntry] = []

        def walk(key: int) -> bool:
            # returns False once the limit is hit, to stop the whole search
            if key == start_key:
                paths.append(list(reversed(reversed_path)))
                return len(paths) < limit
            on_path.add(key)  # guards against cycles (e.g. Nf3 Nf6 Ng1 Ng8)
            for e in entries_by_result.get(key, []):
                if e.key in on_path:
                    continue
                reversed_path.append(e)
                keep_going = walk(e.key)
                reversed_path.pop()
                if not keep_going:
                    on_path.discard(key)
                    return False
            on_path.discard(key)
            return True

        truncated = not walk(target_key)

        move_lists: list[list[chess.Move]] = []
        for path in paths:
            board = chess.Board()
            moves: list[chess.Move] = []
            for e in path:
                move = decode_move(board, e)
                if move is None:
                    break  # stale/colliding entry -- drop this line
                moves.append(move)
                board.push(move)
            else:
                move_lists.append(moves)
        return move_lists, truncated

    def _show_transpositions(self, entry: BookEntry):
        move_lists, truncated = self._move_lists_to(entry.resulting_key)
        lines = sorted(((chess.Board().variation_san(moves), moves) for moves in move_lists), key=lambda line: line[0])
        move = decode_move(self.board, entry)
        current = self.game_moves[: self.ply] + [move] if move is not None else None
        TranspositionsDialog(lines, truncated, self._load_line, self, current).exec()

    def _on_line_context_menu(self, pos):
        index = self.line_table.indexAt(pos)
        if not index.isValid() or self.line_table.item(index.row(), index.column()) is None:
            return
        ply = index.row() * 2 + index.column() + 1
        moves = self.game_moves[:ply]
        menu = QMenu(self)
        play_action = menu.addAction("Autoplay from here")
        menu.addSeparator()
        copy_fen_action = menu.addAction("Copy FEN")
        copy_pgn_action = menu.addAction("Copy PGN")
        chosen = menu.exec(self.line_table.viewport().mapToGlobal(pos))
        if chosen == play_action:
            self._start_autoplay(ply)
        elif chosen == copy_fen_action:
            board = chess.Board()
            for move in moves:
                board.push(move)
            QApplication.clipboard().setText(board.fen())
        elif chosen == copy_pgn_action:
            # '*' = PGN result terminator (unknown), as in the Transpositions dialog
            QApplication.clipboard().setText(f"{chess.Board().variation_san(moves)} *\n")

    def _set_animation_speed(self, speed: str):
        self.board_widget.set_animation_speed(speed)
        _settings().setValue("animation_speed", speed)

    def _set_coordinates(self, mode: str):
        self.board_widget.set_coordinates(mode)
        _settings().setValue("coordinates", mode)

    def _set_play_speed(self, speed: str):
        self.play_speed = speed
        self._autoplay_timer.setInterval(PLAY_SPEEDS_MS[speed])  # also restarts a running playback at the new pace
        _settings().setValue("play_speed", speed)

    def _start_autoplay(self, ply: int):
        """Shows the position before move number `ply` of the current line,
        then plays the line move by move until its end. Any mouse click or
        key press stops it (and then does what it normally does)."""
        self.goto_ply(ply - 1)
        self._autoplay_timer.start()
        QApplication.instance().installEventFilter(self)
        self._update_status()

    def _stop_autoplay(self):
        if self._autoplay_timer.isActive():
            self._autoplay_timer.stop()
            QApplication.instance().removeEventFilter(self)
            self._update_status()

    def _autoplay_step(self):
        self.goto_ply(self.ply + 1)
        if self.ply >= len(self.game_moves):
            self._stop_autoplay()

    def eventFilter(self, obj, event):
        # installed only while "Autoplay from here" runs
        # ShortcutOverride: keys bound to a shortcut (arrows, F, E) never arrive as KeyPress
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            self._stop_autoplay()
        return super().eventFilter(obj, event)

    def _load_line(self, moves: list[chess.Move]):
        """Makes moves the current line and jumps to its end."""
        self.game_moves = list(moves)
        self.ply = len(self.game_moves)
        self._rebuild_board()
        self.refresh()

    def _on_context_menu(self, pos):
        item = self.move_list.itemAt(pos)
        if item is None:
            return
        entry: BookEntry = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        show_transpositions_action = edit_weight_action = delete_action = None
        if item.data(MoveItemDelegate.TRANSPOSITION_ROLE):
            show_transpositions_action = menu.addAction("Transpositions")
        if self.mode == "BUILD":  # View mode: read-only, no editing actions
            edit_weight_action = menu.addAction("Edit weight")
            delete_action = menu.addAction("Delete")
        if menu.isEmpty():
            return
        chosen = menu.exec(self.move_list.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == show_transpositions_action:
            self._show_transpositions(entry)
        elif chosen == edit_weight_action:
            self._edit_weight(entry)
        elif chosen == delete_action:
            self._delete_move(entry)

    def _edit_weight(self, entry: BookEntry):
        # polyglot stores the weight as an unsigned 16-bit value
        weight, ok = QInputDialog.getInt(
            self, " ", "Weight:", entry.weight, 1, 0xFFFF
        )
        if not ok or weight == entry.weight:
            return
        entry.weight = weight
        save_book(self.book_path, self.book_entries, self.book_color)
        self.refresh()

    def _delete_move(self, entry: BookEntry):
        move = decode_move(self.board, entry)
        if move is None:
            self._remove_entries([entry])
            self._transposition_cache = None
            save_book(self.book_path, self.book_entries, self.book_color)
            self.refresh()
            return

        doomed = self._entries_orphaned_by(entry)
        following = len(doomed) - 1

        if following > 0:
            question = f"Delete this move and {following} following move(s) from the book?"
        else:
            question = "Delete this move from the book?"
        reply = QMessageBox.question(
            self,
            "Delete move",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._remove_entries(doomed)
        self._transposition_cache = None
        save_book(self.book_path, self.book_entries, self.book_color)
        self.refresh()

    def refresh(self):
        self.board_widget.clear_selection()
        self.board_widget.animate_to_position()
        self.board_widget.set_hover_arrow(None)
        self.board_widget.set_engine_arrow(None)
        self.eval_label.setText("")  # stale until the engine reports for the new position
        self._populate_move_list()
        self._update_line_table()
        self._update_status()
        self.board_widget.redraw()
        self.btn_start.setEnabled(self.ply > 0)
        self.btn_back.setEnabled(self.ply > 0)
        at_end = self.ply >= len(self.game_moves)
        self.btn_forward.setEnabled(not at_end)
        self.btn_end.setEnabled(not at_end)
        if self.engine_active and self.engine_worker is not None:
            self.board_widget.set_engine_arrow(None)
            self.engine_worker.start(self.board)

    def _populate_move_list(self):
        self.move_list.clear()
        self.move_list.reset_hover()
        entries = sorted(self._current_entries(), key=lambda e: e.weight, reverse=True)
        if self._transposition_cache is None:
            self._transposition_cache = self._transposition_resulting_keys()
        transposition_keys = self._transposition_cache

        for entry in entries:
            move = decode_move(self.board, entry)
            if move is None:
                continue
            label = f"{self.board.san(move)} ({entry.weight})"
            is_transposition = entry.resulting_key in transposition_keys

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setData(MoveItemDelegate.TRANSPOSITION_ROLE, is_transposition)
            item.setForeground(QBrush(_icon_color()))
            self.move_list.addItem(item)

    def _update_line_table(self):
        board = chess.Board()
        sans = []
        for move in self.game_moves:
            sans.append(board.san(move))
            board.push(move)
        self.line_table.set_line(sans, self.ply)

    def _update_status(self):
        board = self.board
        if board.is_checkmate():
            msg = f"Checkmate — {'Black' if board.turn else 'White'} wins"
        elif board.is_stalemate():
            msg = "Stalemate"
        else:
            msg = "Check" if board.is_check() else ""
        if self._autoplay_timer.isActive():
            msg = "Playing — click to stop"
        self.status_label.setText(msg)
        color = f" ({self.book_color})" if self.book_color else ""
        self.book_label.setText(f"book: {self.book_path}{color}")
        self.book_label.setToolTip(self.book_path)


def main():
    book_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)  # also selects the per-user data folder
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(_desktop_file_name())  # Linux taskbar: see _desktop_file_name
    # window/taskbar icon; shipped next to otb.py (PyInstaller: --add-data)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "otb_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    _migrate_old_settings()
    window = MainWindow(book_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()