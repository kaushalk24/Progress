"""Operator window (Tkinter, part of standard Python on Windows; bundled in the packaged program).

Layout: header with logo - Inputs card - action bar with progress - Results / Log tabs - status bar.
The last used inputs are remembered per user. Regional configs, approved overrides and comparisons
with completed lists stay available on the command line (ftth_addrlist_cli.exe run --help).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk

from . import __version__
from .config import TOOL_ROOT

NAVY, NAVY_2, ACCENT, ACCENT_DARK = "#0E2A4A", "#173E66", "#1E88E5", "#1565C0"
BG, CARD, TEXT, MUTED, BORDER = "#F3F5F8", "#FFFFFF", "#1F2933", "#66788A", "#D8DEE6"
OK, WARN, BAD = "#2E7D32", "#B26A00", "#C62828"
ALL_OLMS = "All OLMs found"
FIELDS = ("reports", "drawing", "out", "prefix", "olm")


def _settings_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "FTTH Address List Tool" / "settings.json"


def clean_path(text: str) -> str:
    """A path as typed or pasted: trims spaces and the quotes Windows 'Copy as path' adds."""
    return text.strip().strip('"').strip("'").strip()


def _open(path) -> None:
    if not path or not Path(path).exists():
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _logo_file() -> Path | None:
    """A company logo in <tool folder>/assets/logo.png wins over the built-in one."""
    for p in (TOOL_ROOT / "assets" / "logo.png", Path(__file__).resolve().parent / "assets" / "logo.png"):
        if p.exists():
            return p
    return None


class Tooltip:
    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#FFFDE7", foreground=TEXT, relief="solid",
                 borderwidth=1, wraplength=420, padx=8, pady=5).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"FTTH Address List Generator {__version__}")
        self.geometry("1000x620")
        self.minsize(820, 540)
        self.configure(background=BG)
        self.q: queue.Queue = queue.Queue()
        self.outcomes: dict[str, object] = {}
        self.vars = {k: tk.StringVar() for k in FIELDS}
        self._ui_style()
        self._ui_icon()
        self._ui_header()
        self.status = ttk.Label(self, text="Ready", style="Status.TLabel", anchor="w", padding=(16, 3))
        self.status.pack(fill="x", side="bottom")          # packed first: always keeps its line
        body = ttk.Frame(self, style="Body.TFrame", padding=(14, 10, 14, 4))
        body.pack(fill="both", expand=True)
        self._ui_inputs(body)
        self._ui_actions(body)
        self._ui_results(body)
        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.say(f"FTTH Address List Generator {__version__}. Choose the splice-report folder and an output "
                 f"folder, add the design drawing, then Generate.")
        self.after(150, self.drain)

    # ------------------------------------------------------------------ look
    def _ui_style(self):
        families = set(tkfont.families(self))
        base = next((f for f in ("Segoe UI", "Helvetica Neue", "DejaVu Sans") if f in families), "TkDefaultFont")
        self.fonts = {k: tkfont.Font(self, family=base, size=s, weight=w) for k, s, w in (
            ("base", 10, "normal"), ("bold", 10, "bold"), ("title", 16, "bold"),
            ("card", 11, "bold"), ("small", 9, "normal"), ("button", 11, "bold"))}
        self.option_add("*Font", self.fonts["base"])
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, font=self.fonts["base"])
        st.configure("Body.TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1, bordercolor=BORDER)
        st.configure("Plain.TFrame", background=CARD, borderwidth=0)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("CardTitle.TLabel", background=CARD, foreground=NAVY, font=self.fonts["card"])
        st.configure("Status.TLabel", background="#E4E9EF", foreground=MUTED, font=self.fonts["small"])
        st.configure("TEntry", fieldbackground="#FFFFFF", bordercolor=BORDER, lightcolor=BORDER, padding=3)
        st.configure("TCombobox", fieldbackground="#FFFFFF", bordercolor=BORDER, padding=3)
        st.configure("TButton", padding=(10, 2), background="#EEF2F6", bordercolor=BORDER)
        st.map("TButton", background=[("active", "#E1E8EF")])
        st.configure("Accent.TButton", padding=(18, 6), background=ACCENT, foreground="#FFFFFF",
                     font=self.fonts["button"], bordercolor=ACCENT_DARK)
        st.map("Accent.TButton", background=[("disabled", "#90A4AE"), ("active", ACCENT_DARK)])
        st.configure("Horizontal.TProgressbar", troughcolor="#E4E9EF", background=ACCENT, bordercolor=BORDER)
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(14, 5), font=self.fonts["bold"])
        st.configure("Treeview", rowheight=24, fieldbackground=CARD, background=CARD, bordercolor=BORDER)
        st.configure("Treeview.Heading", font=self.fonts["bold"], background="#E9EEF4")

    def _ui_icon(self):
        self.logo = None
        p = _logo_file()
        if p is None:
            return
        try:
            img = tk.PhotoImage(file=str(p))
            factor = max(1, img.width() // 44)
            self.logo = img.subsample(factor, factor)
            self.iconphoto(True, img)
        except tk.TclError:
            self.logo = None

    def _ui_header(self):
        bar = tk.Frame(self, background=NAVY, height=64)
        bar.pack(fill="x")
        if self.logo is not None:
            tk.Label(bar, image=self.logo, background=NAVY).pack(side="left", padx=(16, 12), pady=10)
        tk.Label(bar, text="FTTH Address List Generator", font=self.fonts["title"], foreground="#FFFFFF",
                 background=NAVY).pack(side="left", pady=10, padx=(0 if self.logo else 16, 0))
        tk.Label(bar, text=f"v{__version__}", font=self.fonts["small"], foreground="#B8C7D9",
                 background=NAVY_2, padx=10, pady=3).pack(side="right", padx=18)

    def _ui_row(self, card, r, label, key, buttons=(), tip=None, required=False):
        lab = ttk.Label(card, text=label + ("  *" if required else ""), style="Card.TLabel", width=24)
        lab.grid(row=r, column=0, sticky="w", pady=2)
        ent = ttk.Entry(card, textvariable=self.vars[key])
        ent.grid(row=r, column=1, sticky="we", pady=2, padx=(0, 6))
        # long paths: keep the end (file / folder name) in view
        self.vars[key].trace_add("write", lambda *_: ent.after_idle(lambda: ent.xview_moveto(1.0)))
        ent.bind("<Configure>", lambda _: ent.xview_moveto(1.0))
        col = 2
        for text, cmd in buttons:
            ttk.Button(card, text=text, command=cmd).grid(row=r, column=col, sticky="w", padx=(0, 4))
            col += 1
        if tip:
            Tooltip(lab, tip)
            Tooltip(ent, tip)
        return ent

    # ------------------------------------------------------------------ layout
    def _ui_inputs(self, body):
        c = ttk.Frame(body, style="Card.TFrame", padding=(14, 8, 14, 10))
        c.pack(fill="x", pady=(0, 8))
        c.columnconfigure(1, weight=1)
        ttk.Label(c, text="Inputs", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._ui_row(c, 1, "Splice reports folder", "reports", [("Browse…", lambda: self._ui_dir("reports"))],
                     "Folder with the Splice Connections Reports (.xlsx). Sub-folders per OLM are fine. Include the "
                     "hub report of every OLM and as many downstream closure reports as possible.", required=True)
        self._ui_row(c, 2, "Design drawing (.dwg)", "drawing",
                     [("Browse…", lambda: self._ui_file("drawing", [("Drawings", "*.dwg *.dxf"), ("All", "*.*")]))],
                     "Recommended. The region's DWG as exported (AutoCAD 2010-2018). Fills Fiber Splice where the "
                     "reports stop. Run FXAUTO / FXMISSING first when drop lines are used.")
        self._ui_row(c, 3, "Output folder", "out", [("Browse…", lambda: self._ui_dir("out"))],
                     "Where the workbooks and reports are written. Existing files are never overwritten.",
                     required=True)
        self._ui_row(c, 4, "File name prefix", "prefix", tip="Start of every output file name, e.g. "
                     "123456_Example City ST")
        ttk.Label(c, text="OLM", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=2)
        self.olm_box = ttk.Combobox(c, textvariable=self.vars["olm"], values=[ALL_OLMS])
        self.olm_box.grid(row=5, column=1, sticky="we", pady=2, padx=(0, 6))
        ttk.Button(c, text="Scan reports", command=self.scan).grid(row=5, column=2, sticky="w")
        Tooltip(self.olm_box, f"Leave '{ALL_OLMS}' to generate every OLM, or Scan and pick one.")

    def _ui_actions(self, body):
        bar = ttk.Frame(body, style="Body.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        self.run_btn = ttk.Button(bar, text="▶  Generate address list(s)", style="Accent.TButton",
                                  command=self.start)
        self.run_btn.pack(side="left")
        ttk.Button(bar, text="Open output folder", command=self._open_out).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=220)
        self.progress.pack(side="right")
        self.run_state = ttk.Label(bar, text="", foreground=MUTED, background=BG)
        self.run_state.pack(side="right", padx=10)

    def _ui_results(self, body):
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill="both", expand=True)
        res = ttk.Frame(self.tabs, style="Card.TFrame", padding=8)
        cols = ("olm", "result", "rows", "confirmed", "approved", "provisional", "unresolved")
        heads = ("OLM", "Result", "Rows", "Confirmed", "Approved", "Provisional", "Unresolved")
        widths = (120, 260, 80, 110, 110, 110, 110)
        self.tree = ttk.Treeview(res, columns=cols, show="headings", height=4, selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w" if c in ("olm", "result") else "center")
        self.tree.tag_configure("final", foreground=OK)
        self.tree.tag_configure("draft", foreground=WARN)
        self.tree.tag_configure("failed", foreground=BAD)
        self.tree.bind("<Double-1>", lambda _: self._open_selected("workbook"))
        btns = ttk.Frame(res, style="Plain.TFrame")
        btns.pack(fill="x", pady=(8, 0), side="bottom")     # packed before the table: the table gives way
        self.tree.pack(fill="both", expand=True)
        for text, what in (("Open workbook", "workbook"), ("Open review worklist", "worklist"),
                           ("Open exceptions", "exceptions_csv"), ("Reports to request", "reports_to_request")):
            ttk.Button(btns, text=text, command=lambda w=what: self._open_selected(w)).pack(side="left", padx=(0, 6))
        log = ttk.Frame(self.tabs, padding=0)
        self.log = scrolledtext.ScrolledText(log, height=10, font=("Consolas", 9), background="#FBFCFD", wrap="word",
                                             foreground=TEXT, relief="flat", borderwidth=0)
        self.log.pack(fill="both", expand=True)
        self.tabs.add(res, text="Results")
        self.tabs.add(log, text="Log")

    # ------------------------------------------------------------------ helpers
    def _value(self, key) -> str:
        return clean_path(self.vars[key].get())

    def _ui_dir(self, key):
        p = filedialog.askdirectory(initialdir=self._value(key) or None)
        if p:
            self.vars[key].set(p)

    def _ui_file(self, key, types):
        cur = self._value(key)
        p = filedialog.askopenfilename(filetypes=types, initialdir=(str(Path(cur).parent) if cur else None))
        if p:
            self.vars[key].set(p)

    def _open_out(self):
        p = self._value("out")
        if p and Path(p).exists():
            _open(p)
        else:
            messagebox.showinfo("Output folder", "The output folder does not exist yet; it is created by the "
                                                 "first run.")

    def say(self, text):
        self.q.put(("log", text))

    def drain(self):
        while not self.q.empty():
            kind, payload = self.q.get()
            if kind == "log":
                self.log.insert("end", payload + "\n")
                self.log.see("end")
                self.status.configure(text=str(payload).splitlines()[0][:160])
            elif kind == "done":
                self._finish(*payload)
        self.after(150, self.drain)

    # ------------------------------------------------------------------ actions
    def scan(self):
        from .config import load_config
        from .network import Network
        from .pipeline import find_report_files
        from .splice_reports import load_reports
        folder = self._value("reports")
        if not folder:
            messagebox.showwarning("Splice reports", "Choose the splice-report folder first.")
            return
        try:
            cfg = load_config()
            out = self._value("out")
            reps, issues = load_reports(find_report_files(Path(folder), exclude=Path(out) if out else None), cfg)
            olms = Network(reps, cfg).olms()
            self.olm_box["values"] = [ALL_OLMS] + olms
            self.say(f"Scan: {len(reps)} report(s) readable; OLMs: {', '.join(olms) or 'none found'}")
            for i in issues:
                if i.severity == "ERROR":
                    self.say(f"  [ERROR] {i.message}")
        except Exception as exc:
            messagebox.showerror("Scan failed", str(exc))

    def _ui_check(self) -> list[str]:
        v = {k: self._value(k) for k in FIELDS}
        problems = []
        if not v["reports"] or not Path(v["reports"]).exists():
            problems.append("Splice reports folder: choose an existing folder.")
        if not v["out"]:
            problems.append("Output folder: choose where the results go.")
        if v["drawing"] and (not Path(v["drawing"]).is_file() or Path(v["drawing"]).suffix.lower() not in
                             (".dwg", ".dxf")):
            problems.append("Design drawing: the file does not exist or is not a .dwg / .dxf.")
        return problems

    def start(self):
        problems = self._ui_check()
        if problems:
            messagebox.showwarning("Check the inputs", "\n".join(problems))
            return
        self._save_settings()
        self.run_btn.state(["disabled"])
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self.run_state.configure(text="Working…", foreground=MUTED)
        self.tree.delete(*self.tree.get_children())
        self.outcomes.clear()
        self.tabs.select(1)
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        from .pipeline import run
        v = {k: (self._value(k) or None) for k in FIELDS}
        olm = v["olm"] if v["olm"] and v["olm"] != ALL_OLMS else None
        try:
            outs = run(v["reports"], v["out"], [olm] if olm else None, None, None, v["prefix"], None, v["drawing"],
                       log=self.say)
            self.q.put(("done", (outs, None)))
        except Exception as exc:
            self.q.put(("done", ([], exc)))

    def _finish(self, outs, exc):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0 if exc is not None else 100)
        self.run_btn.state(["!disabled"])
        if exc is not None:
            self.run_state.configure(text="Failed", foreground=BAD)
            self.say(f"FAILED: {exc}")
            messagebox.showerror("Run failed", str(exc))
            return
        for o in outs:
            self.outcomes[o.olm] = o
            c = o.counts or {}
            if o.workbook is None:
                result, tag = "FAILED - see Log", "failed"
            elif o.final:
                result, tag = "✔ FINAL", "final"
            else:
                result, tag = "DRAFT - review required", "draft"
            self.tree.insert("", "end", iid=o.olm, tags=(tag,), values=(
                o.olm, result, sum(c.values()) if c else "", c.get("CONFIRMED", ""), c.get("APPROVED", ""),
                c.get("PROVISIONAL", ""), c.get("UNRESOLVED", "")))
        drafts = [o.olm for o in outs if not o.final]
        self.run_state.configure(text="Done" if not drafts else f"Done - {len(drafts)} draft(s)",
                                 foreground=OK if not drafts else WARN)
        self.say("Done. Double-click a result row to open its workbook. " + ("All workbooks FINAL." if not drafts else
                             f"DRAFT (review required): {', '.join(drafts)} - see the Row Status and Exceptions sheets "
                             f"and the review worklist."))
        self.tabs.select(0)
        if outs:
            self.tree.selection_set(outs[0].olm)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Results", "Select an OLM row first.")
            return None
        return self.outcomes.get(sel[0])

    def _open_selected(self, what):
        o = self._selected()
        if o is not None:
            p = getattr(o, what, None)
            if p:
                _open(p)
            else:
                messagebox.showinfo("Results", "That file was not written for this OLM.")

    # ------------------------------------------------------------------ settings
    def _load_settings(self):
        data = {}
        try:
            data = json.loads(_settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        for k in FIELDS:
            if isinstance(data.get(k), str):
                self.vars[k].set(data[k])
        if not self.vars["out"].get():
            self.vars["out"].set(str(Path.home() / "Documents" / "FTTH Address Lists"))
        if not self.vars["olm"].get():
            self.vars["olm"].set(ALL_OLMS)

    def _save_settings(self):
        try:
            p = _settings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({k: self.vars[k].get() for k in FIELDS}, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _close(self):
        self._save_settings()
        self.destroy()


def main():
    if sys.platform.startswith("win"):
        try:  # sharp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
