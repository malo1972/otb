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
import os
import re
import struct
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
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
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
RIGHT_PANEL_WIDTH = 280  # constant width for the nav+list panel
LINE_PANEL_WIDTH = RIGHT_PANEL_WIDTH  # current-line score sheet + nav buttons, same width as the right panel
DRAG_THRESHOLD = 6  # px of mouse movement before a press counts as a drag

HOVER_ARROW_COLOR = "#ffcc00"         # yellow
ENGINE_ARROW_COLOR = "#0066ff"        # blue, continuously-updating engine best move
DRAG_SOURCE_COLOR = "#ffff0088"       # semi-transparent yellow for start square
APP_VERSION = "1.0"
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
TARGET_SQUARE_COLOR = "#3388ff88"     # semi-transparent blue for target squares

NAV_BUTTON_STYLE = (
    "QPushButton { padding: 10px 18px; font-size: 12pt; }"
    "QPushButton:hover:enabled { background-color: #888888; }"
)
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
    "VIEW": {"square light": "#a4f2a4", "square dark": "#40a040"},  # light / dark green
}

PROMO_TO_CODE = {None: 0, chess.KNIGHT: 1, chess.BISHOP: 2, chess.ROOK: 3, chess.QUEEN: 4}
CODE_TO_PROMO = {v: k for k, v in PROMO_TO_CODE.items()}

_ARROW_PAIR_RE = re.compile(
    r'(<line\b[^>]*class="arrow"[^>]*>)\s*(<polygon\b[^>]*class="arrow"[^>]*>)'
)
_STROKE_WIDTH_RE = re.compile(r'stroke-width="([\d.]+)"')
_POINTS_RE = re.compile(r'points="([^"]+)"')
_X2_RE = re.compile(r'x2="[^"]+"')
_Y2_RE = re.compile(r'y2="[^"]+"')
ARROW_THIN_FACTOR = 0.5


