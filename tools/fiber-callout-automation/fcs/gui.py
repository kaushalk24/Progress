# -*- coding: utf-8 -*-
"""FiberCallout Studio - PyQt6 desktop interface."""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, QPointF, QSettings, QSortFilterProxyModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QKeySequence, QPainter, QPen, QPolygonF,
                         QStandardItem, QStandardItemModel, QTextCharFormat, QTextCursor)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDockWidget, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                             QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QStyleFactory,
                             QTableView, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from . import APP_NAME, APP_ORG, APP_VERSION
from .branding import app_icon, logo_pixmap
from .engine import (ADDRESS_FIELDS, CadMap, CalloutEngine, CalloutSpec, Cancelled, ColumnMap, Reporter, RunConfig,
                     RunResult, ScanResult, find_oda_converter, fmt_numbers)

AUTO = "(auto-detect)"
LEVEL_COLORS = {"ERROR": "#C62828", "WARNING": "#B26A00", "SUCCESS": "#1B7F3B", "DEBUG": "#7A8594", "INFO": "#1F2933"}
PRIMARY = "#0B3954"
ACCENT = "#13808C"

QSS = f"""
QMainWindow, QWidget#page {{ background: #F3F5F8; }}
QWidget {{ font-size: 10pt; color: #1F2933; }}
QFrame#header {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0B2545, stop:1 {ACCENT}); }}
QLabel#appTitle {{ color: white; font-size: 17pt; font-weight: 600; }}
QLabel#appSub {{ color: #CFE8EC; font-size: 9.5pt; }}
QLabel#appVer {{ color: #CFE8EC; font-size: 9pt; }}
QListWidget#nav {{ background: #FFFFFF; border: none; border-right: 1px solid #DDE3EA; padding-top: 8px; outline: 0; }}
QListWidget#nav::item {{ padding: 11px 14px; margin: 2px 8px; border-radius: 6px; color: #3E4C59; }}
QListWidget#nav::item:selected {{ background: #E3F1F3; color: {PRIMARY}; font-weight: 600; }}
QListWidget#nav::item:hover {{ background: #F0F4F8; }}
QFrame#card {{ background: #FFFFFF; border: 1px solid #DDE3EA; border-radius: 8px; }}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 600; color: {PRIMARY}; }}
QLabel#hint {{ color: #66788A; font-size: 9pt; }}
QLabel#pageTitle {{ font-size: 15pt; font-weight: 600; color: {PRIMARY}; }}
QPushButton {{ background: #FFFFFF; border: 1px solid #C5CED8; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; background: #F2FAFB; }}
QPushButton:disabled {{ color: #A0AAB4; background: #F3F5F8; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600; padding: 8px 20px; }}
QPushButton#primary:hover {{ background: #0F6E78; }}
QPushButton#primary:disabled {{ background: #9CC7CC; }}
QPushButton#secondary {{ background: {PRIMARY}; color: white; border: none; font-weight: 600; padding: 8px 18px; }}
QPushButton#secondary:hover {{ background: #0A2F45; }}
QPushButton#danger {{ color: #C62828; }}
QLineEdit, QComboBox {{ background: white; border: 1px solid #C5CED8; border-radius: 5px;
    padding: 4px 6px; min-height: 22px; }}
QSpinBox, QDoubleSpinBox {{ background: white; min-height: 26px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QListWidget#files {{ background: #FAFBFC; border: 1px dashed #B8C4CF; border-radius: 6px; }}
QProgressBar {{ border: 1px solid #C5CED8; border-radius: 6px; background: white; text-align: center; height: 18px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QFrame#actionBar {{ background: #FFFFFF; border-top: 1px solid #DDE3EA; }}
QFrame#kpi {{ background: white; border: 1px solid #DDE3EA; border-radius: 8px; }}
QLabel#kpiValue {{ font-size: 20pt; font-weight: 600; }}
QLabel#kpiTitle {{ color: #66788A; font-size: 9pt; }}
QTableView {{ background: white; border: 1px solid #DDE3EA; gridline-color: #EEF1F4; selection-background-color: #D7ECEF;
    selection-color: #1F2933; }}
QHeaderView::section {{ background: #EEF2F6; border: none; border-right: 1px solid #DDE3EA; padding: 5px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid #DDE3EA; background: white; border-radius: 6px; }}
QTabBar::tab {{ padding: 7px 16px; background: #E9EDF2; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: white; color: {PRIMARY}; font-weight: 600; }}
QDockWidget::title {{ background: #E9EDF2; padding: 5px; }}
"""

QUICK_GUIDE = f"""
<h2>{APP_NAME}</h2>
<p>Generates the magenta <b>DES_FIBER_SPL</b> multileader callouts of an FTTx design from its splice reports and
address lists, exactly as drafted in the reference design.</p>
<h3>Workflow</h3>
<ol>
<li><b>Project</b> - pick the design drawing (.dwg or .dxf), add the splice reports and address lists (files, folders
or .zip archives) and an output folder. Drag &amp; drop works everywhere.</li>
<li><b>Scan &amp; Auto-Detect</b> - reads everything and fills <b>Columns</b> and <b>CAD Mapping</b> automatically
(closure blocks + name attribute, handhole blocks, cable layers, address-list columns, splitter size, units).
Review and override anything; <i>(auto-detect)</i> means the tool decides on every run.</li>
<li><b>Validate</b> - dry run: missing closures, address-list / splice-report mismatches, orphan addresses,
missing cable geometry and placement problems. Nothing is written.</li>
<li><b>Generate Callouts</b> - writes the drawing and the QA/QC workbook. Results shows every callout and how its
numbers were calculated.</li>
</ol>
<h3>Rules</h3>
<ul>
<li>Fiber number <b>N = (PON - 1) x splitter size + PON PORT</b>, per OLM.</li>
<li><b>Fiber-number callout</b>: one per terminal + drop closure (per contiguous run): <tt>12</tt>, <tt>218-219</tt>;
arrow on the handhole hosting the drop closure.</li>
<li><b>BFO callout</b>: one per live cable segment leaving a closure that has a splice report:
<tt>BFO 72 / 70-115</tt> = cable fiber count / lowest-highest fiber number carried; arrow on the cable.</li>
</ul>
<h3>DWG files</h3>
<p>DWG 2010-2025 drawings are read by the built-in reader. Without the ODA File Converter the tool writes a
<b>callouts DXF</b> (same coordinates) and an <b>AutoCAD script</b>: open the DWG in AutoCAD, type <tt>SCRIPT</tt>
and pick the .scr file - existing fiber callouts are replaced and the new ones inserted. With the free ODA File
Converter installed the complete drawing is written directly as DWG.</p>
"""


