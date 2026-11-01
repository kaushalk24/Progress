# -*- coding: utf-8 -*-
"""FiberCallout Studio - PyQt6 desktop interface.

Two steps only: *Inputs* (drawing + data + output folder) and *Results*. Everything about the network - closures,
handholes, cables, address-list columns, splitter size, drawing units - is detected from the files on every run.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import threading
import traceback
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt6.QtCore import QObject, QPointF, QSettings, QSortFilterProxyModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QKeySequence, QPainter, QPen, QPolygonF,
                         QStandardItem, QStandardItemModel, QTextCharFormat, QTextCursor)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                             QDockWidget, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                             QScrollArea, QSizePolicy, QStackedWidget, QStyleFactory, QTableView, QTabWidget,
                             QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from . import APP_NAME, APP_ORG, APP_VERSION
from .branding import app_icon, logo_pixmap
from .engine import CalloutEngine, CalloutSpec, Cancelled, Reporter, RunConfig, RunResult, fmt_numbers

DRAWING_EXTS = (".dwg", ".dxf")
DATA_EXTS = (".xlsx", ".xlsm", ".xls", ".csv")
LEVEL_COLORS = {"ERROR": "#C62828", "WARNING": "#9A5B00", "SUCCESS": "#1B7F3B", "DEBUG": "#7A8594", "INFO": "#1F2933"}
NAVY = "#0B2545"
PRIMARY = "#0B3954"
ACCENT = "#13808C"
UI_FONT = "Segoe UI" if os.name == "nt" else "DejaVu Sans"
MONO_FONT = "Consolas" if os.name == "nt" else "DejaVu Sans Mono"

QSS = f"""
QMainWindow, QWidget#page {{ background: #F4F6F9; }}
QWidget {{ font-size: 10pt; color: #1F2933; }}
QFrame#header {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {NAVY}, stop:1 {ACCENT}); }}
QLabel#appTitle {{ color: white; font-size: 16pt; font-weight: 600; }}
QLabel#appSub {{ color: #CFE8EC; font-size: 9.5pt; }}
QLabel#appVer {{ color: #CFE8EC; font-size: 9pt; }}
QFrame#stepBar {{ background: white; border-bottom: 1px solid #DDE3EA; }}
QPushButton#step {{ background: transparent; border: none; border-bottom: 3px solid transparent; border-radius: 0;
    padding: 12px 18px 9px 18px; color: #66788A; font-size: 10.5pt; font-weight: 600; min-width: 112px; }}
QPushButton#step:hover {{ color: {PRIMARY}; background: #F4F8FA; }}
QPushButton#step:checked {{ color: {PRIMARY}; border-bottom-color: {ACCENT}; font-weight: 600; }}
QPushButton#step:disabled {{ color: #B4BEC8; }}
QFrame#card {{ background: white; border: 1px solid #DDE3EA; border-radius: 10px; }}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 600; color: {PRIMARY}; }}
QLabel#cardNum {{ background: {ACCENT}; color: white; border-radius: 11px; font-weight: 600; font-size: 9pt; }}
QLabel#hint {{ color: #66788A; font-size: 9pt; }}
QLabel#ok {{ color: #1B7F3B; font-size: 9pt; }}
QLabel#bad {{ color: #C62828; font-size: 9pt; }}
QLabel#specLine {{ color: #3E4C59; font-size: 9pt; }}
QPushButton {{ background: white; border: 1px solid #C5CED8; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; background: #F2FAFB; }}
QPushButton:disabled {{ color: #A0AAB4; background: #F4F6F9; border-color: #DDE3EA; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600; padding: 9px 24px; }}
QPushButton#primary:hover {{ background: #0F6E78; }}
QPushButton#primary:disabled {{ background: #A9CDD1; color: #EEF6F7; }}
QPushButton#secondary {{ background: white; color: {PRIMARY}; border: 1px solid {PRIMARY}; font-weight: 600;
    padding: 8px 20px; }}
QPushButton#secondary:hover {{ background: #EEF4F8; }}
QPushButton#secondary:disabled {{ color: #A0AAB4; border-color: #C5CED8; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 4px 6px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#danger {{ color: #C62828; border-color: #E3B7B7; }}
QLineEdit, QComboBox {{ background: white; border: 1px solid #C5CED8; border-radius: 6px; padding: 5px 8px;
    min-height: 22px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QListWidget#files {{ background: #FAFBFC; border: 1px dashed #AEBBC8; border-radius: 8px; padding: 4px; }}
QListWidget#files::item {{ padding: 4px 2px; }}
QProgressBar {{ border: none; background: #E3E8EE; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QFrame#actionBar {{ background: white; border-top: 1px solid #DDE3EA; }}
QFrame#kpi {{ background: white; border: 1px solid #DDE3EA; border-radius: 10px; }}
QLabel#kpiValue {{ font-size: 19pt; font-weight: 600; }}
QLabel#kpiTitle {{ color: #66788A; font-size: 9pt; }}
QFrame#bannerOk {{ background: #E8F5EC; border: 1px solid #B9DFC5; border-radius: 10px; }}
QFrame#bannerInfo {{ background: #E8F3F5; border: 1px solid #B5D8DD; border-radius: 10px; }}
QFrame#bannerWarn {{ background: #FFF5E5; border: 1px solid #F0D29E; border-radius: 10px; }}
QLabel#bannerTitle {{ font-size: 12pt; font-weight: 600; color: {PRIMARY}; }}
QLabel#bannerDetail {{ color: #66788A; font-size: 9pt; }}
QTableView {{ background: white; border: 1px solid #DDE3EA; gridline-color: #EEF1F4;
    selection-background-color: #D7ECEF; selection-color: #1F2933; alternate-background-color: #FAFBFC; }}
QHeaderView::section {{ background: #EEF2F6; border: none; border-right: 1px solid #DDE3EA; padding: 5px;
    font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid #DDE3EA; background: white; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ padding: 7px 16px; background: #E9EDF2; border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px; color: #3E4C59; }}
QTabBar::tab:selected {{ background: white; color: {PRIMARY}; font-weight: 600; }}
QDockWidget::title {{ background: #E9EDF2; padding: 5px; }}
QScrollArea {{ background: transparent; }}
"""

QUICK_GUIDE = f"""
<h2>{APP_NAME}</h2>
<p>Generates the magenta <b>DES_FIBER_SPL</b> multileader callouts of an FTTx design from its splice reports and
address lists, exactly as drafted in the reference design. It works for any region: closures, handholes, cables,
address-list columns, splitter size and drawing units are detected from the files on every run.</p>
<h3>1 &nbsp;Inputs</h3>
<ol>
<li><b>Design drawing</b> - the region's .dwg (AutoCAD 2010-2025) or .dxf.</li>
<li><b>Splice reports &amp; address lists</b> - add everything for the region in one list: files, folders or .zip
archives. Splice reports and address lists are told apart automatically; duplicates are ignored.</li>
<li><b>Output folder</b> - defaults to <tt>callout_output</tt> next to the drawing.</li>
</ol>
<p>Drag &amp; drop works anywhere in the window: a drawing goes to the drawing field, everything else to the list.</p>
<h3>2 &nbsp;Validate or Generate</h3>
<ul>
<li><b>Validate</b> analyses the network and lists every problem (missing closures, address-list / splice-report
mismatches, orphan addresses, missing cable geometry, crowded placements). Nothing is written.</li>
<li><b>Generate Callouts</b> writes <tt>*_FIBER_CALLOUTS_*.dxf</tt> (the callouts only, at the drawing's own
coordinates) and the QA/QC workbook <tt>*_FIBER_CALLOUTS_QA_*.xlsx</tt>.</li>
</ul>
<h3>3 &nbsp;Paste into the design</h3>
<ol>
<li>Open the callouts DXF in AutoCAD, press <b>Ctrl+A</b> then <b>Ctrl+C</b>.</li>
<li>Switch to the design drawing and type <b>PASTEORIG</b> - the callouts land at their original coordinates.</li>
<li>Delete the old fiber callouts first if the design already has some (the Results page compares them).</li>
</ol>
<h3>Rules</h3>
<ul>
<li>Fiber number <b>N = (PON - 1) x splitter size + PON PORT</b>, per OLM.</li>
<li><b>Fiber-number callout</b>: one per terminal + drop closure (per contiguous run), e.g. <tt>69</tt> or
<tt>218-219</tt>; arrow on the handhole hosting the drop closure.</li>
<li><b>BFO callout</b>: one per live cable segment leaving a closure that has a splice report, e.g.
<tt>BFO 72 / 70-115</tt> = cable fiber count / lowest-highest fiber number carried; arrow on the cable.</li>
</ul>
"""


# =============================================================================
# Worker
# =============================================================================
class Worker(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, task: str, cfg: RunConfig, cancel: threading.Event, previous: Optional[RunResult] = None) -> None:
        super().__init__()
        self.task, self.cfg, self.cancel, self.previous = task, cfg, cancel, previous

    def run(self) -> None:
        rep = Reporter(lambda m, l: self.log.emit(m, l), lambda p, m: self.progress.emit(p, m), self.cancel)
        try:
            if self.task == "selftest":
                from .selftest import run_selftest
                ok, text = run_selftest(verbose=False, log=lambda m: self.log.emit(m, "INFO"))
                self.finished.emit(self.task, (ok, text))
                return
            eng = CalloutEngine(self.cfg, rep)
            res = eng.generate(self.previous) if self.task == "generate" else eng.analyze()
            self.finished.emit(self.task, res)
        except Cancelled:
            self.failed.emit(self.task, "Cancelled by user")
        except Exception as exc:  # noqa: BLE001 - every failure is reported in the GUI
            self.log.emit(traceback.format_exc(), "DEBUG")
            self.failed.emit(self.task, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Widgets
# =============================================================================
def card(title: str, number: str = "", hint: str = "") -> tuple:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(8)
    row = QHBoxLayout()
    row.setSpacing(10)
    if number:
        n = QLabel(number)
        n.setObjectName("cardNum")
        n.setFixedSize(22, 22)
        n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(n)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    row.addWidget(t)
    row.addStretch(1)
    lay.addLayout(row)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return f, lay


def accepts_urls(e: Any) -> bool:
    return bool(e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()))


def dropped_paths(e: Any) -> List[str]:
    return [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]


class PathEdit(QLineEdit):
    dropped = pyqtSignal(str)

    def __init__(self, placeholder: str = "") -> None:
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)
        self.setClearButtonEnabled(True)

    def dragEnterEvent(self, e: Any) -> None:  # noqa: N802
        if accepts_urls(e):
            e.acceptProposedAction()

    def dropEvent(self, e: Any) -> None:  # noqa: N802
        paths = dropped_paths(e)
        if paths:
            self.setText(paths[0])
            self.dropped.emit(paths[0])


def count_sheets(path: str) -> int:
    """Number of spreadsheet files in a file / folder / zip (what the engine will look at)."""
    p = Path(path)
    try:
        if p.is_dir():
            return sum(1 for f in p.rglob("*") if f.suffix.lower() in DATA_EXTS and not f.name.startswith("~$"))
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                return sum(1 for n in z.namelist() if Path(n).suffix.lower() in DATA_EXTS
                           and not Path(n).name.startswith("~$"))
        return 1 if p.suffix.lower() in DATA_EXTS + (".txt",) else 0
    except (OSError, zipfile.BadZipFile):
        return 0


class DataList(QWidget):
    """One list for every splice report and address list of the region (files, folders or .zip)."""

    changed = pyqtSignal()
    drawing_found = pyqtSignal(str)
    rejected = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMinimumHeight(150)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter  # type: ignore[assignment]
        self.list.dragMoveEvent = self._drag_enter  # type: ignore[assignment]
        self.list.dropEvent = self._drop  # type: ignore[assignment]
        self.empty = QLabel("Drop splice reports and address lists here\nfiles, folders or .zip archives")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("hint")
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        grid = QGridLayout()
        grid.addWidget(self.list, 0, 0)
        grid.addWidget(self.empty, 0, 0)
        lay.addLayout(grid)
        row = QHBoxLayout()
        self.btn_files = QPushButton("Add files...")
        self.btn_folder = QPushButton("Add folder...")
        self.btn_remove = QPushButton("Remove")
        self.btn_files.clicked.connect(self.add_files)
        self.btn_folder.clicked.connect(self.add_folder)
        self.btn_remove.clicked.connect(self.remove)
        for b in (self.btn_files, self.btn_folder, self.btn_remove):
            row.addWidget(b)
        row.addStretch(1)
        self.summary = QLabel("")
        self.summary.setObjectName("hint")
        row.addWidget(self.summary)
        lay.addLayout(row)
        self.list.itemSelectionChanged.connect(self._update)
        self.start_dir: Callable[[], str] = lambda: ""
        self._update()

    def _drag_enter(self, e: Any) -> None:
        if accepts_urls(e):
            e.acceptProposedAction()

    def _drop(self, e: Any) -> None:
        self.add_many(dropped_paths(e))
        e.acceptProposedAction()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add splice reports and address lists", self.start_dir(),
            "Spreadsheets and archives (*.xlsx *.xlsm *.xls *.csv *.zip);;All files (*)")
        self.add_many(files)

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add a folder of splice reports / address lists", self.start_dir())
        if d:
            self.add_many([d])

    def add_many(self, paths: Sequence[str]) -> None:
        skipped = []
        for p in paths:
            pp = Path(p)
            if pp.suffix.lower() in DRAWING_EXTS:
                self.drawing_found.emit(p)
            elif pp.is_dir() or pp.suffix.lower() in DATA_EXTS + (".zip", ".txt"):
                self.add(p, update=False)
            else:
                skipped.append(pp.name)
        self._update()
        if skipped:
            self.rejected.emit(skipped)

    def add(self, path: str, update: bool = True) -> None:
        if not path:
            return
        norm = os.path.normcase(os.path.abspath(path))
        if any(os.path.normcase(os.path.abspath(x)) == norm for x in self.paths()):
            return
        pp = Path(path)
        n = count_sheets(path)
        if pp.is_dir():
            kind = f"folder - {n} spreadsheet(s)"
        elif pp.suffix.lower() == ".zip":
            kind = f"zip - {n} spreadsheet(s)"
        else:
            kind = pp.suffix.lower().lstrip(".")
        it = QListWidgetItem(f"{pp.name}     ({kind})")
        it.setToolTip(path)
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setData(Qt.ItemDataRole.UserRole + 1, n)
        self.list.addItem(it)
        if update:
            self._update()

    def remove(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._update()

    def clear(self) -> None:
        self.list.clear()
        self._update()

    def paths(self) -> List[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def sheet_count(self) -> int:
        return sum(int(self.list.item(i).data(Qt.ItemDataRole.UserRole + 1) or 0) for i in range(self.list.count()))

    def _update(self) -> None:
        n = self.list.count()
        self.empty.setVisible(n == 0)
        self.btn_remove.setEnabled(bool(self.list.selectedItems()))
        self.summary.setText(f"{self.sheet_count()} spreadsheet(s) in {n} item(s)" if n else "")
        self.changed.emit()


class CalloutPreview(QWidget):
    """How the callouts look in AutoCAD model space."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(300, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(200)

    def paintEvent(self, _e: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#212830"))
        p.drawRoundedRect(0, 0, w, h, 8, 8)
        mag, green, grey = QColor("#FF00FF"), QColor("#3DBE3D"), QColor("#C9CED4")
        p.setPen(QPen(grey, 1))
        p.drawLine(0, int(h * 0.30), w, int(h * 0.30))
        p.drawLine(0, int(h * 0.84), w, int(h * 0.84))
        cy = h * 0.57
        p.setPen(QPen(green, 3))
        p.drawLine(0, int(cy), w, int(cy))
        cx = w * 0.55
        p.setBrush(green)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(cx - 20, cy - 12), QPointF(cx, cy), QPointF(cx - 20, cy + 12)]))
        p.drawPolygon(QPolygonF([QPointF(cx + 20, cy - 12), QPointF(cx, cy), QPointF(cx + 20, cy + 12)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(grey, 1.5))
        hx, hy = w * 0.82, h * 0.71
        p.drawRect(int(hx - 11), int(hy - 11), 22, 22)
        font = QFont(MONO_FONT)
        font.setPixelSize(14)
        p.setFont(font)
        fm = p.fontMetrics()

        def callout(land: QPointF, lines: List[str], tip: QPointF) -> None:
            # MLEADER: the landing underlines the first text line on the side facing the arrow
            tw = max(fm.horizontalAdvance(x) for x in lines)
            text_left = tip.x() >= land.x()
            x0 = land.x() - 3 - tw if text_left else land.x() + 3
            p.setPen(mag)
            for i, t in enumerate(lines):
                p.drawText(QPointF(x0, land.y() - 4 + i * 18), t)
            p.setPen(QPen(mag, 1.2))
            p.drawLine(QPointF(x0, land.y()), QPointF(x0 + tw, land.y()))
            p.drawLine(QPointF(x0 + tw if text_left else x0, land.y()), land)
            p.drawLine(land, tip)
            dx, dy = tip.x() - land.x(), tip.y() - land.y()
            ln = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            ux, uy = dx / ln, dy / ln
            b = QPointF(tip.x() - ux * 10, tip.y() - uy * 10)
            p.setBrush(mag)
            p.drawPolygon(QPolygonF([tip, QPointF(b.x() - uy * 3.2, b.y() + ux * 3.2),
                                     QPointF(b.x() + uy * 3.2, b.y() - ux * 3.2)]))
            p.setBrush(Qt.BrushStyle.NoBrush)

        callout(QPointF(w * 0.30, h * 0.15), ["BFO 72", "70-115"], QPointF(cx - 58, cy))
        callout(QPointF(w * 0.47, h * 0.74), ["BFO 72", "2-69"], QPointF(cx + 52, cy))
        callout(QPointF(w * 0.70, h * 0.93), ["69"], QPointF(hx - 11, hy + 11))
        p.end()


class Kpi(QFrame):
    def __init__(self, title: str, color: str) -> None:
        super().__init__()
        self.setObjectName("kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        bar = QFrame()
        bar.setFixedHeight(3)
        bar.setStyleSheet(f"background:{color}; border-radius:1px;")
        self.value = QLabel("-")
        self.value.setObjectName("kpiValue")
        self.value.setStyleSheet(f"color:{color};")
        t = QLabel(title)
        t.setObjectName("kpiTitle")
        lay.addWidget(bar)
        lay.addSpacing(4)
        lay.addWidget(self.value)
        lay.addWidget(t)

    def set(self, v: Any) -> None:
        self.value.setText(str(v))


class Table(QWidget):
    """Searchable table with an optional quick filter."""

    def __init__(self, placeholder: str, filters: Optional[Dict[str, Callable[[Dict[str, Any]], bool]]] = None) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        top.addWidget(self.search, 1)
        self.filters = filters or {}
        self.combo: Optional[QComboBox] = None
        if self.filters:
            self.combo = QComboBox()
            self.combo.addItems(list(self.filters))
            self.combo.currentIndexChanged.connect(lambda _i: self._refill())
            top.addWidget(self.combo)
        self.count = QLabel("")
        self.count.setObjectName("hint")
        top.addWidget(self.count)
        lay.addLayout(top)
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
        self.view.setWordWrap(False)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.search.textChanged.connect(self._search)
        lay.addWidget(self.view)
        self.rows: List[Dict[str, Any]] = []
        self.colors: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None

    def _search(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self._count()

    def _count(self) -> None:
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count.setText(f"{shown} of {len(self.rows)}" if shown != len(self.rows) or total != len(self.rows)
                           else f"{len(self.rows)} row(s)")

    def set_filter(self, name: str) -> None:
        if self.combo is not None:
            self.combo.setCurrentText(name)

    def fill(self, rows: List[Dict[str, Any]], colors: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None) -> None:
        self.rows, self.colors = rows, colors
        self._refill()

    def _refill(self) -> None:
        rows = self.rows
        if self.combo is not None:
            pred = self.filters.get(self.combo.currentText())
            if pred is not None:
                rows = [r for r in rows if pred(r)]
        self.view.setSortingEnabled(False)
        self.model.clear()
        headers: List[str] = []
        for r in self.rows:
            for k in r:
                if k not in headers:
                    headers.append(k)
        self.model.setHorizontalHeaderLabels(headers)
        for r in rows:
            col = self.colors(r) if self.colors else None
            items = []
            for h in headers:
                v = r.get(h)
                it = QStandardItem("" if v is None else str(v))
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it.setData(v, Qt.ItemDataRole.EditRole)
                if col:
                    it.setBackground(QBrush(QColor(col)))
                items.append(it)
            self.model.appendRow(items)
        self.view.setSortingEnabled(True)
        hdr = self.view.horizontalHeader()
        for i in range(len(headers)):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.view.resizeColumnToContents(i)
            if self.view.columnWidth(i) > 420:
                self.view.setColumnWidth(i, 420)
        self._count()


# =============================================================================
# Main window
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1280, 860)
        self.setMinimumSize(980, 660)
        self.setAcceptDrops(True)
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.cancel = threading.Event()
        self.outputs: Dict[str, str] = {}
        self.last_result: Optional[RunResult] = None
        self.log_lines: List[tuple] = []
        self._output_user_set = False
        self._closing = False
        self.have_results = False
        self.result_status = ""
        self._build()
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._refresh_ready()
        self._log(f"{APP_NAME} {APP_VERSION} ready - DWG 2010-2025 and DXF drawings supported.", "INFO")

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        self._menus()
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        root.addWidget(self._step_bar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_inputs())
        self.stack.addWidget(self._page_results())
        root.addWidget(self.stack, 1)
        root.addWidget(self._action_bar())
        self.setCentralWidget(central)
        self._log_dock()
        self.statusBar().hide()

    def _menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "New region", self.new_region, "Ctrl+N")
        self._act(m, "Add drawing...", self.pick_drawing, "Ctrl+O")
        self._act(m, "Add splice reports / address lists...", lambda: self.data.add_files(), "Ctrl+Shift+O")
        m.addSeparator()
        self._act(m, "Open output folder", self.open_output_folder)
        m.addSeparator()
        self._act(m, "Exit", self.close, "Alt+F4")
        m = mb.addMenu("&View")
        self.act_log = self._act(m, "Activity log", self.toggle_log, "Ctrl+L")
        self.act_log.setCheckable(True)
        m = mb.addMenu("&Help")
        self._act(m, "Quick guide", self.show_guide, "F1")
        self.act_selftest = self._act(m, "Run self-test", lambda: self.start("selftest"))
        m.addSeparator()
        self._act(m, f"About {APP_NAME}", self.show_about)

    def _act(self, menu: Any, text: str, fn: Callable[[], Any], key: str = "") -> QAction:
        a = QAction(text, self)
        if key:
            a.setShortcut(QKeySequence(key))
        a.triggered.connect(lambda _checked=False: fn())
        menu.addAction(a)
        return a

    def _header(self) -> QWidget:
        f = QFrame()
        f.setObjectName("header")
        f.setFixedHeight(72)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(20, 8, 22, 8)
        lay.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(52))
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(APP_NAME)
        t.setObjectName("appTitle")
        s = QLabel("Fiber-number and BFO callouts for FTTx designs, built from splice reports and address lists")
        s.setObjectName("appSub")
        col.addStretch(1)
        col.addWidget(t)
        col.addWidget(s)
        col.addStretch(1)
        lay.addLayout(col, 1)
        v = QLabel(f"v{APP_VERSION}")
        v.setObjectName("appVer")
        lay.addWidget(v)
        return f

    def _step_bar(self) -> QWidget:
        f = QFrame()
        f.setObjectName("stepBar")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(0)
        self.steps = QButtonGroup(self)
        self.steps.setExclusive(True)
        self.btn_step_inputs = QPushButton("1  Inputs")
        self.btn_step_results = QPushButton("2  Results")
        for i, b in enumerate((self.btn_step_inputs, self.btn_step_results)):
            b.setObjectName("step")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.steps.addButton(b, i)
            lay.addWidget(b)
        self.btn_step_inputs.setChecked(True)
        self.btn_step_results.setEnabled(False)
        self.btn_step_results.setToolTip("Available after Validate or Generate")
        self.steps.idClicked.connect(self.go)
        lay.addStretch(1)
        return f

    def go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        b = self.steps.button(index)
        if b is not None and not b.isChecked():
            b.setChecked(True)

    def _scroll_page(self) -> tuple:
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
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(16)
        sc.setWidget(inner)
        outer.addWidget(sc)
        return page, lay

    @staticmethod
    def _row(*widgets: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            h.addWidget(x)
        return w

    def _page_inputs(self) -> QWidget:
        page, lay = self._scroll_page()
        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)

        c, cl = card("Design drawing", "1", "The region's FTTx design: AutoCAD .dwg (2010-2025) or .dxf.")
        self.ed_drawing = PathEdit("Drop the .dwg / .dxf here or click Browse")
        self.ed_drawing.textChanged.connect(lambda _t: self._drawing_changed())
        b = QPushButton("Browse...")
        b.clicked.connect(self.pick_drawing)
        cl.addWidget(self._row(self.ed_drawing, b))
        self.lbl_drawing = QLabel("")
        self.lbl_drawing.setObjectName("hint")
        self.lbl_drawing.setWordWrap(True)
        cl.addWidget(self.lbl_drawing)
        left.addWidget(c)

        c, cl = card("Splice reports & address lists", "2",
                     "Add everything for the region in one list - files, folders or .zip archives. Splice reports and "
                     "address lists are recognised automatically; duplicates are ignored.")
        self.data = DataList()
        self.data.start_dir = lambda: self._start_dir()
        self.data.changed.connect(self._data_changed)
        self.data.drawing_found.connect(self._set_drawing)
        self.data.rejected.connect(self._rejected)
        cl.addWidget(self.data)
        left.addWidget(c, 1)

        c, cl = card("Output folder", "3", "The callouts DXF and the QA/QC workbook are saved here.")
        self.ed_output = PathEdit("callout_output next to the drawing")
        self.ed_output.textEdited.connect(self._output_edited)
        b = QPushButton("Browse...")
        b.clicked.connect(self.pick_output)
        cl.addWidget(self._row(self.ed_output, b))
        left.addWidget(c)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(16)
        c, cl = card("Callout standard", "", "Every callout is written exactly like the reference design.")
        cl.addWidget(CalloutPreview())
        s = CalloutSpec()
        for line in (f"MULTILEADER on layer {s.terminal_layer} (magenta, ACI {s.layer_color})",
                     f"Text style {s.text_style}, height {s.text_height:g}, closed-filled arrow {s.arrow_size:g}",
                     "Fiber number  N = (PON - 1) x splitter size + PON PORT",
                     f"Cable callout  {s.cable_prefix} <fiber count> / <lowest>-<highest>"):
            lb = QLabel("•  " + line)
            lb.setObjectName("specLine")
            lb.setWordWrap(True)
            cl.addWidget(lb)
        auto = QLabel("Detected from your files on every run: closures, handholes, cables, address-list columns, "
                      "splitter size and drawing units - nothing to configure for a new region.")
        auto.setObjectName("hint")
        auto.setWordWrap(True)
        cl.addSpacing(4)
        cl.addWidget(auto)
        right.addWidget(c)
        right.addStretch(1)
        cols.addLayout(right, 2)
        lay.addLayout(cols, 1)
        return page

    def _page_results(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 12)
        lay.setSpacing(14)

        self.banner = QFrame()
        self.banner.setObjectName("bannerInfo")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(16)
        txt = QVBoxLayout()
        txt.setSpacing(3)
        self.banner_title = QLabel("")
        self.banner_title.setObjectName("bannerTitle")
        self.banner_title.setWordWrap(True)
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        self.banner_text.setTextFormat(Qt.TextFormat.RichText)
        self.banner_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner_detail = QLabel("")
        self.banner_detail.setObjectName("bannerDetail")
        self.banner_detail.setWordWrap(True)
        txt.addWidget(self.banner_title)
        txt.addWidget(self.banner_text)
        txt.addWidget(self.banner_detail)
        bl.addLayout(txt, 1)
        self.btn_open_dxf = QPushButton("Open callouts DXF")
        self.btn_open_dxf.setObjectName("primary")
        self.btn_open_qa = QPushButton("Open QA workbook")
        self.btn_open_folder = QPushButton("Open folder")
        self.btn_open_dxf.clicked.connect(lambda: self._open(self.outputs.get("Callouts DXF")))
        self.btn_open_qa.clicked.connect(lambda: self._open(self.outputs.get("QA workbook")))
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        for b in (self.btn_open_dxf, self.btn_open_qa, self.btn_open_folder):
            b.setVisible(False)
            bl.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.banner)

        k = QHBoxLayout()
        k.setSpacing(12)
        self.kpi_t = Kpi("Fiber-number callouts", ACCENT)
        self.kpi_c = Kpi("BFO callouts", PRIMARY)
        self.kpi_clean = Kpi("Clean placement", "#1B7F3B")
        self.kpi_e = Kpi("Errors", "#C62828")
        self.kpi_w = Kpi("Warnings", "#9A5B00")
        for w in (self.kpi_t, self.kpi_c, self.kpi_clean, self.kpi_e, self.kpi_w):
            k.addWidget(w)
        lay.addLayout(k)

        self.tabs = QTabWidget()
        self.tbl_issues = Table("Search issues...", {
            "Errors and warnings": lambda r: r["Severity"] in ("ERROR", "WARNING"),
            "Errors": lambda r: r["Severity"] == "ERROR",
            "Warnings": lambda r: r["Severity"] == "WARNING",
            "All, including info": lambda r: True})
        self.tbl_callouts = Table("Search callouts - text, closure, OLM...", {
            "All callouts": lambda r: True,
            "Fiber number": lambda r: r["Kind"] == "Fiber number",
            "BFO": lambda r: r["Kind"] == "BFO",
            "Placement to review": lambda r: "PLACEMENT REVIEW" in (r["Notes"] or ""),
            "Failed": lambda r: r["Status"] == "FAILED"})
        self.tbl_network = Table("Search...")
        self.tbl_existing = Table("Search...", {
            "All": lambda r: True,
            "Differences only": lambda r: not str(r.get("Result", "")).startswith("MATCH")})
        self.tabs.addTab(self.tbl_issues, "Issues")
        self.tabs.addTab(self.tbl_callouts, "Callouts")
        self.tabs.addTab(self.tbl_network, "Network")
        self.tabs.addTab(self.tbl_existing, "Existing callouts")
        lay.addWidget(self.tabs, 1)
        return page

    def _action_bar(self) -> QWidget:
        f = QFrame()
        f.setObjectName("actionBar")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(22, 10, 22, 10)
        lay.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(5)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        col.addWidget(self.status)
        col.addWidget(self.progress)
        lay.addLayout(col, 1)
        self.btn_log = QPushButton("Show log")
        self.btn_log.setObjectName("link")
        self.btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log.clicked.connect(self.toggle_log)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setVisible(False)
        self.btn_validate = QPushButton("Validate")
        self.btn_validate.setObjectName("secondary")
        self.btn_validate.setToolTip("Analyse the inputs and list every problem - nothing is written")
        self.btn_generate = QPushButton("Generate Callouts")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.setToolTip("Write the callouts DXF and the QA/QC workbook")
        self.btn_cancel.clicked.connect(self.cancel_job)
        self.btn_validate.clicked.connect(lambda: self.start("validate"))
        self.btn_generate.clicked.connect(lambda: self.start("generate"))
        for b in (self.btn_log, self.btn_cancel, self.btn_validate, self.btn_generate):
            lay.addWidget(b)
        return f

    def _log_dock(self) -> None:
        self.dock = QDockWidget("Activity log", self)
        self.dock.setObjectName("logDock")
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 4, 8, 8)
        row = QHBoxLayout()
        self.cb_level = QComboBox()
        self.cb_level.addItems(["All messages", "Warnings and errors"])
        self.cb_level.currentIndexChanged.connect(self._render_log)
        b1 = QPushButton("Clear")
        b1.clicked.connect(self._clear_log)
        b2 = QPushButton("Save log...")
        b2.clicked.connect(self._save_log)
        row.addWidget(self.cb_level)
        row.addStretch(1)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont(MONO_FONT, 9))
        self.console.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.console)
        self.dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [240], Qt.Orientation.Vertical)
        self.dock.visibilityChanged.connect(self._dock_visibility)
        self.dock.hide()

    # ----------------------------------------------------------------- input handling
    def _start_dir(self) -> str:
        d = self.ed_drawing.text().strip()
        if d and Path(d).parent.exists():
            return str(Path(d).parent)
        return str(self.settings.value("lastDir", "") or "")

    def _set_drawing(self, path: str) -> None:
        self.ed_drawing.setText(path)

    def pick_drawing(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Design drawing", self._start_dir(),
                                           "CAD drawings (*.dwg *.dxf);;All files (*)")
        if f:
            self.settings.setValue("lastDir", str(Path(f).parent))
            self._set_drawing(f)

    def pick_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.ed_output.text() or self._start_dir())
        if d:
            self.ed_output.setText(d)
            self._output_user_set = True

    def _output_edited(self, text: str) -> None:
        self._output_user_set = bool(text.strip())

    @staticmethod
    def drawing_check(p: str) -> tuple:
        """(message, usable) for a drawing path."""
        path = Path(p)
        if not path.is_file():
            return "File not found", False
        if path.suffix.lower() not in DRAWING_EXTS:
            return "Not a .dwg or .dxf file", False
        info = f"{path.suffix.upper().lstrip('.')}  \u00b7  {path.stat().st_size / 1e6:.1f} MB"
        if path.suffix.lower() == ".dwg":
            from .dwg_native import KNOWN, SUPPORTED
            try:
                with path.open("rb") as fh:
                    ver = fh.read(6).decode("ascii", "replace")
            except OSError as exc:
                return f"Cannot read the file: {exc}", False
            if ver not in SUPPORTED:
                return (f"{info}  \u00b7  {KNOWN.get(ver, 'unrecognised')} format - save it as AutoCAD 2010 or newer "
                        "DWG (or as DXF) and try again"), False
            info += f"  \u00b7  {SUPPORTED[ver]} format"
        return info, True

    def _drawing_changed(self) -> None:
        raw = self.ed_drawing.text()
        p = raw.strip().strip('"').strip()
        if p != raw:
            self.ed_drawing.setText(p)      # re-enters with the cleaned path
            return
        self.result_status = ""
        if not p:
            self._set_drawing_status("", "hint")
        else:
            msg, ok = self.drawing_check(p)
            self._set_drawing_status(("\u2713  " if ok else "\u26a0  ") + msg, "ok" if ok else "bad")
            if ok:
                self.settings.setValue("lastDir", str(Path(p).parent))
                if not self._output_user_set:
                    self.ed_output.setText(str(Path(p).parent / "callout_output"))
        self._refresh_ready()

    def _set_drawing_status(self, text: str, kind: str) -> None:
        self.lbl_drawing.setText(text)
        self.lbl_drawing.setObjectName(kind)
        self.lbl_drawing.style().unpolish(self.lbl_drawing)
        self.lbl_drawing.style().polish(self.lbl_drawing)

    def _rejected(self, names: List[str]) -> None:
        shown = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        self._log(f"Not added (not a spreadsheet, folder or .zip): {', '.join(names)}", "WARNING")
        QMessageBox.information(self, APP_NAME, f"Not added: {shown}\n\nAdd splice reports and address lists as "
                                ".xlsx / .xls / .csv files, folders or .zip archives. Drawings go in the drawing field.")

    def _data_changed(self) -> None:
        self.result_status = ""
        self._refresh_ready()

    def _ready(self) -> str:
        """Empty when Validate / Generate can run, otherwise what is missing."""
        p = self.ed_drawing.text().strip()
        if not p:
            return "Add the design drawing and its splice reports / address lists to begin."
        if not self.drawing_check(p)[1]:
            return "The design drawing cannot be used - see the message under the drawing."
        if not self.data.paths():
            return "Add the splice reports and address lists of the region."
        return ""

    def _refresh_ready(self) -> None:
        if self.thread is not None:
            return
        why = self._ready()
        for b in (self.btn_validate, self.btn_generate):
            b.setEnabled(not why)
        self.status.setText(why or self.result_status or "Ready - Validate to check the inputs, or Generate Callouts.")

    def config(self) -> RunConfig:
        cfg = RunConfig()
        cfg.drawing_path = self.ed_drawing.text().strip()
        data = self.data.paths()
        cfg.splice_paths = list(data)
        cfg.address_paths = list(data)
        cfg.output_dir = self.ed_output.text().strip() or str(Path(cfg.drawing_path).parent / "callout_output")
        return cfg

    def new_region(self) -> None:
        if self.thread is not None:
            return
        self.ed_drawing.clear()
        self.data.clear()
        self.ed_output.clear()
        self._output_user_set = False
        self.last_result = None
        self.outputs = {}
        self.have_results = False
        self.result_status = ""
        self.btn_step_results.setEnabled(False)
        self.go(0)
        self._refresh_ready()
        self._log("New region - inputs cleared", "INFO")

    # ----------------------------------------------------------------- drag & drop anywhere
    def dragEnterEvent(self, e: Any) -> None:  # noqa: N802
        if accepts_urls(e) and self.thread is None:
            e.acceptProposedAction()

    def dragMoveEvent(self, e: Any) -> None:  # noqa: N802
        self.dragEnterEvent(e)

    def dropEvent(self, e: Any) -> None:  # noqa: N802
        if self.thread is not None:
            return
        self.go(0)
        self.data.add_many(dropped_paths(e))

    # ----------------------------------------------------------------- log
    def toggle_log(self) -> None:
        self.dock.setVisible(not self.dock.isVisible())

    def _dock_visibility(self, visible: bool) -> None:
        self.btn_log.setText("Hide log" if visible else "Show log")
        self.act_log.setChecked(visible)

    def _log(self, msg: str, level: str) -> None:
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((stamp, level, msg))
        if len(self.log_lines) > 20000:
            del self.log_lines[:5000]
        if self._visible(level):
            self._append(stamp, level, msg)

    def _visible(self, level: str) -> bool:
        return self.cb_level.currentIndex() == 0 or level in ("WARNING", "ERROR", "SUCCESS")

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
        f, _ = QFileDialog.getSaveFileName(self, "Save log", str(Path(self._start_dir() or ".") / "fibercallout_log.txt"),
                                           "Text (*.txt)")
        if f:
            Path(f).write_text("\n".join(f"[{s}] {l:<7} {m}" for s, l, m in self.log_lines), encoding="utf-8")

    # ----------------------------------------------------------------- outputs
    def _open(self, path: Optional[str]) -> None:
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif path:
            QMessageBox.warning(self, APP_NAME, f"File not found:\n{path}")

    def open_output_folder(self) -> None:
        p = self.outputs.get("Callouts DXF", "")
        folder = Path(p).parent if p else Path(self.ed_output.text().strip() or ".")
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QMessageBox.information(self, APP_NAME, "The output folder is created when the callouts are generated.")

    def show_results(self, res: RunResult) -> None:
        s = res.summary
        n_t, n_c = s.get("Fiber-number callouts", 0), s.get("BFO callouts", 0)
        n_e, n_w = s.get("Errors", 0), s.get("Warnings", 0)
        self.kpi_t.set(n_t)
        self.kpi_c.set(n_c)
        self.kpi_clean.set(f"{s.get('Placement - clean', 0)} / {n_t + n_c}")
        self.kpi_e.set(n_e)
        self.kpi_w.set(n_w)
        self.outputs = dict(res.outputs)
        generated = bool(self.outputs)
        self.banner_detail.setText(
            f"{s.get('OLMs', '')}  \u00b7  {s.get('Formula', '')}  \u00b7  {s.get('Splice reports', 0)} splice report(s), "
            f"{s.get('Address rows (PON assigned)', 0)} address rows, {s.get('Closures in drawing', 0)} closures")
        total = n_t + n_c
        errs = f" - {n_e} error(s) to review" if n_e else ""
        if generated:
            self.banner.setObjectName("bannerOk" if not n_e else "bannerWarn")
            self.banner_title.setText(f"{total:,} callouts ready{errs}")
            self.banner_text.setText(
                f"Saved <b>{Path(self.outputs['Callouts DXF']).name}</b> and the QA workbook.<br>"
                "To place them: open the callouts DXF in AutoCAD &rarr; <b>Ctrl+A</b>, <b>Ctrl+C</b> &rarr; switch to the "
                "design drawing &rarr; <b>PASTEORIG</b> (pastes at the original coordinates).")
        else:
            self.banner.setObjectName("bannerInfo" if not n_e else "bannerWarn")
            self.banner_title.setText(f"Validation complete - {total:,} callouts planned{errs}")
            self.banner_text.setText("Nothing was written. Review the issues below, then <b>Generate Callouts</b>.")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        for b in (self.btn_open_dxf, self.btn_open_qa, self.btn_open_folder):
            b.setVisible(generated)

        rows = [{"Kind": "Fiber number" if p.kind == "TERMINAL" else "BFO", "Text": p.text.replace("\\P", " / "),
                 "OLM": p.olm, "Closure": p.closure, "Anchor": p.anchor, "Numbers": fmt_numbers(p.numbers, "exact", 0),
                 "Status": p.status, "Existing": p.existing_match, "Notes": p.notes, "Calculation": p.calculation,
                 "ID": p.uid} for p in res.plans]
        self.tbl_callouts.fill(rows, lambda r: "#FDECEA" if r["Status"] == "FAILED" else
                               ("#FFF6E0" if "PLACEMENT REVIEW" in (r["Notes"] or "") else None))
        issues = [{"Severity": i.severity, "Category": i.category, "Object": i.obj, "Message": i.message}
                  for i in res.issues.items]
        order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        issues.sort(key=lambda r: (order.get(r["Severity"], 3), r["Category"]))
        self.tbl_issues.fill(issues, lambda r: {"ERROR": "#FDECEA", "WARNING": "#FFF6E0"}.get(r["Severity"]))
        self.tbl_issues.set_filter("Errors and warnings" if n_e + n_w else "All, including info")
        self.tabs.setTabText(0, f"Issues ({n_e + n_w})" if n_e + n_w else "Issues")
        self.tabs.setTabText(1, f"Callouts ({len(rows)})")
        self.tbl_network.fill(res.network)
        self.tbl_existing.fill(res.existing_rows, lambda r: "#E8F5E9" if str(r.get("Result", "")).startswith("MATCH")
                               else None)
        self.tabs.setTabVisible(3, bool(res.existing_rows))
        if res.existing_rows:
            ok = s.get("Existing callouts matched", 0)
            self.tabs.setTabText(3, f"Existing callouts ({ok}/{s.get('Existing callouts found', 0)} identical)")
        self.tabs.setCurrentIndex(0 if n_e + n_w else 1)
        self.have_results = True
        self.btn_step_results.setEnabled(True)
        self.go(1)

    # ----------------------------------------------------------------- jobs
    def start(self, task: str) -> None:
        if self.thread is not None:
            return
        cfg = self.config()
        if task in ("validate", "generate"):
            why = self._ready()
            if why:
                QMessageBox.information(self, APP_NAME, why)
                self.go(0)
                return
            if not self._output_user_set and not self.ed_output.text().strip():
                self.ed_output.setText(cfg.output_dir)
        self.cancel.clear()
        self.progress.setValue(0)
        self._log(f"--- {task.upper()} ---", "INFO")
        self._busy(True, task)
        self.thread = QThread(self)
        self.worker = Worker(task, cfg, self.cancel, self.last_result if task == "generate" else None)
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
        if self._closing:
            self.close()

    def _busy(self, busy: bool, task: str = "") -> None:
        self.btn_cancel.setVisible(busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_validate.setVisible(not busy)
        self.btn_generate.setVisible(not busy)
        self.progress.setVisible(busy)
        self.stack.widget(0).setEnabled(not busy)
        for b in (self.btn_step_inputs, self.btn_step_results):
            b.setEnabled(not busy and (b is self.btn_step_inputs or self.have_results))
        self.act_selftest.setEnabled(not busy)
        if busy:
            self.status.setText({"validate": "Validating...", "generate": "Generating callouts...",
                                 "selftest": "Running self-test..."}.get(task, "Working..."))
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()
            self._refresh_ready()

    def cancel_job(self) -> None:
        self.cancel.set()
        self.btn_cancel.setEnabled(False)
        self.status.setText("Cancelling...")
        self._log("Cancelling...", "WARNING")

    def _progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(pct)
        if msg and not self.cancel.is_set():
            self.status.setText(f"{msg}...")

    def _done(self, task: str, res: Any) -> None:
        if task in ("validate", "generate") and isinstance(res, RunResult):
            self.last_result = res
            self.show_results(res)
            s = res.summary
            self.result_status = (("Generated: " if res.outputs else "Validated: ") +
                                  f"{s.get('Fiber-number callouts', 0)} fiber-number + {s.get('BFO callouts', 0)} BFO "
                                  f"callouts  \u00b7  {s.get('Errors', 0)} error(s), {s.get('Warnings', 0)} warning(s)")
        elif task == "selftest":
            ok, _text = res
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, APP_NAME, "Self-test passed - every check succeeded." if ok else
                "Self-test FAILED - details are in the activity log.")
            if not ok:
                self.dock.show()

    def _failed(self, task: str, msg: str) -> None:
        if msg == "Cancelled by user":
            self._log("Cancelled", "WARNING")
            self.result_status = "Cancelled"
            return
        self._log(f"{task} failed: {msg}", "ERROR")
        self.result_status = f"{task.capitalize()} failed - see the log"
        self.dock.show()
        if not self._closing:
            QMessageBox.critical(self, APP_NAME, f"{task.capitalize()} failed:\n\n{msg}\n\nDetails are in the activity log.")

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self.thread is not None:
            if not self._closing:
                if QMessageBox.question(self, APP_NAME, "A job is still running. Cancel it and exit?") != \
                        QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                self._closing = True
                self.cancel.set()
            event.ignore()          # closes from _cleanup_thread once the worker has stopped
            return
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()

    # ----------------------------------------------------------------- help
    def show_guide(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(f"{APP_NAME} - Quick guide")
        d.resize(720, 640)
        lay = QVBoxLayout(d)
        tb = QTextBrowser()
        tb.setHtml(QUICK_GUIDE)
        tb.setOpenExternalLinks(True)
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.exec()

    def show_about(self) -> None:
        d = QDialog(self)
        d.setWindowTitle(f"About {APP_NAME}")
        lay = QVBoxLayout(d)
        row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(112))
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        txt = QLabel(f"<h2 style='margin-bottom:2px'>{APP_NAME}</h2><p>Version {APP_VERSION}</p>"
                     "<p>DES_FIBER_SPL fiber-number and BFO callouts for FTTx OSP designs, computed from splice reports "
                     "and address lists and written as MULTILEADERs identical to the reference drafting standard, "
                     "with a QA/QC workbook.</p>"
                     f"<p style='color:#66788A'>Python {sys.version.split()[0]} &middot; PyQt6 &middot; ezdxf &middot; "
                     "openpyxl</p>")
        txt.setWordWrap(True)
        txt.setMinimumWidth(380)
        row.addWidget(txt, 1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(d.accept)
        lay.addWidget(bb)
        d.exec()


def run_gui(on_ready: Optional[Callable[[Any, Any], None]] = None) -> int:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FTTx.FiberCalloutStudio")
        except Exception:  # noqa: BLE001 - taskbar grouping only
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(QFont(UI_FONT, 10))
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    if on_ready is not None:
        QTimer.singleShot(0, lambda: on_ready(win, app))
    return app.exec()


__all__ = ["run_gui", "MainWindow"]
