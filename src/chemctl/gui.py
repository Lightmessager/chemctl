"""PySide6 HTTP client. All filesystem and chemistry work belongs to the API."""
import json
import os
import sys
from datetime import datetime
from html import escape as esc
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QObject, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRunnable,
    QSignalBlocker, QSize, QThreadPool, QTimer, Qt, QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .client import APIError, Client
from .widgets import Chart, Hero, Molecule, Nav, Progress, Pulse, Spinner, count_to

TONES = {"ok": "#4fd1a5", "warn": "#f0b354", "bad": "#f47c7c", "info": "#6cb6ff", "muted": "#8a9bb0"}

STYLE = """
QWidget { background: #0a0e15; color: #e6ecf5; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'; font-size: 13px; }
QFrame#side { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101826, stop:1 #0b1019); border-right: 1px solid #1a2433; }
QFrame#side QLabel { background: transparent; }
QPushButton#brand { background: transparent; border: none; text-align: left; padding: 0; font-size: 23px; font-weight: 800; color: #ffffff; }
QPushButton#brand:hover { color: #5eead4; background: transparent; }
QLabel#brandSub { color: #8a9bb0; font-size: 12px; }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 11px 16px; font-size: 14px; color: #9fb0c5; border-radius: 10px; }
QPushButton#nav:hover { color: #ffffff; background: rgba(255, 255, 255, 0.05); }
QPushButton#nav:checked { color: #ffffff; font-weight: 700; background: transparent; }
QFrame#navPill { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14b8a6, stop:1 #6d5cf6); border-radius: 10px; }
QLabel#title { font-size: 26px; font-weight: 800; color: #ffffff; }
QLabel#muted, QLabel#empty { color: #8a9bb0; }
QLabel#empty { font-size: 14px; padding: 30px; background: #0e141e; border: 1px dashed #263448; border-radius: 12px; }
QLabel#section { font-size: 14px; font-weight: 700; color: #dbe4f0; background: transparent; }
QWidget#hero QLabel { background: transparent; }
QLabel#heroTitle { font-size: 30px; font-weight: 800; color: #ffffff; }
QLabel#heroText { font-size: 14px; color: rgba(232, 240, 255, 0.85); }
QFrame#card { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #141d2b, stop:1 #0f1622); border: 1px solid #1f2b3c; border-radius: 14px; }
QFrame#card QLabel { background: transparent; }
QLabel#tileValue { font-size: 24px; font-weight: 800; }
QLabel[tone="ok"] { color: #4fd1a5; } QLabel[tone="warn"] { color: #f0b354; } QLabel[tone="bad"] { color: #f47c7c; }
QLabel[tone="info"] { color: #6cb6ff; } QLabel[tone="muted"] { color: #8a9bb0; }
QLabel#pill { background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 5px 12px; color: #9ddcff; }
QFrame#banner { border-radius: 10px; border: 1px solid #2c4664; background: #13233a; }
QFrame#banner[tone="ok"] { border-color: #1f7a63; background: #0f2e29; }
QFrame#banner[tone="bad"] { border-color: #8a3a40; background: #331a1f; }
QFrame#banner QLabel { background: transparent; }
QPushButton { background: #172131; border: 1px solid #2a394d; border-radius: 8px; padding: 8px 15px; }
QPushButton:hover { background: #22304a; border-color: #4b6a8f; }
QPushButton:pressed { background: #121a27; }
QPushButton:disabled { color: #566477; background: #111823; border-color: #1c2635; }
QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14b8a6, stop:1 #3b82f6); border: none; color: #ffffff; font-weight: 700; padding: 9px 18px; }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2dd4bf, stop:1 #60a5fa); }
QPushButton#primary:disabled { background: #1a3a44; color: #7fa0a8; }
QPushButton#glass { background: rgba(255, 255, 255, 0.10); border: 1px solid rgba(255, 255, 255, 0.24); color: #ffffff; }
QPushButton#glass:hover { background: rgba(255, 255, 255, 0.20); }
QPushButton#flat { background: transparent; border: none; color: #6cb6ff; padding: 4px 6px; }
QPushButton#flat:hover { color: #b5dcff; background: transparent; }
QTableWidget { background: #0e141e; alternate-background-color: #111926; border: 1px solid #1f2b3c; border-radius: 12px; gridline-color: transparent; outline: 0; }
QTableWidget::item { padding: 4px 10px; border-bottom: 1px solid #172131; }
QTableWidget::item:selected { background: #16384a; color: #ffffff; }
QHeaderView::section { background: #121a27; color: #8fa2b8; padding: 9px 10px; border: none; border-bottom: 1px solid #223044; font-weight: 700; }
QTableCornerButton::section { background: #121a27; border: none; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser { background: #0e141e; border: 1px solid #26344a; border-radius: 8px; padding: 8px; selection-background-color: #14b8a6; }
QLineEdit:focus, QComboBox:focus { border-color: #2dd4bf; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #121a27; border: 1px solid #26344a; selection-background-color: #1d4046; }
QPlainTextEdit { font-family: Consolas, 'Microsoft YaHei UI'; }
QTabWidget::pane { border: none; border-top: 1px solid #1f2b3c; }
QTabBar::tab { background: transparent; color: #8fa2b8; padding: 9px 20px; border-bottom: 3px solid transparent; font-size: 14px; }
QTabBar::tab:hover { color: #ffffff; }
QTabBar::tab:selected { color: #5eead4; border-bottom: 3px solid #2dd4bf; font-weight: 700; }
QSplitter::handle { background: transparent; height: 10px; width: 10px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #40546d; border-radius: 4px; background: #0e141e; }
QCheckBox::indicator:checked { background: #14b8a6; border-color: #5eead4; }
QScrollBar:vertical { background: transparent; width: 10px; } QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle { background: #26344a; border-radius: 5px; min-height: 30px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: transparent; height: 0; width: 0; }
QToolTip { background: #121a27; color: #e6ecf5; border: 1px solid #26344a; padding: 4px; }
"""

PAGES = ["Overview", "Servers", "Jobs", "Files", "Parser", "Results", "Settings"]
NAV = ["概览", "服务器", "任务", "文件", "解析", "结果", "设置"]

# Four independent state families; never merged into one "status".
PARSE = {"parsed": ("已解析", "ok"), "partial": ("部分解析", "warn"), "unsupported": ("不支持", "muted"),
         "not_parsed": ("未解析", "muted"), "failed": ("解析失败", "bad")}
CALC = {"completed": ("正常终止", "ok"), "incomplete": ("未完成", "warn"), "failed": ("计算失败", "bad"), "stale": ("已过期", "bad")}
JOB = {"queued": ("排队中", "info"), "running": ("运行中", "info"), "completed": ("已完成", "ok"),
       "failed": ("失败", "bad"), "cancelled": ("已取消", "muted"), "held": ("挂起", "warn"),
       "uploading": ("上传中", "info"), "submitting": ("提交中", "info"), "submission_unknown": ("提交回执待确认", "warn"),
       "unknown": ("状态待确认", "warn"), "cancelling": ("取消中", "warn")}
BATCH = {"queued": ("排队中", "info"), "running": ("解析中", "info"), "succeeded": ("执行完成", "ok"),
         "partially_succeeded": ("部分文件失败", "warn"), "failed": ("失败", "bad")}


def status(mapping, value):
    if value is None:
        return "—"
    label, tone = mapping.get(value, (value, "muted"))
    return f"● {label} · {value}", tone