# =============================================================================
# Worker
# =============================================================================
class Worker(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, task: str, cfg: RunConfig, cancel: threading.Event) -> None:
        super().__init__()
        self.task, self.cfg, self.cancel = task, cfg, cancel

    def run(self) -> None:
        rep = Reporter(lambda m, l: self.log.emit(m, l), lambda p, m: self.progress.emit(p, m), self.cancel)
        try:
            if self.task == "selftest":
                from .selftest import run_selftest
                ok, text = run_selftest(verbose=False, log=lambda m: self.log.emit(m, "INFO"))
                self.finished.emit(self.task, (ok, text))
                return
            eng = CalloutEngine(self.cfg, rep)
            res = {"scan": eng.scan, "validate": eng.validate, "generate": eng.generate}[self.task]()
            self.finished.emit(self.task, res)
        except Cancelled:
            self.failed.emit(self.task, "Cancelled by user")
        except Exception as exc:  # noqa: BLE001 - every failure is reported in the GUI
            self.log.emit(traceback.format_exc(), "DEBUG")
            self.failed.emit(self.task, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Widgets
# =============================================================================
def card(title: str, hint: str = "") -> tuple:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    lay.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return f, lay


class PathEdit(QLineEdit):
    dropped = pyqtSignal(str)

    def __init__(self, placeholder: str = "") -> None:
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e: Any) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: Any) -> None:  # noqa: N802
        urls = e.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())
            self.dropped.emit(self.text())


