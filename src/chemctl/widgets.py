"""Animated, custom-painted widgets for the desktop client. Pure QPainter; they never fetch data."""
import math
import random

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QTimer, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget

TEAL, BLUE, VIOLET, RED, MUTED = "#2dd4bf", "#38bdf8", "#8b5cf6", "#f47c7c", "#8a9bb0"


def count_to(target, value):
    """Roll an integer label up from 0."""
    target.setText("0")
    animation = QVariantAnimation(target)
    animation.setStartValue(0.0)
    animation.setEndValue(float(value))
    animation.setDuration(700)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.valueChanged.connect(lambda v: target.setText(str(round(v))))
    animation.start(QVariantAnimation.DeleteWhenStopped)


class Animated(QWidget):
    """Runs tick() only while the widget is on screen."""
    interval = 33

    def __init__(self):
        super().__init__()
        self.clock = QTimer(self)
        self.clock.setInterval(self.interval)
        self.clock.timeout.connect(self.step)

    def step(self):
        self.tick()
        self.update()

    def tick(self):
        pass

    def showEvent(self, event):
        self.clock.start()

    def hideEvent(self, event):
        self.clock.stop()


class Nav(QWidget):
    """Sidebar navigation with a pill that slides to the current entry."""
    currentRowChanged = Signal(int)

    def __init__(self, names):
        super().__init__()
        self.row = -1
        self.pill = QFrame(self)
        self.pill.setObjectName("navPill")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.buttons = []
        for index, name in enumerate(names):
            item = QPushButton(name)
            item.setObjectName("nav")
            item.setCheckable(True)
            item.setCursor(Qt.PointingHandCursor)
            item.clicked.connect(lambda _=False, index=index: self.setCurrentRow(index))
            layout.addWidget(item)
            self.buttons.append(item)
        layout.addStretch()
        self.slide = QPropertyAnimation(self.pill, b"geometry", self)
        self.slide.setDuration(380)
        self.slide.setEasingCurve(QEasingCurve.OutBack)

    def setCurrentRow(self, index):
        for position, item in enumerate(self.buttons):
            item.setChecked(position == index)
        if index == self.row:
            return
        animated, self.row = self.row >= 0, index
        self.slide.stop()
        if animated:
            self.slide.setStartValue(self.pill.geometry())
            self.slide.setEndValue(self.buttons[index].geometry())
            self.slide.start()
        else:
            self.pill.setGeometry(self.buttons[index].geometry())
        self.currentRowChanged.emit(index)

    def resizeEvent(self, event):
        if self.row >= 0:
            self.slide.stop()
            self.pill.setGeometry(self.buttons[self.row].geometry())
        self.pill.lower()


