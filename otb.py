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
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSettings,
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
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

MIN_BOARD_SIZE = 320   # smallest the board will shrink to
RIGHT_PANEL_WIDTH = 280  # constant width for the nav+list panel
DRAG_THRESHOLD = 6  # px of mouse movement before a press counts as a drag

HOVER_ARROW_COLOR = "#ffcc00"         # yellow
ENGINE_ARROW_COLOR = "#0066ff"        # blue, continuously-updating engine best move
DRAG_SOURCE_COLOR = "#ffff0088"       # semi-transparent yellow for start square
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


ENGINE_ICON_PNG_B64 = (
    "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"
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(58, 32)

        self._knob_pos = 0.0  # 0.0 = left/off, 1.0 = right/on
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

        track_off = self.TRACK_OFF_COLOR.darker(120) if self._hovered else self.TRACK_OFF_COLOR
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
    """Wide Browse/Edit switch: grey track (inactive background); the
    knob itself is the colored element, sliding between green (Browse,
    the default) and red (Edit). Both labels are always visible, with
    only font weight (bold vs light) distinguishing the selected side,
    per spec. Sized to fill whatever width its layout slot gives it (see
    MainWindow: it spans the same two grid columns as the start/back
    buttons), not a fixed pixel width."""

    TRACK_COLOR = QColor("#bbbbbb")       # grey: inactive background
    KNOB_OFF_COLOR = QColor("#40a040")    # green: Browse
    KNOB_ON_COLOR = QColor("#a04040")     # red: Edit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._knob_pos = 0.0  # 0.0 = left/Browse, 1.0 = right/Edit
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

        browse_rect = QRectF(rect.left(), rect.top(), half_w, rect.height())
        edit_rect = QRectF(rect.left() + half_w, rect.top(), half_w, rect.height())
        browse_selected = self._knob_pos < 0.5

        painter.setPen(_icon_color())
        painter.setFont(bold_font if browse_selected else light_font)
        painter.drawText(browse_rect, Qt.AlignmentFlag.AlignCenter, "Browse")
        painter.setFont(light_font if browse_selected else bold_font)
        painter.drawText(edit_rect, Qt.AlignmentFlag.AlignCenter, "Edit")


# Mode board color schemes: {"square light": ..., "square dark": ...}
BOARD_COLORS = {
    "EDIT": {"square light": "#f2a4a4", "square dark": "#a04040"},    # light / dark red
    "BROWSE": {"square light": "#a4f2a4", "square dark": "#40a040"},  # light / dark green
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

    def _run(self, board: chess.Board):
        try:
            if self._engine is None:
                self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
                self._engine.configure({"Threads": self.THREADS, "Hash": self.HASH_MB})
            limit = chess.engine.Limit(time=self.ANALYSIS_TIME_LIMIT)
            with self._engine.analysis(board, limit) as analysis:
                self._analysis = analysis
                for info in analysis:
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
        colors = BOARD_COLORS.get(mode, BOARD_COLORS["BROWSE"])
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

        arrows = []
        if self.hover_arrow is not None:
            arrows.append(chess.svg.Arrow(self.hover_arrow[0], self.hover_arrow[1], color=HOVER_ARROW_COLOR))
        if self.engine_arrow is not None:
            arrows.append(chess.svg.Arrow(self.engine_arrow[0], self.engine_arrow[1], color=ENGINE_ARROW_COLOR))

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

class MoveItemDelegate(QStyledItemDelegate):
    """Paints the row separator line and the hover background by hand.
    Deliberately not done via QSS (QListWidget::item { ... }) -- applying
    any stylesheet to ::item makes Qt's CSS engine take over painting for
    that sub-control, which silently stops respecting a background set via
    item.setBackground()/Qt::BackgroundRole. Painting both ourselves avoids
    that conflict entirely."""

    SEPARATOR_COLOR = QColor("#cccccc")
    TRANSPOSITION_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, list_widget: "HoverListWidget"):
        super().__init__(list_widget)
        self.list_widget = list_widget

    def paint(self, painter, option, index):
        item = self.list_widget.item(index.row())
        super().paint(painter, option, index)
        if index.data(self.TRANSPOSITION_ROLE):
            painter.fillRect(option.rect, TRANSPOSITION_ROW_COLOR)
        if item is not None and item is self.list_widget.hovered_item:
            painter.fillRect(option.rect, HOVER_ROW_COLOR)  # translucent: blends on top
        painter.save()
        painter.setPen(self.SEPARATOR_COLOR)
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class HoverListWidget(QListWidget):
    hoverChanged = pyqtSignal(object)

    POLL_INTERVAL_MS = 80

    def __init__(self):
        super().__init__()
        self.hovered_item: QListWidgetItem | None = None
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


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, book_path: str | None):
        super().__init__()

        if book_path:
            self.book_path = book_path
        else:
            settings = QSettings("ChessRepertoire", "ChessRepertoireApp")
            stored_path = settings.value("book_path", type=str)
            if stored_path and os.path.exists(stored_path):
                self.book_path = stored_path
            else:
                self.book_path = "book.bin"
        self.book_entries: list[BookEntry] = load_book(self.book_path)
        self._backfill_resulting_keys()
        self._transposition_cache: set[int] | None = None
        self._update_window_title()

        self.game_moves: list[chess.Move] = []
        self.ply = 0
        self.board = chess.Board()

        self.mode = "BROWSE"

        self.engine_worker: EngineWorker | None = None
        self.engine_active = False

        self.board_widget = BoardWidget(lambda: self.board, lambda: self.mode, self.play_move)

        self.move_list = HoverListWidget()
        list_font = self.move_list.font()
        if list_font.pointSize() > 0:
            list_font.setPointSize(list_font.pointSize() * 2)
        else:
            list_font.setPixelSize(list_font.pixelSize() * 2)
        self.move_list.setFont(list_font)
        self.move_list.itemClicked.connect(self._on_item_clicked)
        self.move_list.hoverChanged.connect(self._on_item_hover_changed)
        self.move_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.move_list.customContextMenuRequested.connect(self._on_context_menu)

        self.btn_start = QPushButton()
        self.btn_start.setIcon(_make_skip_start_icon())
        self.btn_start.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_start.setToolTip("Go to start")

        self.btn_back = QPushButton()
        self.btn_back.setIcon(_make_step_back_icon())
        self.btn_back.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_back.setToolTip("Step back")

        self.btn_flip = QPushButton()
        self.btn_flip.setIcon(_make_flip_icon())
        self.btn_flip.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.btn_flip.setToolTip("Flip board")

        for btn in (self.btn_start, self.btn_back, self.btn_flip):
            btn.setStyleSheet(NAV_BUTTON_STYLE)

        self.engine_label = QLabel()
        self.engine_label.setToolTip("Engine")
        self.engine_toggle = ToggleSwitch()
        self.engine_toggle.setToolTip("Engine")

        self.mode_switch = ModeSwitch()
        self.mode_switch.setToolTip("Browse / Edit mode")

        nav_button_height = self.btn_start.sizeHint().height()
        self.mode_switch.setFixedHeight(nav_button_height)
        self.engine_toggle.setFixedSize(int(nav_button_height * 1.9), nav_button_height)
        self.engine_label.setPixmap(
            _make_engine_icon(nav_button_height).pixmap(nav_button_height, nav_button_height)
        )
        # self.mode == "BROWSE" is the default; knob starts unchecked/left (green)

        self.btn_start.clicked.connect(self.goto_start)
        self.btn_back.clicked.connect(self.step_back)
        self.btn_flip.clicked.connect(self.board_widget.flip)
        self.engine_toggle.toggled.connect(self._on_engine_toggle_changed)
        self.mode_switch.toggled.connect(lambda checked: self._set_mode("EDIT" if checked else "BROWSE"))

        nav_grid = QGridLayout()
        nav_grid.setHorizontalSpacing(6)
        nav_grid.setVerticalSpacing(6)
        # spans both columns, so it's exactly as wide as start+back combined
        nav_grid.addWidget(self.mode_switch, 0, 0, 1, 2)
        nav_grid.addWidget(self.btn_start, 1, 0)
        nav_grid.addWidget(self.btn_back, 1, 1)
        nav_grid.addWidget(self.btn_flip, 2, 0)
        engine_group = QHBoxLayout()
        engine_group.addWidget(self.engine_label)
        engine_group.addStretch()  # icon pinned left, switch pinned right
        engine_group.addWidget(self.engine_toggle)
        nav_grid.addLayout(engine_group, 2, 1)  # fills the cell: matches btn_back's left/right edges

        # Without this, column 1 (btn_back + engine_group) would size itself
        # wider than column 0 (btn_start/btn_flip alone), since the engine
        # group needs more room than a single icon-only button -- stretching
        # btn_back to match and breaking "all three buttons same size".
        # Forcing both columns to the same explicit minimum keeps every
        # button identical while still giving the engine group enough room.
        engine_group_width = self.engine_label.sizeHint().width() + 6 + self.engine_toggle.width()
        column_width = max(self.btn_start.sizeHint().width(), engine_group_width)
        nav_grid.setColumnMinimumWidth(0, column_width)
        nav_grid.setColumnMinimumWidth(1, column_width)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(nav_grid)
        right.addWidget(self.move_list)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(RIGHT_PANEL_WIDTH)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.board_widget)
        layout.addWidget(right_widget)
        self.setCentralWidget(central)

        self._build_menu()
        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(False)
        # showMessage() puts text in the *temporary* slot, which Qt clears
        # whenever a menu opens/closes (the menu pushes its own status tip).
        # A permanent widget is untouched by that, so the status text stays.
        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusBar().addWidget(self.status_label, 1)
        size_grip = ManualSizeGrip(self)
        self.statusBar().addPermanentWidget(size_grip)

        self.refresh()

    def _set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        self.import_pgn_action.setEnabled(self.mode == "EDIT")
        self.board_widget.redraw()
        self._update_status()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")

        self.import_pgn_action = QAction("Import PGN…", self)
        self.import_pgn_action.triggered.connect(self._import_pgn_dialog)
        self.import_pgn_action.setEnabled(self.mode == "EDIT")  # Browse mode: read-only
        file_menu.addAction(self.import_pgn_action)

        open_action = QAction("Open Book…", self)
        open_action.triggered.connect(self._open_book_dialog)
        file_menu.addAction(open_action)

        select_engine_action = QAction("Select Engine…", self)
        select_engine_action.triggered.connect(self._select_engine_dialog)
        file_menu.addAction(select_engine_action)

    def _select_engine_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select UCI engine executable", "", "All files (*)"
        )
        if path:
            settings = QSettings("ChessRepertoire", "ChessRepertoireApp")
            settings.setValue("engine_path", path)
            if self.engine_active:
                self._stop_engine()
                self.engine_worker = None
                self._start_engine()

    def _update_window_title(self):
        self.setWindowTitle(f"Opening Tree Builder — {os.path.basename(self.book_path)}")

    def _open_book_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Polyglot book", "", "Polyglot books (*.bin);;All files (*)"
        )
        if path:
            self.book_path = path
            self.book_entries = load_book(path)
            self._backfill_resulting_keys()
            self._transposition_cache = None
            QSettings("ChessRepertoire", "ChessRepertoireApp").setValue("book_path", path)
            self._update_window_title()
            self.refresh()

    def _import_pgn_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PGN", "", "PGN files (*.pgn);;All files (*)"
        )
        if not path:
            return
        try:
            game_count, move_count = self._import_pgn_file(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {game_count} game(s) from the PGN file, "
            f"adding/updating {move_count} move(s) in the book.",
        )

    def _import_pgn_file(self, path: str) -> tuple[int, int]:
        game_count = 0
        move_count = 0
        with open(path, encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                game_count += 1
                move_count += self._import_game_tree(game, game.board())
        save_book(self.book_path, self.book_entries)
        return game_count, move_count

    def _import_game_tree(self, node: chess.pgn.GameNode, board: chess.Board) -> int:
        count = 0
        for child in node.variations:
            move = child.move
            self._record_book_move(board, move, save=False)
            count += 1
            board.push(move)
            count += self._import_game_tree(child, board)
            board.pop()
        return count

    def goto_start(self):
        self.ply = 0
        self._rebuild_board()
        self.refresh()

    def step_back(self):
        if self.ply > 0:
            self.ply -= 1
            self._rebuild_board()
            self.refresh()

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
            settings = QSettings("ChessRepertoire", "ChessRepertoireApp")
            path = settings.value("engine_path", type=str)

            if not path or not os.path.exists(path):
                path, _ = QFileDialog.getOpenFileName(
                    self, "Select UCI engine executable", "", "All files (*)"
                )
                if not path:
                    self._sync_engine_toggle()  # user cancelled: uncheck again
                    return
                settings.setValue("engine_path", path)

            self.engine_worker = EngineWorker(path)
            self.engine_worker.best_move_found.connect(self._on_engine_best_move)
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
            except (TypeError, RuntimeError):
                pass
            self.engine_worker.stop()
            self.engine_worker = None

        self.board_widget.set_engine_arrow(None)
        self.refresh()

    def _on_engine_best_move(self, from_square: int, to_square: int):
        self.board_widget.set_engine_arrow((from_square, to_square))

    def _on_engine_error(self, message: str):
        self._stop_engine()
        QMessageBox.warning(self, "Engine error", message)

    def closeEvent(self, event):
        if self.engine_worker is not None:
            self.engine_worker.quit_engine()
        super().closeEvent(event)

    def play_move(self, move: chess.Move):
        if self.mode == "EDIT":
            self._record_book_move(self.board, move)
        if self.ply < len(self.game_moves) and move == self.game_moves[self.ply]:
            self.ply += 1
        else:
            self.game_moves = self.game_moves[: self.ply] + [move]
            self.ply += 1
        self._rebuild_board()
        self.refresh()

    def _record_book_move(self, board_before: chess.Board, move: chess.Move, save: bool = True):
        key = chess.polyglot.zobrist_hash(board_before)
        from_sq, to_sq, promo = encode_move(board_before, move)
        for e in self.book_entries:
            if e.key == key and e.from_square == from_sq and e.to_square == to_sq and e.promotion == promo:
                e.weight += 1
                break
        else:
            board_after = board_before.copy()
            board_after.push(move)
            resulting_key = chess.polyglot.zobrist_hash(board_after)
            self.book_entries.append(BookEntry(key, from_sq, to_sq, promo, 1, 0, resulting_key))
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

    def _backfill_resulting_keys(self):
        """Entries created this session (played moves, PGN import) already
        have resulting_key cached at creation time. Entries just loaded
        from a .bin file don't -- the Polyglot format has no such field --
        so walk the book once from the starting position to fill them in.
        Call this once per load, not on every refresh."""
        if all(e.resulting_key is not None for e in self.book_entries):
            return  # nothing to backfill

        entries_by_key = self._index_entries_by_key()
        visited: set[int] = set()
        queue: deque[chess.Board] = deque([chess.Board()])
        visited.add(chess.polyglot.zobrist_hash(queue[0]))

        while queue:
            board = queue.popleft()
            key = chess.polyglot.zobrist_hash(board)
            for e in entries_by_key.get(key, []):
                move = decode_move(board, e)
                if move is None:
                    continue
                board.push(move)
                child_key = chess.polyglot.zobrist_hash(board)
                if e.resulting_key is None:
                    e.resulting_key = child_key
                if child_key not in visited:
                    visited.add(child_key)
                    queue.append(board.copy())
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
        downstream continuation."""
        entries_by_key = self._index_entries_by_key()

        in_degree: dict[int, int] = {}
        expanded: set[int] = set()

        start = chess.Board()
        expanded.add(chess.polyglot.zobrist_hash(start))
        queue: deque[chess.Board] = deque([start])

        while queue:
            board = queue.popleft()
            key = chess.polyglot.zobrist_hash(board)
            for e in entries_by_key.get(key, []):
                move = decode_move(board, e)
                if move is None:
                    continue
                board.push(move)
                child_key = chess.polyglot.zobrist_hash(board)
                in_degree[child_key] = in_degree.get(child_key, 0) + 1
                if child_key not in expanded:
                    expanded.add(child_key)
                    queue.append(board.copy())
                board.pop()

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

    def _on_context_menu(self, pos):
        if self.mode != "EDIT":
            return  # Browse mode: read-only, no delete available
        item = self.move_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self.move_list.mapToGlobal(pos))
        if chosen != delete_action:
            return

        entry: BookEntry = item.data(Qt.ItemDataRole.UserRole)
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
        self.board_widget.set_hover_arrow(None)
        self.board_widget.set_engine_arrow(None)
        self._populate_move_list()
        self._update_status()
        self.board_widget.redraw()
        self.btn_start.setEnabled(self.ply > 0)
        self.btn_back.setEnabled(self.ply > 0)
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
            label = self.board.san(move)
            is_transposition = entry.resulting_key in transposition_keys

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setData(MoveItemDelegate.TRANSPOSITION_ROLE, is_transposition)
            item.setForeground(QBrush(_icon_color()))
            self.move_list.addItem(item)

    def _update_status(self):
        board = self.board
        mode_str = f"[{self.mode} mode]"
        if board.is_checkmate():
            msg = f"{mode_str} Checkmate — {'Black' if board.turn else 'White'} wins"
        elif board.is_stalemate():
            msg = f"{mode_str} Stalemate"
        else:
            side = "White" if board.turn else "Black"
            check = " (check)" if board.is_check() else ""
            msg = (
                f"{mode_str} {side} to move{check} — ply {self.ply}/{len(self.game_moves)} "
                f"— book: {self.book_path}"
            )
        self.status_label.setText(msg)


def main():
    book_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    window = MainWindow(book_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()