class FileList(QWidget):
    changed = pyqtSignal()

    def __init__(self, filt: str, hint: str) -> None:
        super().__init__()
        self.filt = filt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMinimumHeight(74)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter  # type: ignore[assignment]
        self.list.dragMoveEvent = self._drag_enter  # type: ignore[assignment]
        self.list.dropEvent = self._drop  # type: ignore[assignment]
        self.list.setToolTip(hint)
        row = QHBoxLayout()
        for label, fn in (("Add files...", self.add_files), ("Add folder...", self.add_folder),
                          ("Remove", self.remove), ("Clear", self.clear)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.count = QLabel("")
        self.count.setObjectName("hint")
        row.addWidget(self.count)
        lay.addWidget(self.list)
        lay.addLayout(row)
        self._update()

    def _drag_enter(self, e: Any) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def _drop(self, e: Any) -> None:
        for u in e.mimeData().urls():
            self.add(u.toLocalFile())

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select files", "", self.filt)
        for f in files:
            self.add(f)

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            self.add(d)

    def add(self, path: str) -> None:
        if path and path not in self.paths():
            pp = Path(path)
            kind = "Folder" if pp.is_dir() else ("ZIP" if pp.suffix.lower() == ".zip" else pp.suffix.upper().lstrip("."))
            it = QListWidgetItem(f"{pp.name}    [{kind}]    {pp.parent}")
            it.setToolTip(path)
            it.setData(Qt.ItemDataRole.UserRole, path)
            self.list.addItem(it)
            self._update()

    def remove(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._update()

    def clear(self) -> None:
        self.list.clear()
        self._update()

    def set_paths(self, paths: List[str]) -> None:
        self.list.clear()
        for p in paths:
            self.add(p)
        self._update()

    def paths(self) -> List[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def _update(self) -> None:
        n = self.list.count()
        self.count.setText(f"{n} item(s)" if n else "drop files, folders or .zip here")
        self.changed.emit()


class CalloutPreview(QWidget):
    """Shows how the callouts will look in AutoCAD (dark model space)."""

    def __init__(self) -> None:
        super().__init__()
        self.prefix = "BFO"
        self.setMinimumSize(360, 230)

    def paintEvent(self, _e: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#212830"))
        mag = QColor("#FF00FF")
        green = QColor("#3DBE3D")
        p.setPen(QPen(QColor("#E0E0E0"), 1))
        p.drawLine(0, int(h * 0.30), w, int(h * 0.30))
        p.drawLine(0, int(h * 0.82), w, int(h * 0.82))
        p.setPen(QPen(green, 3))
        cy = h * 0.56
        p.drawLine(0, int(cy), w, int(cy))
        cx = w * 0.55
        p.setBrush(green)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(cx - 22, cy - 13), QPointF(cx, cy), QPointF(cx - 22, cy + 13)]))
        p.drawPolygon(QPolygonF([QPointF(cx + 22, cy - 13), QPointF(cx, cy), QPointF(cx + 22, cy + 13)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#E0E0E0"), 1.5))
        hx, hy = w * 0.80, h * 0.70
        p.drawRect(int(hx - 12), int(hy - 12), 24, 24)
        font = QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono")
        font.setPixelSize(15)
        p.setFont(font)
        fm = p.fontMetrics()

        def callout(land: QPointF, lines: List[str], tip: QPointF) -> None:
            # MLEADER: the landing sits under the first text line, on the side facing the arrow
            tw = max(fm.horizontalAdvance(x) for x in lines)
            text_left = tip.x() >= land.x()
            x0 = land.x() - 3 - tw if text_left else land.x() + 3
            p.setPen(mag)
            for i, t in enumerate(lines):
                p.drawText(QPointF(x0, land.y() - 4 + i * 19), t)
            p.setPen(QPen(mag, 1.2))
            p.drawLine(QPointF(x0, land.y()), QPointF(x0 + tw, land.y()))
            p.drawLine(QPointF(x0 + tw if text_left else x0, land.y()), land)
            p.drawLine(land, tip)
            dx, dy = tip.x() - land.x(), tip.y() - land.y()
            ln = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            ux, uy = dx / ln, dy / ln
            b = QPointF(tip.x() - ux * 11, tip.y() - uy * 11)
            p.setBrush(mag)
            p.drawPolygon(QPolygonF([tip, QPointF(b.x() - uy * 3.5, b.y() + ux * 3.5), QPointF(b.x() + uy * 3.5, b.y() - ux * 3.5)]))
            p.setBrush(Qt.BrushStyle.NoBrush)
        callout(QPointF(w * 0.30, h * 0.16), [f"{self.prefix} 72", "70-115"], QPointF(cx - 60, cy))
        callout(QPointF(w * 0.48, h * 0.73), [f"{self.prefix} 72", "2-69"], QPointF(cx + 55, cy))
        callout(QPointF(w * 0.70, h * 0.90), ["69"], QPointF(hx - 12, hy + 12))
        p.setPen(QColor("#8A96A3"))
        f2 = QFont()
        f2.setPixelSize(11)
        p.setFont(f2)
        p.drawText(8, h - 8, "Preview - layer DES_FIBER_SPL (ACI 6), MULTILEADER")
        p.end()



class Kpi(QFrame):
    def __init__(self, title: str, color: str) -> None:
        super().__init__()
        self.setObjectName("kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        bar = QFrame()
        bar.setFixedHeight(4)
        bar.setStyleSheet(f"background:{color}; border-radius:2px;")
        self.value = QLabel("-")
        self.value.setObjectName("kpiValue")
        self.value.setStyleSheet(f"color:{color};")
        t = QLabel(title)
        t.setObjectName("kpiTitle")
        lay.addWidget(bar)
        lay.addWidget(self.value)
        lay.addWidget(t)

    def set(self, v: Any) -> None:
        self.value.setText(str(v))


class Table(QWidget):
    def __init__(self, placeholder: str = "Search...") -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.model = QStandardItemModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        lay.addWidget(self.search)
        lay.addWidget(self.view)

    def fill(self, rows: List[Dict[str, Any]], colors: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None) -> None:
        self.model.clear()
        if not rows:
            return
        headers: List[str] = []
        for r in rows:
            for k in r:
                if k not in headers:
                    headers.append(k)
        self.model.setHorizontalHeaderLabels(headers)
        for r in rows:
            col = colors(r) if colors else None
            items = []
            for h in headers:
                v = r.get(h)
                it = QStandardItem("" if v is None else str(v))
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it.setData(v, Qt.ItemDataRole.UserRole)
                if col:
                    it.setBackground(QBrush(QColor(col)))
                items.append(it)
            self.model.appendRow(items)
        hdr = self.view.horizontalHeader()
        for i in range(len(headers)):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.view.resizeColumnToContents(i)
            if self.view.columnWidth(i) > 380:
                self.view.setColumnWidth(i, 380)


# =============================================================================
# Main window
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1320, 900)
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.cancel = threading.Event()
        self.outputs: Dict[str, str] = {}
        self.scan: Optional[ScanResult] = None
        self.log_lines: List[tuple] = []
        self._build()
        self._restore()
        QTimer.singleShot(0, self._startup_info)

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        self._menus()
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        body = QHBoxLayout()
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(210)
        for t in ("1   Project", "2   Columns", "3   CAD Mapping", "4   Callout Style", "5   Results"):
            self.nav.addItem(QListWidgetItem(t))
        self.stack = QStackedWidget()
        for page in (self._page_project(), self._page_columns(), self._page_cad(), self._page_style(), self._page_results()):
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        root.addWidget(self._action_bar())
        self.setCentralWidget(central)
        self._log_dock()
        self.statusBar().showMessage("Ready")

    def _menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for text, fn, key in (("New project", self.new_project, "Ctrl+N"), ("Open project...", self.open_project, "Ctrl+O"),
                              ("Save project...", self.save_project, "Ctrl+S")):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(fn)
            m.addAction(a)
        m.addSeparator()
        a = QAction("Exit", self)
        a.triggered.connect(self.close)
        m.addAction(a)
        m = mb.addMenu("&Tools")
        a = QAction("Run built-in self-test", self)
        a.triggered.connect(lambda: self.start("selftest"))
        m.addAction(a)
        a = QAction("Locate ODA File Converter", self)
        a.triggered.connect(self._locate_oda)
        m.addAction(a)
        a = QAction("Open output folder", self)
        a.triggered.connect(self.open_output_folder)
        m.addAction(a)
        m = mb.addMenu("&Help")
        a = QAction("Quick guide", self)
        a.setShortcut(QKeySequence("F1"))
        a.triggered.connect(self.show_guide)
        m.addAction(a)
        a = QAction(f"About {APP_NAME}", self)
        a.triggered.connect(self.show_about)
        m.addAction(a)

    def _header(self) -> QWidget:
        f = QFrame()
        f.setObjectName("header")
        f.setFixedHeight(78)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(18, 8, 18, 8)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(56))
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(APP_NAME)
        t.setObjectName("appTitle")
        s = QLabel("Automated DES_FIBER_SPL fiber-number callouts for FTTx OSP designs - splice reports + address lists -> CAD")
        s.setObjectName("appSub")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col, 1)
        v = QLabel(f"v{APP_VERSION}")
        v.setObjectName("appVer")
        lay.addWidget(v)
        return f

    def _scroll(self, title: str, subtitle: str) -> tuple:
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)
        tl = QLabel(title)
        tl.setObjectName("pageTitle")
        st = QLabel(subtitle)
        st.setObjectName("hint")
        st.setWordWrap(True)
        lay.addWidget(tl)
        lay.addWidget(st)
        sc.setWidget(inner)
        outer.addWidget(sc)
        return page, lay

    def _row(self, *widgets: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        return w

    def _browse_btn(self, fn: Callable[[], None]) -> QPushButton:
        b = QPushButton("Browse...")
        b.clicked.connect(fn)
        return b

    def _page_project(self) -> QWidget:
        page, lay = self._scroll("Project", "Select the design drawing, its splice reports and address lists. Files, folders "
                                            "and .zip archives are accepted; drag & drop works on every field.")
        c, cl = card("Design drawing", "AutoCAD DWG (2010-2025) or DXF of the FTTx design. DWG files are read by the "
                                       "built-in reader, or by the ODA File Converter when installed.")
        self.ed_drawing = PathEdit("Drop a .dwg / .dxf here or click Browse")
        self.ed_drawing.dropped.connect(lambda _p: self._drawing_changed())
        self.ed_drawing.editingFinished.connect(self._drawing_changed)
        cl.addWidget(self._row(self.ed_drawing, self._browse_btn(self.pick_drawing)))
        self.lbl_drawing = QLabel("")
        self.lbl_drawing.setObjectName("hint")
        cl.addWidget(self.lbl_drawing)
        lay.addWidget(c)
        grid = QGridLayout()
        grid.setSpacing(14)
        c1, l1 = card("Splice reports", "Splice Connections Report or Fiber Optic Splice Guide workbooks (.xlsx/.xls/.csv).")
        self.fl_splice = FileList("Splice reports (*.xlsx *.xlsm *.xls *.csv *.zip);;All files (*)", "Drop splice reports here")
        l1.addWidget(self.fl_splice)
        c2, l2 = card("Address lists", "One or more address lists (PON, port, address, terminal, drop splice).")
        self.fl_addr = FileList("Address lists (*.xlsx *.xlsm *.xls *.csv *.zip);;All files (*)", "Drop address lists here")
        self.fl_addr.changed.connect(self._addresses_changed)
        l2.addWidget(self.fl_addr)
        grid.addWidget(c1, 0, 0)
        grid.addWidget(c2, 0, 1)
        lay.addLayout(grid)
        c, cl = card("Output & options")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        self.ed_output = PathEdit("Default: <drawing folder>\\callout_output")
        form.addRow("Output folder:", self._row(self.ed_output, self._browse_btn(self.pick_output)))
        self.cb_existing = QComboBox()
        self.cb_existing.addItems(["Replace existing fiber callouts", "Keep existing, add only missing callouts",
                                   "Keep existing, add all callouts"])
        form.addRow("Existing callouts:", self.cb_existing)
        self.cb_reader = QComboBox()
        self.cb_reader.addItems(["Automatic (ODA if installed, else built-in)", "Built-in DWG reader", "ODA File Converter"])
        form.addRow("DWG reader:", self.cb_reader)
        self.ed_oda = PathEdit("Optional - ODAFileConverter.exe (auto-detected in Program Files)")
        form.addRow("ODA File Converter:", self._row(self.ed_oda, self._browse_btn(self.pick_oda)))
        self.chk_dwg = QCheckBox("Write DWG output when the ODA File Converter is available")
        self.chk_dwg.setChecked(True)
        self.cb_dwgver = QComboBox()
        self.cb_dwgver.addItems(["R2018", "R2013", "R2010", "R2007", "R2004", "R2000"])
        form.addRow("DWG output:", self._row(self.chk_dwg, QLabel("version"), self.cb_dwgver))
        self.cb_units = QComboBox()
        self.cb_units.addItems(["auto", "feet", "meters", "inches"])
        form.addRow("Drawing units:", self.cb_units)
        self.sp_ports = QSpinBox()
        self.sp_ports.setRange(0, 1024)
        self.sp_ports.setSpecialValueText("auto (splitter size from splice reports)")
        form.addRow("Ports per PON:", self.sp_ports)
        cl.addLayout(form)
        lay.addWidget(c)
        lay.addStretch(1)
        return page

    def _page_columns(self) -> QWidget:
        page, lay = self._scroll("Address-list columns", "Columns are matched automatically per file by name (synonyms "
                                 "and fuzzy matching). Override a field only if the auto-detection picked the wrong column.")
        c, cl = card("Column mapping", "* required.  The fiber number is computed as (PON - 1) x splitter size + PORT.")
        form = QFormLayout()
        self.col_boxes: Dict[str, QComboBox] = {}
        for k, (req, _syn, desc) in ADDRESS_FIELDS.items():
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItem(AUTO)
            self.col_boxes[k] = cb
            form.addRow(f"{desc}{' *' if req else ''}:", cb)
        cl.addLayout(form)
        lay.addWidget(c)
        lay.addStretch(1)
        return page

    def _page_cad(self) -> QWidget:
        page, lay = self._scroll("CAD mapping", "How the network is drawn. Leave (auto-detect) to let the tool identify it "
                                 "on every run from geometry and the closure names in your data - recommended for new regions.")
        c, cl = card("Network objects")
        form = QFormLayout()
        self.cb_cl_layer, self.cb_cl_block, self.cb_cl_tag = QComboBox(), QComboBox(), QComboBox()
        self.cb_hh_layer, self.cb_term_layer = QComboBox(), QComboBox()
        for cb in (self.cb_cl_layer, self.cb_cl_block, self.cb_cl_tag, self.cb_hh_layer, self.cb_term_layer):
            cb.setEditable(True)
            cb.addItem(AUTO)
        self.cb_cl_layer.currentTextChanged.connect(self._refresh_closure_blocks)
        self.cb_hh_layer.currentTextChanged.connect(lambda _t: self._refresh_hh_blocks(None))
        form.addRow("Splice closure layer:", self.cb_cl_layer)
        form.addRow("Splice closure block:", self.cb_cl_block)
        form.addRow("Closure name attribute:", self.cb_cl_tag)
        form.addRow("Handhole layer:", self.cb_hh_layer)
        self.lst_hh = QListWidget()
        self.lst_hh.setMaximumHeight(120)
        form.addRow("Handhole blocks (checked; none = auto):", self.lst_hh)
        form.addRow("Terminal layer:", self.cb_term_layer)
        self.lst_cables = QListWidget()
        self.lst_cables.setMaximumHeight(160)
        form.addRow("Cable layers (checked; none = auto):", self.lst_cables)
        self.sp_snap = QDoubleSpinBox()
        self.sp_snap.setRange(0.0, 50.0)
        self.sp_snap.setDecimals(2)
        self.sp_snap.setSpecialValueText("auto")
        form.addRow("Cable-to-closure snap tolerance:", self.sp_snap)
        cl.addLayout(form)
        b = QPushButton("Reset all to auto-detect")
        b.clicked.connect(self._reset_cad)
        cl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(c)
        lay.addStretch(1)
        return page

    def _page_style(self) -> QWidget:
        page, lay = self._scroll("Callout style", "Defaults reproduce the reference DES_FIBER_SPL standard exactly "
                                 "(lengths in feet; converted automatically for metric drawings).")
        h = QHBoxLayout()
        c, cl = card("Drafting standard")
        form = QFormLayout()
        s = CalloutSpec()
        self.style_w: Dict[str, Any] = {}

        def add(name: str, label: str, w: QWidget) -> None:
            self.style_w[name] = w
            form.addRow(label, w)

        def ds(val: float, lo: float, hi: float, dec: int = 2) -> QDoubleSpinBox:
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setDecimals(dec)
            sp.setValue(val)
            return sp
        add("cable_layer", "BFO callout layer:", QLineEdit(s.cable_layer))
        add("terminal_layer", "Fiber-number callout layer:", QLineEdit(s.terminal_layer))
        sp = QSpinBox()
        sp.setRange(1, 255)
        sp.setValue(s.layer_color)
        add("layer_color", "Layer color (ACI, for new layers):", sp)
        add("text_style", "Text style:", QLineEdit(s.text_style))
        add("text_style_font", "Font (new style):", QLineEdit(s.text_style_font))
        add("mleader_style", "MLEADER style:", QLineEdit(s.mleader_style))
        add("text_height", "Text height:", ds(s.text_height, 0.01, 1000))
        add("arrow_size", "Arrow size:", ds(s.arrow_size, 0.0, 1000))
        add("landing_gap", "Landing gap:", ds(s.landing_gap, 0.0, 100, 3))
        add("dogleg_length", "Dogleg length:", ds(s.dogleg_length, 0.0, 100, 3))
        add("terminal_leader_length", "Fiber-number leader length:", ds(s.terminal_leader_length, 0.5, 1000))
        add("cable_leader_length", "BFO leader length:", ds(s.cable_leader_length, 0.5, 1000))
        add("cable_offset_along", "BFO arrow distance from closure:", ds(s.cable_offset_along, 0.0, 1000))
        add("handhole_search_radius", "Handhole search radius:", ds(s.handhole_search_radius, 1.0, 5000, 1))
        ed = QLineEdit(s.cable_prefix)
        ed.textChanged.connect(self._update_preview)
        add("cable_prefix", "Cable callout prefix:", ed)
        sp = QSpinBox()
        sp.setRange(0, 6)
        sp.setValue(s.zero_pad)
        sp.setSpecialValueText("none (3, 12)")
        add("zero_pad", "Zero padding:", sp)
        cb = QComboBox()
        cb.addItems(["span", "exact"])
        add("cable_range_mode", "BFO range (span = lowest-highest):", cb)
        ch = QCheckBox("One callout per contiguous run (reference behaviour)")
        ch.setChecked(s.split_terminal_runs)
        add("split_terminal_runs", "Non-contiguous terminals:", ch)
        cl.addLayout(form)
        b = QPushButton("Reset to DES_FIBER_SPL standard")
        b.clicked.connect(self._reset_style)
        cl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        h.addWidget(c, 3)
        c2, cl2 = card("Preview", "Magenta MULTILEADER, MText underlined top line, closed-filled arrow, dogleg landing.")
        self.preview = CalloutPreview()
        cl2.addWidget(self.preview)
        cl2.addStretch(1)
        h.addWidget(c2, 2)
        lay.addLayout(h)
        lay.addStretch(1)
        return page

    def _page_results(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 18, 24, 12)
        t = QLabel("Results")
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        self.lbl_result = QLabel("Run Validate or Generate to see results.")
        self.lbl_result.setObjectName("hint")
        lay.addWidget(self.lbl_result)
        k = QHBoxLayout()
        self.kpi_t = Kpi("Fiber-number callouts", ACCENT)
        self.kpi_c = Kpi("BFO callouts", PRIMARY)
        self.kpi_clean = Kpi("Clean placement", "#1B7F3B")
        self.kpi_e = Kpi("Errors", "#C62828")
        self.kpi_w = Kpi("Warnings", "#B26A00")
        for w in (self.kpi_t, self.kpi_c, self.kpi_clean, self.kpi_e, self.kpi_w):
            k.addWidget(w)
        lay.addLayout(k)
        self.tabs = QTabWidget()
        self.tbl_callouts = Table("Search callouts (text, closure, OLM, status...)")
        self.tbl_issues = Table("Search issues...")
        self.tbl_network = Table("Search...")
        self.tbl_existing = Table("Search...")
        self.tabs.addTab(self.tbl_callouts, "Callouts")
        self.tabs.addTab(self.tbl_issues, "Validation issues")
        self.tabs.addTab(self.tbl_network, "Network summary")
        self.tabs.addTab(self.tbl_existing, "Existing vs computed")
        lay.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        self.btn_open_folder = QPushButton("Open output folder")
        self.btn_open_qa = QPushButton("Open QA workbook")
        self.btn_open_dwg = QPushButton("Open drawing output")
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        self.btn_open_qa.clicked.connect(lambda: self._open(self.outputs.get("QA workbook")))
        self.btn_open_dwg.clicked.connect(lambda: self._open(self.outputs.get("DWG") or self.outputs.get("DXF")
                                                             or self.outputs.get("Callouts DXF")))
        for b in (self.btn_open_folder, self.btn_open_qa, self.btn_open_dwg):
            b.setEnabled(False)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _action_bar(self) -> QWidget:
        f = QFrame()
        f.setObjectName("actionBar")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(18, 10, 18, 10)
        self.btn_scan = QPushButton("Scan && Auto-Detect")
        self.btn_validate = QPushButton("Validate")
        self.btn_validate.setObjectName("secondary")
        self.btn_generate = QPushButton("Generate Callouts")
        self.btn_generate.setObjectName("primary")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setEnabled(False)
        self.btn_scan.clicked.connect(lambda: self.start("scan"))
        self.btn_validate.clicked.connect(lambda: self.start("validate"))
        self.btn_generate.clicked.connect(lambda: self.start("generate"))
        self.btn_cancel.clicked.connect(self.cancel_job)
        for b in (self.btn_scan, self.btn_validate, self.btn_generate, self.btn_cancel):
            lay.addWidget(b)
        lay.addSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Ready")
        self.status.setObjectName("hint")
        col.addWidget(self.progress)
        col.addWidget(self.status)
        lay.addLayout(col, 1)
        return f

    def _log_dock(self) -> None:
        dock = QDockWidget("Activity log", self)
        dock.setObjectName("logDock")
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 4, 6, 6)
        row = QHBoxLayout()
        self.cb_level = QComboBox()
        self.cb_level.addItems(["All messages", "Warnings and errors", "Errors only"])
        self.cb_level.currentIndexChanged.connect(self._render_log)
        b1 = QPushButton("Clear")
        b1.clicked.connect(self._clear_log)
        b2 = QPushButton("Save log...")
        b2.clicked.connect(self._save_log)
        row.addWidget(QLabel("Show:"))
        row.addWidget(self.cb_level)
        row.addStretch(1)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 9))
        lay.addWidget(self.console)
        dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [230], Qt.Orientation.Vertical)

    # ----------------------------------------------------------------- helpers
    def _startup_info(self) -> None:
        oda = find_oda_converter(self.ed_oda.text().strip())
        self.statusBar().showMessage(f"ODA File Converter: {oda}" if oda else
                                     "ODA File Converter not found - DWG files are read with the built-in reader")
        self._log(f"{APP_NAME} {APP_VERSION} ready. " + ("ODA File Converter found: " + oda if oda else
                  "DWG 2010-2025 supported by the built-in reader (ODA File Converter optional)."), "INFO")

    def _log(self, msg: str, level: str) -> None:
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((stamp, level, msg))
        if self._visible(level):
            self._append(stamp, level, msg)

    def _visible(self, level: str) -> bool:
        i = self.cb_level.currentIndex()
        return i == 0 or (i == 1 and level in ("WARNING", "ERROR", "SUCCESS")) or (i == 2 and level == "ERROR")

    def _append(self, stamp: str, level: str, msg: str) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(LEVEL_COLORS.get(level, "#1F2933")))
        if level in ("ERROR", "SUCCESS"):
            fmt.setFontWeight(QFont.Weight.DemiBold)
        cur = self.console.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(f"[{stamp}] {msg}\n", fmt)
        self.console.setTextCursor(cur)
        self.console.ensureCursorVisible()

    def _render_log(self) -> None:
        self.console.clear()
        for stamp, level, msg in self.log_lines[-4000:]:
            if self._visible(level):
                self._append(stamp, level, msg)

    def _clear_log(self) -> None:
        self.log_lines.clear()
        self.console.clear()

    def _save_log(self) -> None:
        f, _ = QFileDialog.getSaveFileName(self, "Save log", "fibercallout_log.txt", "Text (*.txt)")
        if f:
            Path(f).write_text("\n".join(f"[{s}] {l:<7} {m}" for s, l, m in self.log_lines), encoding="utf-8")

    def _open(self, path: Optional[str]) -> None:
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_output_folder(self) -> None:
        p = next(iter(self.outputs.values()), "") if self.outputs else ""
        folder = str(Path(p).parent) if p else (self.ed_output.text() or "")
        if folder and Path(folder).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def pick_drawing(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Design drawing", self.settings.value("lastDir", ""),
                                           "CAD drawings (*.dwg *.dxf);;All files (*)")
        if f:
            self.settings.setValue("lastDir", str(Path(f).parent))
            self.ed_drawing.setText(f)
            self._drawing_changed()

    def pick_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.ed_output.text())
        if d:
            self.ed_output.setText(d)

    def pick_oda(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "ODA File Converter executable", "", "Executable (*.exe);;All files (*)")
        if f:
            self.ed_oda.setText(f)

    def _locate_oda(self) -> None:
        oda = find_oda_converter(self.ed_oda.text().strip())
        if oda:
            self.ed_oda.setText(oda)
            QMessageBox.information(self, APP_NAME, f"ODA File Converter found:\n{oda}")
        else:
            QMessageBox.information(self, APP_NAME, "ODA File Converter was not found. DWG files are still supported by "
                                    "the built-in reader; output is then a callouts DXF + AutoCAD script.\n\n"
                                    "Free download: https://www.opendesign.com/guestfiles/oda_file_converter")

    def _drawing_changed(self) -> None:
        p = self.ed_drawing.text().strip()
        if not p:
            self.lbl_drawing.setText("")
            return
        path = Path(p)
        if not path.exists():
            self.lbl_drawing.setText("File not found")
            return
        info = f"{path.suffix.upper().lstrip('.')} - {path.stat().st_size / 1e6:.1f} MB"
        if path.suffix.lower() == ".dwg":
            try:
                ver = path.open("rb").read(6).decode("ascii", "replace")
                from .dwg_native import KNOWN, SUPPORTED
                info += f" - format {ver} ({SUPPORTED.get(ver) or KNOWN.get(ver, 'unknown')})"
            except OSError:
                pass
        self.lbl_drawing.setText(info)
        if not self.ed_output.text().strip():
            self.ed_output.setText(str(path.parent / "callout_output"))
        if self.scan is not None:
            self._reset_cad()
            self._log("Drawing changed - CAD mapping reset to auto-detect (run Scan to review)", "INFO")

    def _addresses_changed(self) -> None:
        for cb in getattr(self, "col_boxes", {}).values():
            cb.setCurrentIndex(0)

    def _reset_cad(self) -> None:
        for cb in (self.cb_cl_layer, self.cb_cl_block, self.cb_cl_tag, self.cb_hh_layer, self.cb_term_layer):
            cb.setCurrentText(AUTO)
        for lst in (self.lst_hh, self.lst_cables):
            for i in range(lst.count()):
                lst.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.sp_snap.setValue(0.0)

    def _reset_style(self) -> None:
        self._apply_spec(CalloutSpec())

    def _update_preview(self) -> None:
        self.preview.prefix = self.style_w["cable_prefix"].text() or "BFO"
        self.preview.update()

    def _refresh_closure_blocks(self) -> None:
        if not self.scan:
            return
        layer = self.cb_cl_layer.currentText()
        cur_b, cur_t = self.cb_cl_block.currentText(), self.cb_cl_tag.currentText()
        self.cb_cl_block.blockSignals(True)
        self.cb_cl_block.clear()
        self.cb_cl_block.addItem(AUTO)
        self.cb_cl_block.addItems([b for l, b, _n in self.scan.insert_pairs if l == layer])
        self.cb_cl_block.setCurrentText(cur_b)
        self.cb_cl_block.blockSignals(False)
        tags = sorted({t for key, ts in self.scan.insert_tags.items() if key.split("|")[0] == layer for t in ts})
        self.cb_cl_tag.clear()
        self.cb_cl_tag.addItem(AUTO)
        self.cb_cl_tag.addItems(tags)
        self.cb_cl_tag.setCurrentText(cur_t)

    def _refresh_hh_blocks(self, checked: Optional[List[str]]) -> None:
        if not self.scan:
            return
        layer = self.cb_hh_layer.currentText()
        keep = set(checked) if checked is not None else {self.lst_hh.item(i).text() for i in range(self.lst_hh.count())
                                                          if self.lst_hh.item(i).checkState() == Qt.CheckState.Checked}
        self.lst_hh.clear()
        for l, b, n in self.scan.insert_pairs:
            if l == layer:
                it = QListWidgetItem(b)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if b in keep else Qt.CheckState.Unchecked)
                it.setToolTip(f"{n} instance(s)")
                self.lst_hh.addItem(it)

    # ----------------------------------------------------------------- config
    @staticmethod
    def _auto(text: str) -> str:
        t = text.strip()
        return "" if t in ("", AUTO) else t

    def collect_config(self) -> RunConfig:
        cfg = RunConfig()
        cfg.drawing_path = self.ed_drawing.text().strip()
        cfg.output_dir = self.ed_output.text().strip()
        cfg.oda_path = self.ed_oda.text().strip()
        cfg.splice_paths = self.fl_splice.paths()
        cfg.address_paths = self.fl_addr.paths()
        cfg.existing_mode = ("replace", "skip", "append")[self.cb_existing.currentIndex()]
        cfg.dwg_reader = ("auto", "builtin", "oda")[self.cb_reader.currentIndex()]
        cfg.export_dwg = self.chk_dwg.isChecked()
        cfg.dwg_version = self.cb_dwgver.currentText()
        cfg.units = self.cb_units.currentText()
        cfg.ports_per_pon = self.sp_ports.value()
        for k, cb in self.col_boxes.items():
            setattr(cfg.columns, k, self._auto(cb.currentText()) or None)
        cfg.cad = CadMap(
            closure_layer=self._auto(self.cb_cl_layer.currentText()),
            closure_block=self._auto(self.cb_cl_block.currentText()),
            closure_name_tag=self._auto(self.cb_cl_tag.currentText()),
            handhole_layer=self._auto(self.cb_hh_layer.currentText()),
            handhole_blocks=[self.lst_hh.item(i).text() for i in range(self.lst_hh.count())
                             if self.lst_hh.item(i).checkState() == Qt.CheckState.Checked],
            terminal_layer=self._auto(self.cb_term_layer.currentText()),
            cable_layers=[self.lst_cables.item(i).text() for i in range(self.lst_cables.count())
                          if self.lst_cables.item(i).checkState() == Qt.CheckState.Checked],
            snap_tolerance=self.sp_snap.value())
        sp = CalloutSpec()
        for name, w in self.style_w.items():
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                setattr(sp, name, w.value())
            elif isinstance(w, QLineEdit):
                setattr(sp, name, w.text().strip() or getattr(CalloutSpec(), name))
            elif isinstance(w, QComboBox):
                setattr(sp, name, w.currentText())
            elif isinstance(w, QCheckBox):
                setattr(sp, name, w.isChecked())
        cfg.spec = sp
        return cfg

    def _apply_spec(self, sp: CalloutSpec) -> None:
        for name, w in self.style_w.items():
            v = getattr(sp, name)
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                w.setValue(v)
            elif isinstance(w, QLineEdit):
                w.setText(str(v))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
        self._update_preview()

    def apply_config(self, cfg: RunConfig) -> None:
        self.ed_drawing.setText(cfg.drawing_path)
        self.ed_output.setText(cfg.output_dir)
        self.ed_oda.setText(cfg.oda_path)
        self.fl_splice.set_paths(cfg.splice_paths)
        self.fl_addr.set_paths(cfg.address_paths)
        self.cb_existing.setCurrentIndex(("replace", "skip", "append").index(cfg.existing_mode)
                                         if cfg.existing_mode in ("replace", "skip", "append") else 0)
        self.cb_reader.setCurrentIndex(("auto", "builtin", "oda").index(cfg.dwg_reader) if cfg.dwg_reader in ("auto", "builtin", "oda") else 0)
        self.chk_dwg.setChecked(cfg.export_dwg)
        self.cb_dwgver.setCurrentText(cfg.dwg_version)
        self.cb_units.setCurrentText(cfg.units)
        self.sp_ports.setValue(cfg.ports_per_pon)
        for k, cb in self.col_boxes.items():
            cb.setCurrentText(getattr(cfg.columns, k) or AUTO)
        c = cfg.cad
        self.cb_cl_layer.setCurrentText(c.closure_layer or AUTO)
        self.cb_cl_block.setCurrentText(c.closure_block or AUTO)
        self.cb_cl_tag.setCurrentText(c.closure_name_tag or AUTO)
        self.cb_hh_layer.setCurrentText(c.handhole_layer or AUTO)
        self.cb_term_layer.setCurrentText(c.terminal_layer or AUTO)
        for lst, vals in ((self.lst_hh, c.handhole_blocks), (self.lst_cables, c.cable_layers)):
            lst.clear()
            for v in vals:
                it = QListWidgetItem(v)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked)
                lst.addItem(it)
        self.sp_snap.setValue(c.snap_tolerance)
        self._apply_spec(cfg.spec)
        self._drawing_changed()

    def apply_scan(self, res: ScanResult) -> None:
        self.scan = res
        for k, cb in self.col_boxes.items():
            cb.clear()
            cb.addItem(AUTO)
            cb.addItems(res.headers)
            cb.setCurrentText(getattr(res.columns, k) or AUTO)
        if res.cad:
            for cb in (self.cb_cl_layer, self.cb_hh_layer, self.cb_term_layer):
                cb.blockSignals(True)
                cb.clear()
                cb.addItem(AUTO)
                cb.addItems(res.layers)
                cb.blockSignals(False)
            self.cb_cl_layer.setCurrentText(res.cad.closure_layer or AUTO)
            self._refresh_closure_blocks()
            self.cb_cl_block.setCurrentText(res.cad.closure_block or AUTO)
            self.cb_cl_tag.setCurrentText(res.cad.closure_name_tag or AUTO)
            self.cb_hh_layer.setCurrentText(res.cad.handhole_layer or AUTO)
            self._refresh_hh_blocks(res.cad.handhole_blocks)
            self.cb_term_layer.setCurrentText(res.cad.terminal_layer or AUTO)
            self.lst_cables.clear()
            for l, n in res.line_layers:
                it = QListWidgetItem(l)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if l in res.cad.cable_layers else Qt.CheckState.Unchecked)
                it.setToolTip(f"{n} linear entities")
                self.lst_cables.addItem(it)
            self.sp_snap.setValue(res.cad.snap_tolerance)
            self.lbl_drawing.setText(res.drawing_info)

    def show_results(self, res: RunResult) -> None:
        s = res.summary
        self.kpi_t.set(s.get("Fiber-number callouts", 0))
        self.kpi_c.set(s.get("BFO callouts", 0))
        total = s.get("Fiber-number callouts", 0) + s.get("BFO callouts", 0)
        self.kpi_clean.set(f"{s.get('Placement - clean', 0)}/{total}")
        self.kpi_e.set(s.get("Errors", 0))
        self.kpi_w.set(s.get("Warnings", 0))
        mode = "Generated" if res.outputs else "Validation (dry run)"
        self.lbl_result.setText(f"{mode} - {s.get('OLMs', '')} - {s.get('Formula', '')} - reader: {s.get('Drawing reader', '')}")
        rows = [dict(ID=p.uid, Kind="Fiber number" if p.kind == "TERMINAL" else "BFO", OLM=p.olm,
                     Text=p.text.replace("\\P", " / "), Closure=p.closure, Anchor=p.anchor,
                     Numbers=fmt_numbers(p.numbers, "exact", 0), Status=p.status, Existing=p.existing_match,
                     Notes=p.notes, Calculation=p.calculation) for p in res.plans]
        self.tbl_callouts.fill(rows, lambda r: "#FDECEA" if r["Status"] == "FAILED" else
                               ("#FFF6E0" if "PLACEMENT REVIEW" in (r["Notes"] or "") else None))
        issues = [dict(Severity=i.severity, Category=i.category, Object=i.obj, Message=i.message) for i in res.issues.items]
        self.tbl_issues.fill(issues, lambda r: {"ERROR": "#FDECEA", "WARNING": "#FFF6E0"}.get(r["Severity"]))
        self.tbl_network.fill(res.network)
        self.tbl_existing.fill(res.existing_rows, lambda r: "#E8F5E9" if str(r.get("Result", "")).startswith("MATCH") else None)
        self.outputs = dict(res.outputs)
        for b in (self.btn_open_folder, self.btn_open_qa, self.btn_open_dwg):
            b.setEnabled(bool(self.outputs))
        self.nav.setCurrentRow(4)

    # ----------------------------------------------------------------- projects / settings
    def new_project(self) -> None:
        self.apply_config(RunConfig())
        self.scan = None
        self._log("New project", "INFO")

    def open_project(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Open project", "", "FiberCallout project (*.fcsproj.json *.json)")
        if f:
            try:
                self.apply_config(RunConfig.from_dict(json.loads(Path(f).read_text(encoding="utf-8"))))
                self._log(f"Project loaded: {f}", "INFO")
            except (OSError, ValueError, TypeError) as exc:
                QMessageBox.critical(self, APP_NAME, f"Cannot open project:\n{exc}")

    def save_project(self) -> None:
        f, _ = QFileDialog.getSaveFileName(self, "Save project", "region.fcsproj.json", "FiberCallout project (*.fcsproj.json)")
        if f:
            Path(f).write_text(json.dumps(self.collect_config().to_dict(), indent=2), encoding="utf-8")
            self._log(f"Project saved: {f}", "INFO")

    def _restore(self) -> None:
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        raw = self.settings.value("lastConfig", "")
        if raw:
            try:
                cfg = RunConfig.from_dict(json.loads(raw))
                cfg.cad = CadMap()
                cfg.columns = ColumnMap()
                self.apply_config(cfg)
            except (ValueError, TypeError):
                pass
        self._update_preview()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self.thread is not None:
            self.cancel.set()
            self.thread.quit()
            self.thread.wait(5000)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("lastConfig", json.dumps(self.collect_config().to_dict()))
        event.accept()

    # ----------------------------------------------------------------- jobs
    def start(self, task: str) -> None:
        if self.thread is not None:
            return
        cfg = self.collect_config()
        if task in ("validate", "generate"):
            missing = [n for n, ok in (("design drawing", bool(cfg.drawing_path)), ("address list(s)", bool(cfg.address_paths)))
                       if not ok]
            if missing:
                QMessageBox.warning(self, APP_NAME, "Please add the " + " and ".join(missing) + " on the Project page.")
                self.nav.setCurrentRow(0)
                return
            if not cfg.splice_paths:
                if QMessageBox.question(self, APP_NAME, "No splice reports added - only fiber-number callouts can be "
                                        "produced (no BFO cable callouts). Continue?") != QMessageBox.StandardButton.Yes:
                    return
        if task == "scan" and not (cfg.drawing_path or cfg.address_paths or cfg.splice_paths):
            QMessageBox.warning(self, APP_NAME, "Add a drawing, splice reports or address lists first.")
            return
        if task == "generate" and not cfg.output_dir:
            cfg.output_dir = str(Path(cfg.drawing_path).parent / "callout_output")
            self.ed_output.setText(cfg.output_dir)
        self.cancel.clear()
        self.progress.setValue(0)
        self._log(f"--- {task.upper()} ---", "INFO")
        self._busy(True)
        self.thread = QThread(self)
        self.worker = Worker(task, cfg, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self._busy(False)

    def _busy(self, busy: bool) -> None:
        for b in (self.btn_scan, self.btn_validate, self.btn_generate):
            b.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.nav.setEnabled(not busy)
        self.stack.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()

    def cancel_job(self) -> None:
        self.cancel.set()
        self._log("Cancelling...", "WARNING")

    def _progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(pct)
        if msg:
            self.status.setText(msg)

    def _done(self, task: str, res: Any) -> None:
        if task == "scan" and isinstance(res, ScanResult):
            self.apply_scan(res)
            self.status.setText("Scan complete - mapping filled in; review Columns and CAD Mapping")
            self._log("Scan complete - review the Columns and CAD Mapping pages, then Validate or Generate.", "SUCCESS")
            self.nav.setCurrentRow(2 if res.cad else 1)
        elif task in ("validate", "generate") and isinstance(res, RunResult):
            self.show_results(res)
            s = res.summary
            msg = (f"{s.get('Fiber-number callouts', 0)} fiber-number + {s.get('BFO callouts', 0)} BFO callouts; "
                   f"{s.get('Errors', 0)} error(s), {s.get('Warnings', 0)} warning(s)")
            self.status.setText(("Generated: " if task == "generate" else "Validated: ") + msg)
            if task == "generate":
                files = "\n".join(f"  {k}: {v}" for k, v in res.outputs.items())
                extra = ""
                if "AutoCAD script" in res.outputs:
                    extra = ("\n\nTo apply: open the DWG in AutoCAD, type SCRIPT and pick the .scr file. Existing fiber "
                             "callouts are replaced and the new ones inserted at the same coordinates.")
                QMessageBox.information(self, APP_NAME, f"Callouts generated.\n\n{msg}\n\n{files}{extra}")
        elif task == "selftest":
            ok, _text = res
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, APP_NAME, "Self-test PASSED - all checks succeeded." if ok else "Self-test FAILED - see the log.")

    def _failed(self, task: str, msg: str) -> None:
        self._log(f"{task} failed: {msg}", "ERROR")
        self.status.setText(f"{task} failed")
        if msg != "Cancelled by user":
            QMessageBox.critical(self, APP_NAME, f"{task.capitalize()} failed:\n\n{msg}")

    # ----------------------------------------------------------------- help
    def show_guide(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(f"{APP_NAME} - Quick guide")
        d.resize(760, 640)
        lay = QVBoxLayout(d)
        tb = QTextBrowser()
        tb.setHtml(QUICK_GUIDE)
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.exec()

    def show_about(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(f"About {APP_NAME}")
        lay = QHBoxLayout(d)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(128))
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        txt = QLabel(f"<h2>{APP_NAME}</h2><p>Version {APP_VERSION}</p>"
                     "<p>Automated DES_FIBER_SPL fiber-number callouts for FTTx OSP designs.<br>"
                     "Reads DWG/DXF drawings, splice reports and address lists; writes MULTILEADER callouts "
                     "identical to the reference drafting standard plus a QA/QC workbook.</p>"
                     f"<p>Python {sys.version.split()[0]} &middot; PyQt6 &middot; ezdxf &middot; openpyxl</p>")
        txt.setWordWrap(True)
        txt.setMinimumWidth(380)
        lay.addWidget(txt)
        d.exec()


def run_gui(on_ready: Optional[Callable[[Any, Any], None]] = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FTTx.FiberCalloutStudio")
        except Exception:  # noqa: BLE001 - taskbar grouping only
            pass
    win = MainWindow()
    win.show()
    if on_ready is not None:
        QTimer.singleShot(0, lambda: on_ready(win, app))
    return app.exec()


__all__ = ["run_gui", "MainWindow"]