class Pulse(Animated):
    """Status dot with an expanding ring."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(16, 16)
        self.color, self.phase = QColor(MUTED), 0.0

    def set_color(self, color):
        self.color = QColor(color)

    def tick(self):
        self.phase = (self.phase + 0.025) % 1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ring = QColor(self.color)
        ring.setAlphaF(0.55 * (1 - self.phase))
        p.setPen(QPen(ring, 1.4))
        p.drawEllipse(QPointF(8, 8), 3 + 4.5 * self.phase, 3 + 4.5 * self.phase)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QPointF(8, 8), 3.2, 3.2)


class Spinner(Animated):
    def __init__(self):
        super().__init__()
        self.setFixedSize(36, 36)
        self.angle = 0

    def tick(self):
        self.angle = (self.angle + 9) % 360

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#1f2b3c"), 3))
        p.drawEllipse(QRectF(5, 5, 26, 26))
        p.setPen(QPen(QColor(TEAL), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(5, 5, 26, 26), -self.angle * 16, 100 * 16)


class Hero(Animated):
    """Overview header: gradient with a drifting node network. Decorative only; it shows no data."""

    def __init__(self):
        super().__init__()
        self.setObjectName("hero")
        self.setFixedHeight(176)
        rng = random.Random(11)
        palette = [TEAL, BLUE, VIOLET, "#e6ecf5"]
        self.nodes = [{"x": rng.random(), "y": rng.random(), "vx": rng.uniform(-1, 1) * 0.0011, "vy": rng.uniform(-1, 1) * 0.0022,
                       "color": QColor(rng.choice(palette)), "r": rng.uniform(2.2, 4.6)} for _ in range(30)]
        self.ring = 0  # frames left of the benzene formation

    def benzene(self):
        self.ring = 240

    def ring_target(self, index):
        radius = 34 if index < 6 else 62
        angle = math.radians(60 * (index % 6) + 30)
        return (self.width() * 0.76 + radius * math.cos(angle)) / self.width(), (self.height() * 0.5 + radius * math.sin(angle)) / self.height()

    def tick(self):
        self.ring = max(0, self.ring - 1)
        for index, n in enumerate(self.nodes):
            if self.ring and index < 12:
                tx, ty = self.ring_target(index)
                n["x"] += (tx - n["x"]) * 0.09
                n["y"] += (ty - n["y"]) * 0.09
                continue
            n["x"] += n["vx"]
            n["y"] += n["vy"]
            if not 0 < n["x"] < 1:
                n["vx"] = -n["vx"]
            if not 0 < n["y"] < 1:
                n["vy"] = -n["vy"]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 16, 16)
        p.setClipPath(clip)
        background = QLinearGradient(0, 0, w, h)
        for stop, color in ((0, "#0d3b40"), (0.5, "#16224f"), (1, "#35185c")):
            background.setColorAt(stop, QColor(color))
        p.fillRect(self.rect(), background)
        glow = QRadialGradient(w * 0.78, h * 0.4, h * 1.1)
        glow.setColorAt(0, QColor(139, 92, 246, 70))
        glow.setColorAt(1, QColor(139, 92, 246, 0))
        p.fillRect(self.rect(), glow)
        points = [(n["x"] * w, n["y"] * h) for n in self.nodes]
        for i, (x1, y1) in enumerate(points):
            for j in range(i + 1, len(points)):
                x2, y2 = points[j]
                if self.ring and i < 12 and j < 12:
                    linked = (i < 6 and j < 6 and (j - i) in (1, 5)) or j == i + 6
                    alpha = 210 if linked else 0
                else:
                    distance = math.hypot(x2 - x1, y2 - y1)
                    alpha = int(110 * (1 - distance / 130)) if distance < 130 else 0
                if alpha:
                    p.setPen(QPen(QColor(190, 225, 255, alpha), 1.1))
                    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(Qt.NoPen)
        for n, (x, y) in zip(self.nodes, points):
            halo = QColor(n["color"])
            halo.setAlpha(45)
            p.setBrush(halo)
            p.drawEllipse(QPointF(x, y), n["r"] * 2.6, n["r"] * 2.6)
            p.setBrush(n["color"])
            p.drawEllipse(QPointF(x, y), n["r"], n["r"])
        veil = QLinearGradient(0, 0, w * 0.62, 0)  # keeps the text on the left readable
        veil.setColorAt(0, QColor(9, 28, 40, 215))
        veil.setColorAt(1, QColor(9, 28, 40, 0))
        p.fillRect(self.rect(), veil)


class Progress(Animated):
    """Gradient bar that eases toward its value, with a moving sheen while active."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(14)
        self.target = self.shown = 0.0
        self.active = self.unknown = False
        self.phase = 0.0

    def set(self, done, total, active):
        self.active, self.unknown = active, active and not total
        self.target = done / total if total else (0.0 if active else self.target)

    def tick(self):
        self.shown += (self.target - self.shown) * 0.16
        self.phase = (self.phase + 0.018) % 1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.fillPath(track, QColor("#131b28"))
        p.setClipPath(track)
        fill = QLinearGradient(0, 0, w, 0)
        for stop, color in ((0, TEAL), (0.6, BLUE), (1, VIOLET)):
            fill.setColorAt(stop, QColor(color))
        if self.unknown:
            start = (self.phase * 1.4 - 0.4) * w
            p.fillRect(QRectF(start, 0, w * 0.4, h), fill)
            return
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(0, 0, w * self.shown, h), h / 2, h / 2)
        p.fillPath(bar, fill)
        if self.active:
            p.setClipPath(bar)
            sheen = QLinearGradient(0, 0, 80, 0)
            sheen.setColorAt(0, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.5, QColor(255, 255, 255, 110))
            sheen.setColorAt(1, QColor(255, 255, 255, 0))
            p.translate(self.phase * (w + 80) - 80, 0)
            p.fillRect(QRectF(0, 0, 80, h), sheen)