def _thin_arrows(svg_data: str) -> str:
    """chess.svg.Arrow has no thickness option: the shaft is a <line> that
    stops short to make room for a fixed-size <polygon> arrowhead. Shrink
    both by ARROW_THIN_FACTOR, keeping the polygon's tip (its first point)
    anchored -- and pull the line's endpoint in to meet the new, smaller
    polygon base, so there's no gap between shaft and head."""

    def shrink_pair(match: re.Match) -> str:
        line_tag, poly_tag = match.group(1), match.group(2)

        line_tag = _STROKE_WIDTH_RE.sub(
            lambda m: f'stroke-width="{float(m.group(1)) * ARROW_THIN_FACTOR:g}"', line_tag
        )

        pts_match = _POINTS_RE.search(poly_tag)
        if not pts_match:
            return line_tag + poly_tag
        points = [tuple(map(float, p.split(","))) for p in pts_match.group(1).split()]
        if len(points) != 3:
            return line_tag + poly_tag

        tip_x, tip_y = points[0]
        scaled = [points[0]] + [
            (tip_x + (x - tip_x) * ARROW_THIN_FACTOR, tip_y + (y - tip_y) * ARROW_THIN_FACTOR)
            for x, y in points[1:]
        ]
        new_points = " ".join(f"{x:g},{y:g}" for x, y in scaled)
        poly_tag = _POINTS_RE.sub(f'points="{new_points}"', poly_tag)

        mid_x = (scaled[1][0] + scaled[2][0]) / 2
        mid_y = (scaled[1][1] + scaled[2][1]) / 2
        line_tag = _X2_RE.sub(f'x2="{mid_x:g}"', line_tag)
        line_tag = _Y2_RE.sub(f'y2="{mid_y:g}"', line_tag)

        return line_tag + poly_tag

    return _ARROW_PAIR_RE.sub(shrink_pair, svg_data)


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
    macOS ~/Library/Application Support/GambitGear/OTB."""
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "book.bin")


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


def load_book(path: str) -> list[BookEntry]:
    entries: list[BookEntry] = []
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return entries
    for offset in range(0, len(data) - 15, 16):
        key, mv, weight, learn = struct.unpack_from(">QHHI", data, offset)
        to_sq = mv & 0x3F
        from_sq = (mv >> 6) & 0x3F
        promo = (mv >> 12) & 0x7
        entries.append(BookEntry(key, from_sq, to_sq, promo, weight, learn))
    return entries


def save_book(path: str, entries: list[BookEntry]) -> None:
    ordered = sorted(entries, key=lambda e: e.key)
    with open(path, "wb") as f:
        for e in ordered:
            mv = (e.promotion << 12) | (e.from_square << 6) | e.to_square
            f.write(struct.pack(">QHHI", e.key, mv, e.weight, e.learn))


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
                self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
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

        self.renderer = QSvgRenderer()
        self.setMinimumSize(MIN_BOARD_SIZE, MIN_BOARD_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.redraw()

    def set_hover_arrow(self, arrow: tuple[int, int] | None):
        self.hover_arrow = arrow
        self.redraw()

    def set_engine_arrow(self, arrow: tuple[int, int] | None):
        self.engine_arrow = arrow
        self.redraw()

    def flip(self):
        self.orientation = not self.orientation
        self.redraw()

    def board_rect(self) -> QRectF:
        w = float(self.width())
        h = float(self.height())
        side = min(w, h)
        return QRectF(0.0, 0.0, side, side)

    def redraw(self):
        board = self.get_board()
        mode = self.get_mode()
        colors = BOARD_COLORS.get(mode, BOARD_COLORS["VIEW"])
        display_board = board
        fill = {}

        if self.selected is not None:
            # a piece is actually selected (clicked): show it and where it can go
            piece = board.piece_at(self.selected)
            if piece is not None and piece.color == board.turn:
                fill[self.selected] = DRAG_SOURCE_COLOR
                for target in self._legal_targets(board, self.selected):
                    fill[target] = TARGET_SQUARE_COLOR
        elif self.hover_square is not None:
            # merely hovering: highlight the start square only, no targets
            piece = board.piece_at(self.hover_square)
            if piece is not None and piece.color == board.turn:
                fill[self.hover_square] = DRAG_SOURCE_COLOR

        if self.selected is not None and self.dragging:
            display_board = board.copy()
            display_board.remove_piece_at(self.selected)

        # SVG paints in list order, so the hover arrow goes last to stay on
        # top; if it shows the engine's move, the blue arrow is left out.
        arrows = []
        if self.engine_arrow is not None and self.engine_arrow != self.hover_arrow:
            arrows.append(chess.svg.Arrow(self.engine_arrow[0], self.engine_arrow[1], color=ENGINE_ARROW_COLOR))
        if self.hover_arrow is not None:
            arrows.append(chess.svg.Arrow(self.hover_arrow[0], self.hover_arrow[1], color=HOVER_ARROW_COLOR))

        lastmove = board.move_stack[-1] if board.move_stack else None
        svg_data = chess.svg.board(
            board=display_board,
            lastmove=lastmove,
            fill=fill,
            arrows=arrows,
            colors=colors,
            orientation=self.orientation,
            coordinates=False,
            check=board.king(board.turn) if board.is_check() else None,
        )

        self.renderer.load(_thin_arrows(svg_data).encode("utf-8"))
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.renderer.render(painter, self.board_rect())

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

class ManualSizeGrip(QWidget):
    GRIP_SIZE = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.GRIP_SIZE, self.GRIP_SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self._dragging = False
        self._drag_start_pos: QPoint | None = None
        self._start_size = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = painter.pen()
        pen.setColor(self.palette().color(self.foregroundRole()))
        pen.setWidth(2)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        for offset in (6, 13, 20):
            painter.drawLine(w - offset, h - 2, w - 2, h - offset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._start_size = self.window().size()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.globalPosition().toPoint() - self._drag_start_pos
        window = self.window()
        new_width = max(window.minimumWidth(), self._start_size.width() + delta.x())
        new_height = max(window.minimumHeight(), self._start_size.height() + delta.y())
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
    one PGN movetext line per row. Left-click loads a line via
    on_select(moves), right-click copies its PGN."""

    def __init__(self, lines: list[tuple[str, list[chess.Move]]], truncated: bool, on_select, parent=None):
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
        layout.addWidget(QLabel(caption + ".\nLeft-click a line to load it, right-click to copy the PGN."))
        layout.addWidget(SeparatorFrame(self.list_widget))  # same outer frame as the move lists
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

        self.btn_start = QPushButton()
        self.btn_start.setIcon(_make_skip_start_icon())
        self.btn_start.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_start.setToolTip("Go to start (Home)")

        self.btn_back = QPushButton()
        self.btn_back.setIcon(_make_step_back_icon())
        self.btn_back.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_back.setToolTip("Step back (←)")

        self.btn_forward = QPushButton()
        self.btn_forward.setIcon(_make_step_forward_icon())
        self.btn_forward.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_forward.setToolTip("Step forward (→)")

        self.btn_end = QPushButton()
        self.btn_end.setIcon(_make_skip_end_icon())
        self.btn_end.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_end.setToolTip("Go to end (End)")

        self.btn_flip = QPushButton()
        self.btn_flip.setIcon(_make_flip_icon())
        self.btn_flip.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_flip.setToolTip("Flip board (F)")

        for btn in (self.btn_start, self.btn_back, self.btn_forward, self.btn_end, self.btn_flip):
            btn.setStyleSheet(NAV_BUTTON_STYLE)
            # no keyboard focus: avoids the dotted focus frame some styles
            # (Windows) draw; the keys work through window-wide shortcuts
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.engine_label = QLabel()
        self.engine_toggle = ToggleSwitch()

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
        self.statusBar().addWidget(self.eval_label)  # leftmost, before the status text
        # eval | check/mate message ............ book path | size grip
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

        self.refresh()

    def _set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        self.import_pgn_action.setEnabled(self.mode == "BUILD")
        self.board_widget.redraw()
        self._update_status()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")

        self.import_pgn_action = QAction("Import PGN…", self)
        self.import_pgn_action.triggered.connect(self._import_pgn_dialog)
        self.import_pgn_action.setEnabled(self.mode == "BUILD")  # View mode: read-only
        file_menu.addAction(self.import_pgn_action)

        open_action = QAction("Open Book…", self)
        open_action.triggered.connect(self._open_book_dialog)
        file_menu.addAction(open_action)

        select_engine_action = QAction("Select Engine…", self)
        select_engine_action.triggered.connect(self._select_engine_dialog)
        file_menu.addAction(select_engine_action)

        search_menu = self.menuBar().addMenu("Search")
        search_fen_action = QAction("by FEN…", self)
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
            "<p><i>File > Import PGN…</i> adds whole games (build mode).</p>"
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
            "<hr>"
            "<p>For open-source chess broadcasting hard- and software, tournaments and more visit:</p>"
            '<p style="font-size: x-large;">'
            '<a href="https://www.gambitgear.ch">www.gambitgear.ch</a></p>'
        )
        box.exec()

    NO_ENGINE_HINT = "Please select an engine first via File → Select Engine…"

    @staticmethod
    def _engine_path() -> str | None:
        path = _settings().value("engine_path", type=str)
        return path if path and os.path.exists(path) else None

    def _update_engine_availability(self):
        """Engine switch is unavailable (faded, explains itself) until a
        valid engine executable has been selected, e.g. right after install."""
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
        box.setInformativeText(
            "OTB works with any UCI chess engine, e.g. Stockfish (free, stockfishchess.org)."
        )
        select_button = box.addButton("Select Engine…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is select_button:
            self._select_engine_dialog()

    def _select_engine_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select UCI engine executable", "", "All files (*)"
        )
        if path:
            settings = _settings()
            settings.setValue("engine_path", path)
            self._update_engine_availability()
            if self.engine_active:
                self._stop_engine()
                self.engine_worker = None
                self._start_engine()

    def _open_book_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Polyglot book", "", "Polyglot books (*.bin);;All files (*)"
        )
        if path:
            self.book_path = path
            self._load_book(path)
            _settings().setValue("book_path", path)
            self.refresh()

    def _import_pgn_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PGN", "", "PGN files (*.pgn);;All files (*)"
        )
        if not path:
            return

        progress = self._make_progress("Importing PGN…", cancellable=True)

        def report(fraction: float, game_count: int) -> bool:
            progress.setValue(int(fraction * 1000))
            progress.setLabelText(f"Importing PGN… {game_count} games")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            result = self._import_pgn_file(path, report)
        except Exception as exc:  # noqa: BLE001
            progress.close()
            self._load_book(self.book_path)  # drop the partial in-memory import
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        if result is None:  # cancelled: nothing was saved, restore the book
            progress.close()
            self._load_book(self.book_path)
            return
        game_count, move_count = result
        progress.setLabelText("Updating view…")
        QApplication.processEvents()
        self.refresh()
        progress.close()
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {game_count} game(s) from the PGN file, "
            f"adding/updating {move_count} move(s) in the book.",
        )

    def _import_pgn_file(self, path: str, report=None) -> tuple[int, int] | None:
        """report(fraction_done, game_count) -> keep_going is called every
        few games; returns None (book left unsaved) if it asks to stop."""
        game_count = 0
        move_count = 0
        total_size = os.path.getsize(path) or 1
        index = {(e.key, e.from_square, e.to_square, e.promotion): e for e in self.book_entries}
        with open(path, encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                game_count += 1
                move_count += self._import_game_tree(game, game.board(), index)
                if report is not None and game_count % 20 == 0:
                    if not report(min(f.tell() / total_size, 1.0), game_count):
                        return None
        save_book(self.book_path, self.book_entries)
        return game_count, move_count

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

        self.book_entries = load_book(path)
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
            settings = _settings()
            path = settings.value("engine_path", type=str)

            if not path or not os.path.exists(path):
                path, _ = QFileDialog.getOpenFileName(
                    self, "Select UCI engine executable", "", "All files (*)"
                )
                if not path:
                    self._sync_engine_toggle()  # user cancelled: uncheck again
                    return
                settings.setValue("engine_path", path)
                self._update_engine_availability()

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
        imports; without it every call scans the whole book, which makes
        importing a big PGN quadratic."""
        key = chess.polyglot.zobrist_hash(board_before)
        from_sq, to_sq, promo = encode_move(board_before, move)
        if index is not None:
            existing = index.get((key, from_sq, to_sq, promo))
        else:
            existing = next(
                (e for e in self.book_entries
                 if e.key == key and e.from_square == from_sq and e.to_square == to_sq and e.promotion == promo),
                None,
            )
        if existing is not None:
            existing.weight = min(existing.weight + 1, 0xFFFF)  # polyglot weight is 16-bit
        else:
            # push/pop instead of copy(): copy() duplicates the whole move stack
            board_before.push(move)
            resulting_key = chess.polyglot.zobrist_hash(board_before)
            board_before.pop()
            entry = BookEntry(key, from_sq, to_sq, promo, 1, 0, resulting_key)
            self.book_entries.append(entry)
            if index is not None:
                index[(key, from_sq, to_sq, promo)] = entry
            self._transposition_cache = None  # graph structure changed
        if save:
            save_book(self.book_path, self.book_entries)

    def _current_entries(self) -> list[BookEntry]:
        key = chess.polyglot.zobrist_hash(self.board)
        return [e for e in self.book_entries if e.key == key]

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
        index: dict[int, list[BookEntry]] = {}
        for e in self.book_entries:
            index.setdefault(e.key, []).append(e)
        return index

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

    def _collect_subtree(self, board_after_move: chess.Board, entry: BookEntry) -> list[BookEntry]:
        collected = [entry]
        visited: set[int] = {entry.key}

        def walk(board: chess.Board):
            key = chess.polyglot.zobrist_hash(board)
            if key in visited:
                return
            visited.add(key)
            for e in self.book_entries:
                if e.key == key:
                    move = decode_move(board, e)
                    if move is None:
                        continue
                    collected.append(e)
                    board.push(move)
                    walk(board)
                    board.pop()

        walk(board_after_move)
        return collected

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
        TranspositionsDialog(lines, truncated, self._load_line, self).exec()

    def _on_line_context_menu(self, pos):
        index = self.line_table.indexAt(pos)
        if not index.isValid() or self.line_table.item(index.row(), index.column()) is None:
            return
        ply = index.row() * 2 + index.column() + 1
        moves = self.game_moves[:ply]
        menu = QMenu(self)
        copy_fen_action = menu.addAction("Copy FEN")
        copy_pgn_action = menu.addAction("Copy PGN")
        chosen = menu.exec(self.line_table.viewport().mapToGlobal(pos))
        if chosen == copy_fen_action:
            board = chess.Board()
            for move in moves:
                board.push(move)
            QApplication.clipboard().setText(board.fen())
        elif chosen == copy_pgn_action:
            # '*' = PGN result terminator (unknown), as in the Transpositions dialog
            QApplication.clipboard().setText(f"{chess.Board().variation_san(moves)} *\n")

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
        save_book(self.book_path, self.book_entries)
        self.refresh()

    def _delete_move(self, entry: BookEntry):
        move = decode_move(self.board, entry)
        if move is None:
            self.book_entries.remove(entry)
            self._transposition_cache = None
            save_book(self.book_path, self.book_entries)
            self.refresh()
            return

        board_after = self.board.copy()
        board_after.push(move)
        subtree = self._collect_subtree(board_after, entry)
        following = len(subtree) - 1

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

        for e in subtree:
            self.book_entries.remove(e)
        self._transposition_cache = None
        save_book(self.book_path, self.book_entries)
        self.refresh()

    def refresh(self):
        self.board_widget.clear_selection()
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
        self.status_label.setText(msg)
        self.book_label.setText(f"book: {self.book_path}")
        self.book_label.setToolTip(self.book_path)


def main():
    book_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)  # also selects the per-user data folder
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
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