def span(cell):
    text, tone = cell if isinstance(cell, tuple) else (cell, None)
    return f"<span style='color:{TONES[tone]}'>{esc(text)}</span>" if tone else esc(text)


def when(value):
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else "—"


def size_text(value):
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if value >= scale:
            return f"{value / scale:.1f} {unit}"
    return f"{value} B"


def source_text(location):
    if not location:
        return "—"
    return f"行 {location['line']}" if "line" in location else str(location.get("parser_attribute", "—"))


def as_xyz(structure):
    location = structure["source_location"]
    rows = [str(len(structure["symbols"])),
            f"chemctl | angstrom | structure {structure['index']} | {Path(location['path']).name} | {source_text(location)}"]
    rows += [f"{s:<3} {x!r:>16} {y!r:>16} {z!r:>16}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    return "\n".join(rows) + "\n"


def detail_html(pairs, warnings=(), extra=""):
    rows = "".join(f"<tr><td style='color:#8a9bb0;padding:4px 22px 4px 0;white-space:nowrap' valign='top'>{esc(k)}</td>"
                   f"<td style='padding:4px 0'>{v}</td></tr>" for k, v in pairs)
    notes = "".join(f"<p style='color:#f0b354;margin:4px 0'><b>警告</b>　{esc(w)}</p>" for w in warnings)
    return f"{notes}<table cellspacing='0'>{rows}</table>{extra}"


def copy(text):
    QApplication.clipboard().setText(text)


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except APIError as exc:
            self.signals.failed.emit(f"[{exc.response['error']['code']}] {exc}")
        except Exception as exc:
            self.signals.failed.emit(str(exc))


def button(text, callback, kind=None):
    result = QPushButton(text)
    if kind:
        result.setObjectName("primary" if kind is True else kind)
    result.clicked.connect(callback)
    return result


def label(text="", name="muted", wrap=True, selectable=False):
    result = QLabel(text)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    if selectable:
        result.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return result


def set_tone(widget, tone):
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def row(*widgets, stretch=True):
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch:
        layout.addStretch()
    return layout


def browser():
    view = QTextBrowser()
    view.setOpenLinks(False)
    return view


class DataTable(QWidget):
    """Paged table. Records live on the first cell (UserRole), not in a parallel row-index list."""

    def __init__(self, columns, empty, on_page=None, page_size=50, elide=Qt.ElideRight):
        super().__init__()
        self.on_page, self.page_size, self.offset = on_page, page_size, 0
        self.request_revision = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([name for name, _ in columns])
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setTextElideMode(elide)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setHighlightSections(False)
        for index, (_, width) in enumerate(columns):
            header.setSectionResizeMode(index, QHeaderView.Interactive if width else QHeaderView.Stretch)
            if width:
                self.table.setColumnWidth(index, width)
        self.empty = label(empty, "empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty_text = empty
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        waiting = QWidget()
        QVBoxLayout(waiting).addWidget(Spinner(), 0, Qt.AlignCenter)
        self.stack.addWidget(waiting)
        self.stack.setCurrentIndex(1)
        layout.addWidget(self.stack, 1)
        self.info = label(wrap=False)
        self.prev = button("← 上一页", lambda: self.move(-self.page_size))
        self.next = button("下一页 →", lambda: self.move(self.page_size))
        self.prev.setEnabled(False)
        self.next.setEnabled(False)
        footer = row(self.info, stretch=False)
        footer.addStretch()
        footer.addWidget(self.prev)
        footer.addWidget(self.next)
        layout.addLayout(footer)

    def move(self, delta):
        self.offset = max(0, self.offset + delta)
        self.on_page()

    def fill(self, data, cells):
        selection_blocker = QSignalBlocker(self.table)
        items = data["items"]
        self.offset = data["offset"]
        self.table.setRowCount(len(items))
        for i, record in enumerate(items):
            for j, cell in enumerate(cells(record)):
                text, tone = cell if isinstance(cell, tuple) else (cell, None)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if tone:
                    item.setForeground(QColor(TONES[tone]))
                if j == 0:
                    item.setData(Qt.UserRole, record)
                self.table.setItem(i, j, item)
        self.empty.setText(self.empty_text)
        self.stack.setCurrentIndex(0 if items else 1)
        end = self.offset + len(items)
        self.info.setText(f"第 {self.offset + 1}–{end} 条 · 共 {data['total']} 条" if items else "共 0 条")
        self.prev.setEnabled(self.offset > 0)
        self.next.setEnabled(end < data["total"])
        del selection_blocker

    def loading(self):
        if not self.table.rowCount():
            self.stack.setCurrentIndex(2)

    def message(self, text):
        self.empty.setText(text)
        self.stack.setCurrentIndex(1)
        self.info.setText("")

    def current(self):
        index = self.table.currentRow()
        return self.table.item(index, 0).data(Qt.UserRole) if index >= 0 else None

    def select(self, field, value):
        for index in range(self.table.rowCount()):
            if self.table.item(index, 0).data(Qt.UserRole).get(field) == value:
                self.table.selectRow(index)
                return


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client = Client()
        self.pool = QThreadPool.globalInstance()
        self.tasks = set()
        self.closing = False
        self.active_batch, self.polling = None, False
        self.calc_id, self.structure = None, None
        self.detail_revision = 0
        self.setWindowTitle("chemctl · 计算化学工作台")
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "chemctl.ico")))
        self.resize(1240, 800)
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(188)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 22, 14, 16)
        self.brand_clicks = 0
        brand = button("chemctl", self.brand_clicked, "brand")
        brand.setIcon(self.windowIcon())
        brand.setIconSize(QSize(32, 32))
        side_layout.addWidget(brand)
        side_layout.addWidget(label("计算化学工作台", "brandSub"))
        side_layout.addSpacing(20)
        self.nav = Nav(NAV)
        side_layout.addWidget(self.nav, 1)
        self.pulse = Pulse()
        self.api_state = label("正在连接 API…", "apiState", wrap=False)
        side_layout.addLayout(row(self.pulse, self.api_state))
        side_layout.addWidget(label(self.client.url.split("//")[-1], "brandSub"))
        outer.addWidget(side)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner_text = label(name="bannerText", selectable=True)
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 8, 8, 8)
        banner_layout.addWidget(self.banner_text, 1)
        banner_layout.addWidget(button("复制", lambda: copy(self.banner_text.text()), "flat"))
        banner_layout.addWidget(button("关闭", self.banner.hide, "flat"))
        holder = QVBoxLayout()
        holder.setContentsMargins(28, 14, 28, 0)
        holder.addWidget(self.banner)
        main_layout.addLayout(holder)
        self.banner.hide()
        self.banner_serial = 0
        self.banner_slide = QPropertyAnimation(self.banner, b"maximumHeight", self)
        self.banner_slide.setDuration(280)
        self.banner_slide.setStartValue(0)
        self.banner_slide.setEndValue(160)
        self.banner_slide.setEasingCurve(QEasingCurve.OutCubic)
        self.transition = self.transition_page = None
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)
        outer.addWidget(main, 1)
        self.setCentralWidget(root)

        self.build_overview()
        self.build_servers()
        self.build_jobs()
        self.build_files()
        self.build_parser()
        self.build_results()
        self.build_settings()
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.poll_batch)
        self.nav.currentRowChanged.connect(self.switch_page)
        self.nav.setCurrentRow(0)

    # ---- shared plumbing -------------------------------------------------

    def request(self, fn, callback, on_error=None, busy=None):
        """Run fn in the pool. busy: a button kept disabled until the reply arrives."""
        task = Task(fn)
        self.tasks.add(task)
        if busy:
            busy.setEnabled(False)

        def finish(handler, value):
            self.tasks.discard(task)
            if self.closing:
                return
            if busy:
                busy.setEnabled(True)
            handler(value)
        task.signals.done.connect(lambda result: finish(callback, result["data"]))
        task.signals.failed.connect(lambda message: finish(on_error or self.error, message))
        self.pool.start(task)

    def notify(self, text, tone="info", sticky=False):
        self.banner_serial += 1
        serial = self.banner_serial
        self.banner_text.setText(text)
        set_tone(self.banner, tone)
        if self.banner.isHidden():
            self.banner.show()
            self.banner_slide.start()
        if tone != "bad" and not sticky:
            QTimer.singleShot(6000, lambda: serial == self.banner_serial and self.banner.hide())

    def error(self, message):
        self.notify(message, "bad")

    def brand_clicked(self):
        self.brand_clicks += 1
        if self.brand_clicks % 5 == 0:
            self.nav.setCurrentRow(0)
            self.hero.benzene()
            self.notify("C6H6 —— 你找到了苯环。", "ok")

    def page(self, title=None, subtitle=None):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(28, 18, 28, 16)
        layout.setSpacing(12)
        if title:
            layout.addWidget(label(title, "title"))
            layout.addWidget(label(subtitle))
        self.stack.addWidget(widget)
        return layout

    def form(self, title, fields):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(520, 0)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        inputs = {}
        for key, text, default in fields:
            if isinstance(default, list):
                editor = QComboBox()
                editor.addItems(default[1:])
                editor.setCurrentText(default[0])
            else:
                editor = QLineEdit(default)
            layout.addRow(text, editor)
            inputs[key] = editor
        actions = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        actions.button(QDialogButtonBox.Ok).setText("保存")
        actions.button(QDialogButtonBox.Ok).setObjectName("primary")
        actions.button(QDialogButtonBox.Cancel).setText("取消")
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addRow(actions)
        if dialog.exec() != QDialog.Accepted:
            return None
        return {key: (e.currentText() if isinstance(e, QComboBox) else e.text().strip()) for key, e in inputs.items()}

    def switch_page(self, index):
        if self.transition:
            self.transition.stop()
            self.transition_page.setGraphicsEffect(None)
            self.transition_page.move(0, 0)
        self.stack.setCurrentIndex(index)
        page = self.transition_page = self.stack.currentWidget()
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity")
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        rise = QPropertyAnimation(page, b"pos")
        rise.setStartValue(QPoint(0, 28))
        rise.setEndValue(QPoint(0, 0))
        self.transition = QParallelAnimationGroup(self)
        for animation in (fade, rise):
            animation.setDuration(320)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self.transition.addAnimation(animation)
        self.transition.finished.connect(lambda: page.setGraphicsEffect(None))
        self.transition.start()
        self.refresh(PAGES[index])

    def refresh(self, page):
        getattr(self, "refresh_" + page.lower())()

    def listing(self, table, route, cells, after=None, **params):
        table.request_revision += 1
        revision, offset = table.request_revision, table.offset
        def done(data):
            if revision != table.request_revision:
                return
            table.fill(data, cells)
            if after:
                after()
        table.loading()
        self.request(lambda: self.client.get(route, offset=offset, limit=table.page_size, **params), done,
                     lambda message: revision == table.request_revision and table.message("加载失败：" + message))

    # ---- Overview --------------------------------------------------------

    def tile(self, caption, accent):
        frame = QFrame()
        frame.setObjectName("card")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(0, 0, 14, 0)
        outer.setSpacing(14)
        bar = QFrame()
        bar.setFixedWidth(5)
        bar.setStyleSheet(f"background: {accent}; border: none; border-top-left-radius: 14px; border-bottom-left-radius: 14px;")
        outer.addWidget(bar)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(2)
        outer.addLayout(layout, 1)
        layout.addWidget(label(caption, wrap=False))
        value = label("…", "tileValue", wrap=False, selectable=True)
        layout.addWidget(value)
        return frame, value

    def build_overview(self):
        layout = self.page()
        self.hero = Hero()
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(30, 24, 30, 22)
        hero_layout.setSpacing(6)
        hero_layout.addWidget(label("计算化学工作台", "heroTitle", wrap=False))
        hero_layout.addWidget(label("解析 ORCA / Gaussian 输出，查询能量、结构与频率。已确认的 PBS 服务器支持脚本提交、监控与结果同步。", "heroText"))
        hero_layout.addStretch()
        hero_layout.addLayout(row(button("导入输出文件", lambda: self.nav.setCurrentRow(4), True),
                                  button("浏览结果", lambda: self.nav.setCurrentRow(5), "glass"), button("刷新", self.refresh_overview, "glass")))
        layout.addWidget(self.hero)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tiles = {}
        captions = [("api", "API 服务"), ("database", "数据库"), ("version", "程序版本"), ("parser_version", "解析器版本"),
                    ("/files", "已索引输出文件"), ("/calculations", "计算记录"), ("/jobs", "任务（真实 / 模拟）"), ("/servers", "服务器配置")]
        for index, (key, caption) in enumerate(captions):
            frame, self.tiles[key] = self.tile(caption, ("#2dd4bf", "#38bdf8", "#8b5cf6", "#f0b354")[index % 4])
            grid.addWidget(frame, index // 4, index % 4)
        layout.addLayout(grid)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(8)
        card_layout.addWidget(label("本版本能做什么", "section"))
        lines = [("ok", "真实", "本地 ORCA / Gaussian 输出的扫描、批量解析，以及能量、结构、频率查询"),
                 ("info", "模拟", "任务提交与状态流转：不上传文件，不运行任何计算程序，不产生结果"),
                 ("warn", "PBS", "登录后保留 SSH 会话；显式脚本提交、每 30 秒监控、按需同步。提交前展示完整计划")]
        for tone, tag, text in lines:
            card_layout.addWidget(label(f"<b style='color:{TONES[tone]}'>{tag}</b>&nbsp;&nbsp;&nbsp;{text}", "plain"))
        self.remote_note = label()
        card_layout.addWidget(self.remote_note)
        layout.addWidget(card)

        self.home_label = label(wrap=False, selectable=True)
        layout.addLayout(row(label("数据目录", wrap=False), self.home_label, button("复制", lambda: copy(self.home_label.text()), "flat")))
        self.health_toggle = button("显示健康检查原始 JSON", self.toggle_health, "flat")
        layout.addLayout(row(self.health_toggle))
        self.health = QPlainTextEdit()
        self.health.setReadOnly(True)
        self.health.hide()
        layout.addWidget(self.health, 1)
        layout.addStretch()

    def toggle_health(self):
        self.health.setVisible(not self.health.isVisible())
        self.health_toggle.setText(("隐藏" if self.health.isVisible() else "显示") + "健康检查原始 JSON")

    def refresh_overview(self):
        def healthy(data):
            self.show_api_state(True)
            for key in ("api", "database"):
                self.tiles[key].setText("正常" if data[key] == "ok" else str(data[key]))
                set_tone(self.tiles[key], "ok" if data[key] == "ok" else "bad")
            self.tiles["version"].setText(data["version"])
            self.tiles["parser_version"].setText(data["parser_version"])
            self.home_label.setText(data["home"])
            self.remote_note.setText("真实 PBS 任务支持 SSH 密钥自动登录；服务器页可启用免密登录。提交前会展示脚本、资源和目标目录。")
            self.health.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))

        def unreachable(message):
            self.show_api_state(False)
            for key in ("api", "database"):
                self.tiles[key].setText("未连接")
                set_tone(self.tiles[key], "bad")
            self.error(message)
        self.request(lambda: self.client.get("/health"), healthy, unreachable)
        for route in ("/files", "/calculations", "/jobs", "/servers"):
            self.request(lambda route=route: self.client.get(route, limit=1),
                         lambda data, route=route: count_to(self.tiles[route], data["total"]),
                         lambda _, route=route: self.tiles[route].setText("—"))

    def show_api_state(self, ok):
        self.api_state.setText("API 已连接" if ok else "API 未连接")
        self.pulse.set_color(TONES["ok" if ok else "bad"])
        set_tone(self.api_state, "ok" if ok else "bad")

    # ---- Servers ---------------------------------------------------------

    def build_servers(self):
        layout = self.page("服务器", "管理 SSH 连接、免密登录与计算软件探测。确认 PBS 后可提交脚本。")
        self.test_button = button("检查连接", self.test_server)
        layout.addLayout(row(button("添加 SSH 服务器", lambda: self.edit_server(None), True), button("编辑所选", lambda: self.edit_server(self.servers.current())),
                             self.test_button, button("刷新", self.refresh_servers)))
        layout.addLayout(row(button("启用免密登录", self.enable_server_key),
                             button("探测计算软件", self.discover_server_software),
                             button("使用密码连接", lambda: self.test_server(force_password=True))))
        self.servers = DataTable([("名称", 190), ("ID", 90), ("地址", 200), ("连接探测", 130), ("最近探测", 150), ("调度器", 130), ("任务提交", None)],
                                 "还没有服务器配置。\n点击“添加 SSH 服务器”保存主机信息，然后“检查连接”。", self.refresh_servers)
        self.server_detail = browser()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.servers)
        split.addWidget(self.server_detail)
        split.setSizes([330, 250])
        layout.addWidget(split, 1)
        self.servers.table.itemSelectionChanged.connect(self.show_server)

    def server_cells(self, s):
        if s["adapter"] == "mock":
            return [s["name"], s["server_id"], "本机（无连接）", ("模拟", "info"), "—", ("模拟", "info"), ("仅模拟任务", "info")]
        probe = s.get("last_probe")
        address = f"{s.get('username') or '(SSH config)'}@{s['host']}:{s.get('port') or '默认端口'}"
        scheduler = ("未确认", "warn") if s["scheduler"] == "unknown" else f"{s['scheduler']}（配置值）"
        return [s["name"], s["server_id"], address, ("● 上次探测成功", "ok") if probe else ("未探测", "muted"),
                when(probe["checked_at"]) if probe else "—", scheduler, ("PBS 脚本", "ok") if probe and probe.get("submission_supported") else ("待确认", "warn")]

    def refresh_servers(self):
        selected = (self.servers.current() or {}).get("server_id")
        self.listing(self.servers, "/servers", self.server_cells, lambda: (self.servers.select("server_id", selected), self.show_server()))

    def show_server(self):
        s = self.servers.current()
        if not s:
            return self.server_detail.setHtml("<p style='color:#8a9bb0'>选择一个服务器查看最近一次探测结果。</p>")
        if s["adapter"] == "mock":
            return self.server_detail.setHtml(detail_html([("类型", span(("本地模拟，不连接任何服务器，不执行计算", "info")))]))
        probe = s.get("last_probe")
        pairs = [("工作目录（配置）", esc(s.get("remote_root") or "未设置")),
                 ("免密登录", esc("Windows 加密保存专用密钥" if s.get("managed_key_path") else "未启用"))]
        if not probe:
            return self.server_detail.setHtml(detail_html(pairs + [("探测", span(("尚未成功探测。点击“检查连接”。", "muted")))]))
        hint = probe.get("detected_scheduler")
        hint_text = "旧版探测结果不含此项，请重新检查连接" if hint is None else "无法从只读输出判断" if hint == "unknown" else f"{hint}（程序根据输出给出的提示，尚未经人工确认）"
        pairs += [("探测时间", esc(when(probe["checked_at"]))), ("系统", esc(str(probe.get("system")))),
                  ("登录目录", esc(str(probe.get("login_directory")))),
                  ("发现的调度命令", "<br>".join(map(esc, probe.get("scheduler_commands") or [])) or "未发现"),
                  ("调度器类型提示", span((hint_text, "warn"))),
                  ("真实任务提交", span(("PBS 脚本可用；提交前查看计划，需保持 SSH 登录", "ok") if probe.get("submission_supported") else ("调度器尚未确认或探测记录需更新", "warn")))]
        evidence = probe.get("scheduler_evidence")
        extra = f"<p style='color:#8a9bb0'>只读探测原始输出</p><pre>{esc(evidence)}</pre>" if evidence else ""
        if s.get("software_probe"):
            extra += f"<p>计算软件探测</p><pre>{esc(s['software_probe']['evidence'])}</pre>"
        self.server_detail.setHtml(detail_html(pairs, extra=extra))

    def edit_server(self, s):
        if s and s["adapter"] == "mock":
            return self.notify("模拟服务器是内置的，不能编辑。")
        s = s or {}
        values = self.form("SSH 服务器", [("server_id", "ID（字母数字，保存时按 ID 整体替换）", s.get("server_id", "server01")),
            ("name", "名称", s.get("name", "")), ("host", "主机 / SSH 别名", s.get("host", "")),
            ("username", "用户名（留空使用 SSH config）", s.get("username") or ""), ("port", "端口（留空使用默认）", str(s.get("port") or "")),
            ("remote_root", "远程工作目录（可留空）", s.get("remote_root", "")),
            ("scheduler", "调度器（未确认请保持 unknown）", [s.get("scheduler", "unknown"), "unknown", "slurm", "pbs", "sge", "lsf", "direct"])])
        if values:
            values["username"] = values["username"] or None
            values["port"] = int(values["port"]) if values["port"] else None
            self.request(lambda: self.client.post("/servers", **values), lambda _: (self.notify("已保存服务器 " + values["server_id"], "ok"), self.refresh_servers()))

    def test_server(self, force_password=False):
        s = self.servers.current()
        if not s:
            return self.notify("请先在表格中选择一个服务器。")
        password = None
        if s["adapter"] == "ssh" and (force_password or not s.get("managed_key_path")):
            password, accepted = QInputDialog.getText(self, "SSH 认证", f"{s['name']} 的密码，仅用于本次连接，不会保存。\n留空则使用 SSH 密钥 / agent：", QLineEdit.Password)
            if not accepted:
                return
            self.notify(f"正在连接 {s['host']}… 认证最长可能需要 60 秒。", sticky=True)

        def done(result):
            if result.get("simulated"):
                return self.notify("这是本地模拟：没有连接服务器，也没有执行计算。")
            self.notify("SSH 连接成功，会话保留在后台内存中。" + ("PBS 脚本提交可用。" if result.get("submission_supported") else "调度器仍待确认。"), "ok")
            self.refresh_servers()
        self.request(lambda: self.client.post(f"/servers/{s['server_id']}/test", password=password or None), done, busy=self.test_button)

    def enable_server_key(self):
        s = self.servers.current()
        if not s or s['adapter'] != 'ssh':
            return self.notify("请先选择 SSH 服务器并检查连接。")
        self.request(lambda: self.client.post(f"/servers/{s['server_id']}/enable-key"),
                     lambda _: (self.notify("免密登录已验证，私钥由 Windows 当前用户加密保存。", "ok"), self.refresh_servers()))

    def discover_server_software(self):
        s = self.servers.current()
        if not s or s['adapter'] != 'ssh':
            return self.notify("请选择 SSH 服务器。")
        self.request(lambda: self.client.post(f"/servers/{s['server_id']}/software"),
                     lambda _: (self.notify("软件探测完成。", "ok"), self.refresh_servers()))

    # ---- Jobs ------------------------------------------------------------

    def build_jobs(self):
        layout = self.page("任务", "真实 PBS 任务与 demo 模拟分开标记。登录后每 30 秒监控；同步只读取该任务目录。")
        self.advance_button = button("推进模拟状态", lambda: self.job_action("advance-mock"))
        self.cancel_button = button("取消所选", lambda: self.job_action("cancel"))
        layout.addLayout(row(button("提交 PBS 脚本…", self.submit_remote, True), button("模拟任务…", self.submit_demo),
                             self.advance_button, self.cancel_button, button("刷新", self.refresh_jobs)))
        layout.addLayout(row(button("查询远程状态", lambda: self.job_action("refresh")),
                             button("同步并解析结果", lambda: self.job_action("sync"))))
        self.jobs = DataTable([("标签", 180), ("引擎", 110), ("状态", 160), ("类型", 80), ("提交时间", 150), ("状态更新", 150), ("Job ID", None)],
                              "还没有任务。\n“提交模拟任务”会登记一个输入文件并演练 排队 → 运行 → 完成，不会执行任何计算。", self.refresh_jobs)
        self.job_detail = browser()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.jobs)
        split.addWidget(self.job_detail)
        split.setSizes([330, 250])
        layout.addWidget(split, 1)
        self.jobs.table.itemSelectionChanged.connect(self.show_job)

    def refresh_jobs(self):
        selected = (self.jobs.current() or {}).get("job_id")
        cells = lambda j: [j["tag"] or "—", j["engine"], status(JOB, j["status"]), ("模拟", "info") if j["simulated"] else ("真实", "ok"),
                           when(j["submitted_at"]), when(j["last_state_change_at"]), j["job_id"]]
        self.listing(self.jobs, "/jobs", cells, lambda: (self.jobs.select("job_id", selected), self.show_job()))

    def show_job(self):
        j = self.jobs.current()
        active = bool(j) and j["status"] in ("queued", "running", "held", "unknown")
        self.advance_button.setEnabled(active and bool(j["simulated"]))
        self.cancel_button.setEnabled(active)
        if not j:
            return self.job_detail.setHtml("<p style='color:#8a9bb0'>选择一个任务查看输入清单和事件。</p>")

        def render(events):
            if (self.jobs.current() or {}).get("job_id") != j["job_id"]:
                return
            files = "<br>".join(f"{esc(f['name'])} · {size_text(f['size'])}" for f in j["input_manifest"])
            log = "<br>".join(f"{esc(when(e['at']))} &nbsp; {esc(e['action'])} &nbsp; <span style='color:#8a9bb0'>{esc(e['detail'])}</span>" for e in events) or "无"
            self.job_detail.setHtml(detail_html([("状态", span(status(JOB, j["status"]))), ("类型", span(("模拟任务", "info") if j["simulated"] else "真实任务")),
                ("说明", esc(j["message"])), ("输入路径", esc(j["input_path"])), ("输入清单", files), ("服务器", esc(j["server_id"])),
                ("队列任务号", esc(str(j.get("remote_job_id") or "—"))), ("远程目录", esc(j.get("remote_directory") or "—")),
                ("最近监控", esc(when(j.get("last_polled_at")))), ("监控错误", esc(j.get("last_poll_error") or "无")),
                ("同步状态", esc(j.get("sync_status") or "—")), ("同步错误", esc(j.get("sync_error") or "无")),
                ("本地缓存", esc(j.get("cache_path") or "尚未同步")), ("事件", log)]))
        self.request(lambda: self.client.get(f"/jobs/{j['job_id']}/events"), render)

    def submit_demo(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择输入文件（仅登记，不会上传或运行）", "", "Chemistry inputs (*.inp *.gjf *.com);;All files (*)")
        if path:
            engine = "gaussian09d" if Path(path).suffix.lower() in (".gjf", ".com") else "orca"
            self.request(lambda: self.client.post("/jobs", input_path=path, engine=engine, tag=Path(path).stem),
                         lambda _: (self.notify("已创建模拟任务。没有上传文件，也没有运行计算。", "ok"), self.refresh_jobs()))

    def submit_remote(self):
        def choose(data):
            servers = [s["server_id"] for s in data["items"] if s["adapter"] == "ssh"]
            if not servers:
                return self.notify("先在服务器页配置 SSH 并检查连接。", "warn")
            directory = QFileDialog.getExistingDirectory(self, "选择包含 PBS 脚本及全部输入的目录（整个目录将上传）")
            if not directory:
                return
            values = self.form("PBS 任务", [("server_id", "服务器", servers), ("script", "目录内脚本相对路径", "run.pbs"),
                ("engine", "计算引擎标签", ["orca", "gaussian09d"]), ("tag", "任务标签", Path(directory).name)])
            if not values:
                return
            from uuid import uuid4
            payload = {**values, "input_path": directory, "idempotency_key": str(uuid4()), "dry_run": True}
            self.request(lambda: self.client.post("/jobs", **payload), lambda plan: self.confirm_remote(payload, plan))
        self.request(lambda: self.client.get("/servers"), choose)

    def confirm_remote(self, payload, plan):
        dialog = QDialog(self)
        dialog.setWindowTitle("确认真实 PBS 提交计划")
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("以下脚本将实际提交到服务器并消耗计算资源。请核对资源指令、输入文件和远程目录。"))
        preview = QPlainTextEdit(json.dumps(plan, ensure_ascii=False, indent=2))
        preview.setReadOnly(True)
        layout.addWidget(preview, 1)
        layout.addLayout(row(button("取消", dialog.reject), button("确认提交真实任务", dialog.accept, True)))
        if dialog.exec() != QDialog.Accepted:
            return
        payload.update(dry_run=False, expected_plan_hash=plan["plan_hash"])
        def submitted(job):
            self.notify(f"任务 {job['job_id']}：{job['status']}。{job['message']}", "ok" if job["status"] == "queued" else "warn", sticky=True)
            self.refresh_jobs()
        self.request(lambda: self.client.post("/jobs", **payload), submitted)

    def job_action(self, action):
        j = self.jobs.current()
        if not j:
            return self.notify("请先在表格中选择一个任务。")
        if action == "cancel" and QMessageBox.question(self, "取消任务", f"取消{'模拟' if j['simulated'] else '真实'}任务 {j['tag'] or j['job_id']}？\n{j['job_id']}") != QMessageBox.Yes:
            return
        self.request(lambda: self.client.post(f"/jobs/{j['job_id']}/{action}"), lambda _: self.refresh_jobs())

    # ---- Files -----------------------------------------------------------

    def build_files(self):
        layout = self.page("文件", "已索引的本地输出文件。原始文件只读；导出会创建新副本，不覆盖已有文件。")
        layout.addLayout(row(button("扫描目录…", self.scan_folder, True), button("查看解析结果", self.open_file_result),
                             button("导出副本…", self.export_file), button("复制完整路径", self.copy_file_path), button("刷新", self.refresh_files)))
        self.files = DataTable([("文件名", 230), ("大小", 90), ("解析状态", 170), ("扫描时间", 150), ("完整路径", None)],
                               "还没有索引任何输出文件。\n点击“扫描目录”选择包含 .out / .log 的文件夹，或到“解析”页直接导入。",
                               self.refresh_files, elide=Qt.ElideMiddle)
        self.files.table.cellDoubleClicked.connect(lambda *_: self.open_file_result())
        layout.addWidget(self.files, 1)

    def refresh_files(self):
        self.listing(self.files, "/files", lambda f: [f["filename"], size_text(f["size"]), status(PARSE, f["parse_status"]), when(f["scanned_at"]), f["local_path"]])

    def selected_file(self):
        f = self.files.current()
        if not f:
            self.notify("请先在表格中选择一个文件。")
        return f

    def scan_folder(self):
        path = QFileDialog.getExistingDirectory(self, "扫描输出目录")
        if path:
            self.request(lambda: self.client.post("/files/scan", source=path, recursive=True),
                         lambda data: (self.notify(f"扫描完成：索引了 {data['count']} 个输出文件（尚未解析，请到“解析”页导入）。", "ok"), self.refresh_files()))

    def export_file(self):
        f = self.selected_file()
        if f:
            path, _ = QFileDialog.getSaveFileName(self, "导出副本（不会替换已有文件）", f["filename"], options=QFileDialog.DontConfirmOverwrite)
            if path:
                self.request(lambda: self.client.post(f"/files/{f['file_id']}/fetch", destination=path), lambda data: self.notify("已导出到 " + data["path"], "ok"))

    def copy_file_path(self):
        f = self.selected_file()
        if f:
            copy(f["local_path"])
            self.notify("已复制：" + f["local_path"], "ok")

    def open_file_result(self):
        f = self.selected_file()
        if f:
            if not f.get("calculation_id") or f["parse_status"] in ("not_parsed", "failed"):
                return self.notify("这个文件还没有当前有效的解析结果，请先到“解析”页导入。")
            self.calc_id = None
            self.nav.setCurrentRow(5)
            self.load_calc(f["calculation_id"])

    # ---- Parser ----------------------------------------------------------

    def build_parser(self):
        layout = self.page("解析", "批量导入 ORCA / Gaussian 输出（.out / .log）。未改动的文件会跳过；不完整的输出会明确标为部分解析。")
        self.source = QLineEdit()
        self.source.setPlaceholderText("本地输出文件或目录的路径")
        self.source.returnPressed.connect(self.start_parse)
        layout.addLayout(row(self.source, button("选择目录…", self.choose_source), button("选择文件…", self.choose_file), stretch=False))
        self.recursive = QCheckBox("包含子目录")
        self.recursive.setChecked(True)
        self.force = QCheckBox("强制重新解析未改动的文件")
        self.parse_button = button("开始解析", self.start_parse, True)
        examples = Path(__file__).resolve().parents[2] / "examples"
        layout.addLayout(row(self.parse_button, self.recursive, self.force,
                             button("填入合成示例目录（非真实计算）", lambda: self.source.setText(str(examples)), "flat")))

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(10)
        self.batch_status = label("尚未开始批次。选择输出文件或目录后点击“开始解析”。", "section")
        card_layout.addWidget(self.batch_status)
        self.progress = Progress()
        card_layout.addWidget(self.progress)
        self.counts = {}
        counts = QHBoxLayout()
        for key, caption in (("processed", "新解析"), ("skipped", "未改动跳过"), ("failed", "失败"), ("total", "文件总数")):
            box = QVBoxLayout()
            self.counts[key] = label("—", "tileValue", wrap=False)
            box.addWidget(self.counts[key])
            box.addWidget(label(caption, wrap=False))
            counts.addLayout(box)
        self.result_button = button("查看结果 →", lambda: self.nav.setCurrentRow(5), True)
        self.result_button.hide()
        counts.addWidget(self.result_button, 0, Qt.AlignBottom)
        card_layout.addLayout(counts)
        self.batch_note = label("批次“执行完成”只表示每个文件都处理过，不代表计算已收敛或字段完整；请在“结果”页查看各记录的解析状态与警告。")
        card_layout.addWidget(self.batch_note)
        layout.addWidget(card)

        layout.addWidget(label("失败的文件", "section"))
        self.batch_errors = DataTable([("文件 ID", 240), ("错误", None)], "没有失败的文件。")
        self.batch_errors.prev.hide()
        self.batch_errors.next.hide()
        layout.addWidget(self.batch_errors, 1)
        self.batch_toggle = button("显示批次原始 JSON", lambda: self.batch_view.setVisible(not self.batch_view.isVisible()), "flat")
        layout.addLayout(row(self.batch_toggle))
        self.batch_view = QPlainTextEdit()
        self.batch_view.setReadOnly(True)
        self.batch_view.setMaximumHeight(180)
        self.batch_view.hide()
        layout.addWidget(self.batch_view)

    def refresh_parser(self):
        pass  # batch state is driven by start_parse / poll_batch

    def choose_source(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.source.setText(path)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择输出文件", "", "Outputs (*.out *.log)")
        if path:
            self.source.setText(path)

    def start_parse(self):
        source = self.source.text().strip()
        if not source:
            return self.notify("请先填写或选择一个输出文件 / 目录。")

        def accepted(batch):
            self.active_batch = batch["parse_batch_id"]
            self.update_batch(batch)
            if self.active_batch:
                self.timer.start()
        self.request(lambda: self.client.post("/parse/batches", source=source, recursive=self.recursive.isChecked(), force=self.force.isChecked()),
                     accepted, busy=self.parse_button)

    def poll_batch(self):
        if not self.active_batch or self.polling:
            return
        self.polling = True
        key = self.active_batch

        def done(batch):
            self.polling = False
            self.update_batch(batch)

        def failed(message):
            self.polling = False
            self.batch_status.setText("轮询批次状态失败，2 秒后重试：" + message)
            set_tone(self.batch_status, "bad")
        self.request(lambda: self.client.get(f"/parse/batches/{key}"), done, failed)

    def update_batch(self, batch):
        text, tone = status(BATCH, batch["status"])
        self.batch_status.setText(f"{text}　　{batch['source']}" + (f"\n{batch['error']}" if batch.get("error") else ""))
        set_tone(self.batch_status, tone)
        active = batch["status"] in ("queued", "running")
        handled = batch["processed"] + batch["skipped"] + batch["failed"]
        self.progress.set(handled, batch["total"], active)
        for key, widget in self.counts.items():
            widget.setText(str(batch[key]))
        set_tone(self.counts["failed"], "bad" if batch["failed"] else None)
        self.batch_errors.fill({"items": batch["errors"], "total": len(batch["errors"]), "offset": 0}, lambda e: [e["file_id"], (e["message"], "bad")])
        self.batch_view.setPlainText(json.dumps(batch, ensure_ascii=False, indent=2))
        self.parse_button.setEnabled(not active)
        self.result_button.setVisible(not active and handled > 0)
        if not active:
            self.timer.stop()
            self.active_batch = None
            if batch["total"] == 0 and not batch.get("error"):
                self.batch_status.setText(self.batch_status.text() + "\n该路径下没有找到 .out / .log 文件。")

    # ---- Results ---------------------------------------------------------

    def build_results(self):
        layout = self.page("结果", "能量 Eh · 坐标 Å · 频率 cm⁻¹。解析状态与计算终止状态是两回事；不同方法 / 基组的能量不可直接比较。")
        self.engine = QComboBox()
        self.engine.addItems(["全部引擎", "orca", "gaussian09d"])
        self.parse_filter = QComboBox()
        self.parse_filter.addItems(["全部解析状态"] + list(PARSE))
        for combo in (self.engine, self.parse_filter):
            combo.currentIndexChanged.connect(self.filter_results)
        layout.addLayout(row(self.engine, self.parse_filter, button("刷新", self.refresh_results)))
        self.results = DataTable([("输出文件", 180), ("引擎", 95), ("方法 / 基组", 120), ("解析状态", 150), ("计算终止", 175), ("最终能量 (Eh)", 160), ("频率数（虚频）", None)],
                                 "没有符合条件的计算记录。\n到“解析”页导入 ORCA / Gaussian 输出文件后，这里会列出结果。", self.refresh_results)
        self.results.table.itemSelectionChanged.connect(self.result_selected)

        self.summary = browser()
        self.energies = DataTable([("步骤", 60), ("类型", 95), ("能量 (Eh)", 180), ("阶段", 85), ("来源", None)], "选择一条计算记录以查看能量。", self.load_energies, 200)
        self.frequencies = DataTable([("模式", 70), ("频率 (cm⁻¹)", 200), ("阶段", 110), ("来源", None)], "选择一条计算记录以查看频率。", self.load_frequencies, 200)
        self.imaginary = QCheckBox("仅显示虚频")
        self.imaginary.toggled.connect(lambda: (setattr(self.frequencies, "offset", 0), self.calc_id and self.load_frequencies()))
        frequency_tab = QWidget()
        frequency_layout = QVBoxLayout(frequency_tab)
        frequency_layout.addLayout(row(self.imaginary, label("负值为虚频。虚频个数本身不能证明过渡态已被验证。", wrap=False)))
        self.spectrum = Chart("本页频率在数轴上的位置（不含强度）", "cm^-1", marks=True)
        frequency_layout.addWidget(self.beside(self.frequencies, self.spectrum), 1)

        structure_tab = QWidget()
        structure_layout = QVBoxLayout(structure_tab)
        self.structure_info = label("选择一条计算记录以查看结构。", selectable=True)
        self.structure_prev = button("←", lambda: self.load_structure(self.structure_index - 1))
        self.structure_next = button("→", lambda: self.load_structure(self.structure_index + 1))
        self.structure_tools = [self.structure_prev, self.structure_next, button("复制 XYZ", self.copy_xyz), button("保存 XYZ…", self.save_xyz)]
        tools = row(*self.structure_tools, stretch=False)
        tools.addWidget(self.structure_info, 1)
        structure_layout.addLayout(tools)
        self.xyz = QPlainTextEdit()
        self.xyz.setReadOnly(True)
        self.xyz.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.molecule = Molecule()
        structure_layout.addWidget(self.beside(self.molecule, self.xyz), 1)
        for widget in self.structure_tools:
            widget.setEnabled(False)

        self.tabs = QTabWidget()
        self.energy_chart = Chart("本页能量按解析顺序的变化", "Eh")
        energy_tab = QWidget()
        QVBoxLayout(energy_tab).addWidget(self.beside(self.energies, self.energy_chart))
        for name, widget in (("摘要与警告", self.summary), ("能量", energy_tab), ("结构", structure_tab), ("频率", frequency_tab)):
            self.tabs.addTab(widget, name)
        self.summary.setHtml("<p style='color:#8a9bb0'>在上方选择一条计算记录，这里会显示摘要、来源与解析警告。</p>")
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.results)
        split.addWidget(self.tabs)
        split.setSizes([240, 360])
        layout.addWidget(split, 1)

    def beside(self, left, right):
        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([540, 420])
        return split

    def result_cells(self, c):
        f = c["frequency_summary"]
        energy = ("尚无最终值", "muted") if c["final_energy_eh"] is None else repr(c["final_energy_eh"])
        method = " / ".join(x for x in (c["method"], c["basis_set"]) if x) or ("未解析出", "muted")
        return [c["title"], c["engine"] or "—", method, status(PARSE, c["status"]), status(CALC, c["calculation_status"]), energy,
                f"{f['count']}（虚频 {f['imaginary_count']}）" if f else "—"]

    def filter_results(self):
        self.results.offset = 0
        self.refresh_results()

    def refresh_results(self):
        def reselect():
            selection_blocker = QSignalBlocker(self.results.table)
            self.results.select("calculation_id", self.calc_id)
            if not self.results.current() and self.results.table.rowCount():
                self.results.table.selectRow(0)
            selected = self.results.current()
            del selection_blocker
            if selected:
                self.load_calc(selected["calculation_id"])
            else:
                self.clear_result()
        self.listing(self.results, "/calculations", self.result_cells, reselect,
                     engine=self.engine.currentText() if self.engine.currentIndex() else None,
                     status=self.parse_filter.currentText() if self.parse_filter.currentIndex() else None)

    def result_selected(self):
        c = self.results.current()
        if c and c["calculation_id"] != self.calc_id:
            self.load_calc(c["calculation_id"])

    def for_calc(self, callback):
        """Drop replies from an earlier selection or refresh of the same record."""
        key, revision = self.calc_id, self.detail_revision
        return lambda value: key == self.calc_id and revision == self.detail_revision and callback(value)

    def load_calc(self, key):
        self.clear_result(key)
        self.summary.setHtml("<p style='color:#8a9bb0'>加载中…</p>")
        self.energies.offset = self.frequencies.offset = 0
        self.request(lambda: self.client.get(f"/calculations/{key}"), self.for_calc(self.show_summary),
                     self.for_calc(lambda message: self.summary.setPlainText(message)))
        self.load_energies()
        self.load_structure()
        self.load_frequencies()

    def clear_structure(self, message="加载结构中…"):
        self.structure = None
        self.xyz.clear()
        self.molecule.set([], [])
        self.structure_info.setText(message)
        for widget in self.structure_tools:
            widget.setEnabled(False)

    def clear_result(self, key=None):
        self.detail_revision += 1
        self.calc_id = key
        self.summary.setPlainText("选择一条计算记录以查看详情。")
        self.clear_structure("选择一条计算记录以查看结构。")
        for table, chart in ((self.energies, self.energy_chart), (self.frequencies, self.spectrum)):
            table.fill({"items": [], "offset": 0, "total": 0}, lambda _: [])
            table.message("加载中…" if key else "选择一条计算记录。")
            chart.set([])

    def show_summary(self, c):
        geometry = c["convergence"]["geometry"]
        f = c["frequency_summary"]
        missing = lambda value: span(("未解析出", "muted")) if value is None else esc(str(value))
        pairs = [("输出文件", esc(c["title"])), ("程序", esc(f"{c['engine']} {c.get('engine_version') or ''}")),
                 ("方法", missing(c["method"])), ("基组", missing(c["basis_set"])),
                 ("溶剂模型", missing(c.get("solvent_model"))), ("溶剂", missing(c.get("solvent_name"))),
                 ("电荷 / 多重度", f"{missing(c['charge'])} / {missing(c['multiplicity'])}"), ("原子数", missing(c["atom_count"])),
                 ("最终电子能量", span(("尚无最终值", "muted")) if c["final_energy_eh"] is None else f"<b>{c['final_energy_eh']!r}</b> Eh"),
                 ("解析状态", span(status(PARSE, c["status"]))),
                 ("计算终止", span(status(CALC, c["calculation_status"])) + "<span style='color:#8a9bb0'>　仅表示程序终止证据，不等于几何优化收敛</span>"),
                 ("终止标志", missing(c.get("termination"))),
                 ("几何收敛", span({True: ("已收敛", "ok"), False: ("未收敛", "bad"), None: ("未知（输出中没有可用证据）", "muted")}[geometry])),
                 ("频率", f"{f['count']} 个，其中虚频 {f['imaginary_count']} 个" if f else span(("无频率数据", "muted")))]
        pairs += [(f"热化学 · {name}", f"{t['value']!r} {esc(t['unit'])}　<span style='color:#8a9bb0'>{esc(source_text(t['source_location']))}</span>")
                  for name, t in c["thermochemistry"].items()]
        for group in c.get('basis_groups', []):
            pairs.append(("基组 · " + '/'.join(group['elements']),
                          esc(group['basis_set']) + " · 原子 " + esc(', '.join(map(str, group['centers'])))))
        if c.get('ecp_centers'):
            pairs.append(("ECP", '<br>'.join(esc(f"{e['element'] or '?'} #{e['center']}: {e['core_electrons']} 个核心电子")
                                             for e in c['ecp_centers'])))
        unavailable = [name for name, state in c["field_status"].items() if state != "available"]
        pairs += [("不可用字段", esc("、".join(unavailable)) if unavailable else "无"),
                  ("来源文件", esc(c["source_path"])), ("解析时间 / 解析器", esc(f"{when(c['parsed_at'])} · {c['parser_version']}")),
                  ("calculation_id", esc(c["calculation_id"]))]
        self.summary.setHtml(detail_html(pairs, c["warnings"] + [s["warning"] for s in c["stages"] if s.get("warning")]))

    def load_section(self, table, chart, name, section, cells, **params):
        key = self.calc_id
        table.loading()

        def done(data):
            table.fill(data, cells)
            chart.set([(name(item), item["value"]) for item in data["items"] if item["value"] is not None])

        def failed(message):
            table.message(message)
            chart.set([])
        self.request(lambda: self.client.get(f"/calculations/{key}/{section}", offset=table.offset, limit=table.page_size, **params),
                     self.for_calc(done), self.for_calc(failed))

    def load_energies(self):
        self.energies.empty_text = "这条记录没有解析出能量。"
        self.load_section(self.energies, self.energy_chart, lambda e: f"步骤 {e['step']} · {e['kind']}", "energies", lambda e: [str(e["step"]), e["kind"], repr(e["value"]), e["stage_id"] or "—", source_text(e["source_location"])])

    def load_frequencies(self):
        self.frequencies.empty_text = "没有虚频。" if self.imaginary.isChecked() else "这条记录没有频率数据。"
        cells = lambda f: [str(f["mode"]), (repr(f["value"]), "bad") if f["value"] is not None and f["value"] < 0 else "—" if f["value"] is None else repr(f["value"]),
                           f["stage_id"] or "—", source_text(f["source_location"])]
        self.load_section(self.frequencies, self.spectrum, lambda f: f"模式 {f['mode']}", "frequencies", cells, imaginary_only="true" if self.imaginary.isChecked() else None)

    def load_structure(self, index=None):
        key = self.calc_id
        self.clear_structure()

        def done(data):
            total = data["total"]
            if index is None and total > 1:
                return self.load_structure(total - 1)
            for widget in self.structure_tools:
                widget.setEnabled(bool(total))
            if not total:
                self.structure = None
                self.xyz.setPlainText("")
                self.molecule.set([], [])
                return self.structure_info.setText("这条记录没有解析出结构。")
            self.structure, self.structure_index = data["items"][0], data["offset"]
            self.structure_prev.setEnabled(self.structure_index > 0)
            self.structure_next.setEnabled(self.structure_index < total - 1)
            stage = self.structure["stage_id"] or "未与能量步骤匹配"
            self.structure_info.setText(f"结构 {self.structure_index + 1} / {total}（默认显示最后一个）· {len(self.structure['symbols'])} 个原子 · Å · "
                                        f"来源 {source_text(self.structure['source_location'])} · 阶段：{stage}")
            self.xyz.setPlainText(as_xyz(self.structure))
            self.molecule.set(self.structure["symbols"], self.structure["coordinates"])

        def failed(message):
            self.clear_structure(message)
        self.request(lambda: self.client.get(f"/calculations/{key}/structures", offset=index or 0, limit=1), self.for_calc(done), self.for_calc(failed))

    def copy_xyz(self):
        copy(self.xyz.toPlainText())
        self.notify("已复制 XYZ 到剪贴板。", "ok")

    def save_xyz(self):
        name = f"{Path(self.structure['source_location']['path']).stem}-{self.structure_index}.xyz"
        path, _ = QFileDialog.getSaveFileName(self, "保存 XYZ", name, "XYZ (*.xyz)")
        if path:
            Path(path).write_text(self.xyz.toPlainText(), encoding="utf-8")
            self.notify("已保存 " + path, "ok")

    # ---- Settings --------------------------------------------------------

    def build_settings(self):
        layout = self.page("设置", "单用户本地服务。密码和私钥不会保存到应用数据库。")
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        self.setting = {key: label("…", "plain", wrap=False, selectable=True) for key in ("home", "version", "parser_version", "capabilities")}
        url = label(self.client.url, "plain", wrap=False, selectable=True)
        form.addRow(label("API 地址", wrap=False), row(url, button("复制", lambda: copy(self.client.url), "flat")))
        form.addRow("", label("启动前设置环境变量 CHEMCTL_URL 可更改地址；运行中不可切换。"))
        form.addRow(label("数据目录", wrap=False), row(self.setting["home"], button("复制", lambda: copy(self.setting["home"].text()), "flat"),
                                                    button("在资源管理器中打开", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.setting["home"].text())), "flat")))
        form.addRow(label("程序版本", wrap=False), self.setting["version"])
        form.addRow(label("解析器版本", wrap=False), self.setting["parser_version"])
        form.addRow(label("服务能力", wrap=False), self.setting["capabilities"])
        layout.addWidget(card)

        backup = QFrame()
        backup.setObjectName("card")
        backup_layout = QVBoxLayout(backup)
        backup_layout.setContentsMargins(20, 16, 20, 16)
        backup_layout.addWidget(label("数据库备份", "section"))
        backup_layout.addWidget(label("在数据目录的 backups 文件夹中创建一份 SQLite 数据库副本。不会改动现有数据。"))
        self.backup_button = button("立即创建备份", self.create_backup, True)
        self.backup_path = label(selectable=True)
        backup_layout.addLayout(row(self.backup_button, self.backup_path))
        layout.addWidget(backup)
        layout.addStretch()

    def refresh_settings(self):
        def show(data):
            for key, widget in self.setting.items():
                widget.setText("、".join(data[key]) if key == "capabilities" else data[key])
        self.request(lambda: self.client.get("/health"), show)

    def create_backup(self):
        def done(data):
            self.backup_path.setText("最近一次备份：" + data["path"])
            self.notify("备份已创建：" + data["path"], "ok")
        self.request(lambda: self.client.post("/system/backup"), done, busy=self.backup_button)

    def closeEvent(self, event):
        # Close at once; late replies are dropped by request(). main() lets worker threads end on their own.
        self.closing = True
        self.timer.stop()
        event.accept()


def load_fonts():
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc", "consola.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / name))


def main():
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("chemctl.Desktop")
    application = QApplication(sys.argv)
    application.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "chemctl.ico")))
    load_fonts()
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    window = Window()
    window.show()
    code = application.exec()
    QThreadPool.globalInstance().waitForDone()
    sys.exit(code)


if __name__ == "__main__":
    main()