class Chart(QWidget):
    """Plot of the rows currently loaded in the neighbouring table. Values are drawn as given; hover reads them back.

    line: y against sequence position.  marks: positions on a value axis (no intensity is implied).
    """

    def __init__(self, title, unit, marks=False):
        super().__init__()
        self.title, self.unit, self.marks = title, unit, marks
        self.points, self.reveal, self.hover = [], 1.0, None
        self.setMinimumWidth(240)
        self.setMouseTracking(True)
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(650)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self.set_reveal)

    def set_reveal(self, value):
        self.reveal = value
        self.update()

    def set(self, points):
        """points: (label, value) pairs; rows without a value are left out by the caller."""
        self.points, self.hover = points, None
        self.animation.stop()
        self.animation.start()

    def area(self):
        return QRectF(16, 44, self.width() - 32, self.height() - 76)

    def positions(self):
        area, values = self.area(), [v for _, v in self.points]
        low, high = min(values), max(values)
        if self.marks:
            low, high = min(low, 0.0), max(high, 0.0)
        span = (high - low) or 1.0
        if self.marks:
            return [QPointF(area.left() + (v - low) / span * area.width(), area.bottom()) for v in values], low, high
        step = area.width() / max(1, len(values) - 1)
        middle = len(values) == 1
        return [QPointF(area.center().x() if middle else area.left() + i * step,
                        area.center().y() if high == low else area.bottom() - (v - low) / span * area.height())
                for i, v in enumerate(values)], low, high

    def mouseMoveEvent(self, event):
        if self.points:
            spots, _, _ = self.positions()
            x = event.position().x()
            self.hover = min(range(len(spots)), key=lambda i: abs(spots[i].x() - x))
            self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        p.fillPath(frame, QColor("#0e141e"))
        p.setPen(QPen(QColor("#1f2b3c"), 1))
        p.drawPath(frame)
        p.setPen(QColor("#cfd9e6"))
        p.drawText(QRectF(16, 10, self.width() - 32, 20), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        area = self.area()
        if not self.points:
            p.setPen(QColor(MUTED))
            p.drawText(area, Qt.AlignCenter, "当前页没有可绘制的数值")
            return
        spots, low, high = self.positions()
        mono = QFont("Consolas", 9)
        p.setFont(mono)
        p.setPen(QColor(MUTED))
        if self.marks:
            p.drawText(QRectF(16, area.bottom() + 6, area.width(), 18), Qt.AlignLeft, f"{low!r}")
            p.drawText(QRectF(16, area.bottom() + 6, area.width(), 18), Qt.AlignRight, f"{high!r} {self.unit}")
            p.setPen(QPen(QColor("#2a3849"), 1))
            p.drawLine(area.bottomLeft(), area.bottomRight())
            zero = area.left() + (0 - low) / ((high - low) or 1.0) * area.width()
            p.setPen(QPen(QColor("#3a4a5f"), 1, Qt.DashLine))
            p.drawLine(QPointF(zero, area.top()), QPointF(zero, area.bottom()))
            for index, (spot, (_, value)) in enumerate(zip(spots, self.points)):
                color = QColor(RED if value < 0 else TEAL)
                p.setPen(QPen(color, 3 if index == self.hover else 1.6, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(spot, QPointF(spot.x(), area.bottom() - area.height() * 0.8 * self.reveal))
        else:
            p.drawText(QRectF(16, area.top() - 16, area.width(), 14), Qt.AlignRight, f"max {high!r}")
            p.drawText(QRectF(16, area.bottom() + 6, area.width(), 18), Qt.AlignRight, f"min {low!r} {self.unit}")
            p.drawText(QRectF(16, area.bottom() + 6, area.width(), 18), Qt.AlignLeft, f"{len(spots)} 点")
            p.setPen(QPen(QColor("#1b2534"), 1))
            for fraction in (0, 0.5, 1):
                y = area.top() + area.height() * fraction
                p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.save()
            p.setClipRect(QRectF(0, 0, area.left() + area.width() * self.reveal + 6, self.height()))
            line = QPainterPath(spots[0])
            for spot in spots[1:]:
                line.lineTo(spot)
            under = QPainterPath(line)
            under.lineTo(spots[-1].x(), area.bottom())
            under.lineTo(spots[0].x(), area.bottom())
            shade = QLinearGradient(0, area.top(), 0, area.bottom())
            shade.setColorAt(0, QColor(45, 212, 191, 70))
            shade.setColorAt(1, QColor(45, 212, 191, 0))
            p.fillPath(under, shade)
            stroke = QLinearGradient(area.left(), 0, area.right(), 0)
            stroke.setColorAt(0, QColor(TEAL))
            stroke.setColorAt(1, QColor(VIOLET))
            p.setPen(QPen(stroke, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(line)
            if len(spots) <= 60:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#e6ecf5"))
                for spot in spots:
                    p.drawEllipse(spot, 2.6, 2.6)
            p.restore()
        if self.hover is not None:
            spot, (name, value) = spots[self.hover], self.points[self.hover]
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.drawLine(QPointF(spot.x(), area.top()), QPointF(spot.x(), area.bottom()))
            if not self.marks:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(TEAL))
                p.drawEllipse(spot, 4.5, 4.5)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(16, 10, self.width() - 32, 20), Qt.AlignRight | Qt.AlignVCenter, f"{name} · {value!r} {self.unit}")


CPK = {"H": "#eef2f7", "C": "#7b8796", "N": "#5b8cff", "O": "#ff5d5d", "F": "#86efac", "P": "#ff9f43", "S": "#ffd84a",
       "Cl": "#4ade80", "Br": "#c0603f", "I": "#a855f7", "B": "#f5b5a0", "Si": "#d8b98a", "Ni": "#5eead4", "Fe": "#e8793a",
       "Cu": "#d99a66", "Co": "#f08fb0", "Pd": "#4fb3c4", "Pt": "#d5dbe3", "Ru": "#3fa7a0", "Rh": "#e35d8f", "Ir": "#4a6fd0", "Zn": "#9aa6d6"}
COVALENT = {"H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39}


class Molecule(Animated):
    """Rotating ball-and-stick projection of one structure. Display aid only: bonds are guessed from distances."""
    interval = 40

    def __init__(self):
        super().__init__()
        self.setMinimumSize(260, 180)
        self.atoms, self.bonds, self.extent = [], [], 1.0
        self.rx, self.ry, self.zoom, self.spin, self.grab = -0.35, 0.6, 1.0, True, None

    def set(self, symbols, coordinates):
        count = len(symbols)
        center = [sum(c[i] for c in coordinates) / count for i in range(3)] if count else [0, 0, 0]
        self.atoms = [(s, x - center[0], y - center[1], z - center[2]) for s, (x, y, z) in zip(symbols, coordinates)]
        self.extent = max([math.sqrt(x * x + y * y + z * z) for _, x, y, z in self.atoms] + [1.0])
        self.bonds = []
        if count <= 800:
            for i, (a, ax, ay, az) in enumerate(self.atoms):
                for j in range(i + 1, count):
                    b, bx, by, bz = self.atoms[j]
                    limit = 1.2 * (COVALENT.get(a, 1.35) + COVALENT.get(b, 1.35))
                    if (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2 < limit * limit:
                        self.bonds.append((i, j))
        self.zoom, self.spin = 1.0, True
        self.update()

    def tick(self):
        if self.spin and self.grab is None:
            self.ry += 0.012

    def mousePressEvent(self, event):
        self.grab, self.spin = event.position(), False

    def mouseMoveEvent(self, event):
        if self.grab is not None:
            delta = event.position() - self.grab
            self.grab = event.position()
            self.ry += delta.x() * 0.01
            self.rx += delta.y() * 0.01
            self.update()

    def mouseReleaseEvent(self, event):
        self.grab = None

    def mouseDoubleClickEvent(self, event):
        self.rx, self.zoom, self.spin = -0.35, 1.0, True

    def wheelEvent(self, event):
        self.zoom = min(6.0, max(0.3, self.zoom * (1.12 if event.angleDelta().y() > 0 else 0.89)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        backdrop = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
        backdrop.setColorAt(0, QColor("#17233a"))
        backdrop.setColorAt(1, QColor("#0b1019"))
        p.fillPath(frame, backdrop)
        p.setClipPath(frame)
        if not self.atoms:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "没有结构可显示")
            return
        scale = min(w, h) * 0.5 / self.extent * self.zoom
        cy, sy, cx, sx = math.cos(self.ry), math.sin(self.ry), math.cos(self.rx), math.sin(self.rx)
        placed = []
        for symbol, x, y, z in self.atoms:
            x1, z1 = x * cy + z * sy, -x * sy + z * cy
            y1, depth = y * cx - z1 * sx, y * sx + z1 * cx
            placed.append((w / 2 + x1 * scale, h / 2 - y1 * scale, depth, symbol))
        items = [(placed[i][2], 1, i) for i in range(len(placed))] + [((placed[i][2] + placed[j][2]) / 2, 0, (i, j)) for i, j in self.bonds]
        for depth, is_atom, ref in sorted(items, key=lambda item: item[:2]):
            light = 0.5 + 0.5 * (depth + self.extent) / (2 * self.extent)
            if not is_atom:
                (x1, y1, _, _), (x2, y2, _, _) = placed[ref[0]], placed[ref[1]]
                shade = int(150 * light)
                p.setPen(QPen(QColor(shade, shade + 12, shade + 28), max(1.4, scale * 0.13), Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                continue
            x, y, _, symbol = placed[ref]
            radius = max(2.5, scale * (0.2 + 0.28 * COVALENT.get(symbol, 1.35)))
            base = QColor(CPK.get(symbol, "#c9a6ff"))
            color = QColor(int(base.red() * light), int(base.green() * light), int(base.blue() * light))
            ball = QRadialGradient(x - radius * 0.35, y - radius * 0.35, radius * 1.3)
            ball.setColorAt(0, color.lighter(165))
            ball.setColorAt(0.55, color)
            ball.setColorAt(1, color.darker(210))
            p.setPen(Qt.NoPen)
            p.setBrush(ball)
            p.drawEllipse(QPointF(x, y), radius, radius)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(12, h - 26, w - 24, 18), Qt.AlignLeft | Qt.AlignVCenter, "拖动旋转 · 滚轮缩放 · 双击复位　键按原子间距推断，仅用于显示")
