"""Operator window (Tkinter, part of standard Python on Windows; bundled in the packaged program).

Layout: header with logo - Inputs card - Options card (regional config, approved overrides, completed
workbooks to compare) - action bar with progress - Results / Log tabs - status bar. The last used
settings are remembered per user.
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
DEFAULT_CONFIG_LABEL = "Default settings (built-in)"


def _settings_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "FTTH Address List Tool" / "settings.json"


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


def regional_configs() -> dict[str, Path | None]:
    """Display name -> config file, for the configs in <tool folder>/config (default first)."""
    out: dict[str, Path | None] = {DEFAULT_CONFIG_LABEL: None}
    folder = TOOL_ROOT / "config"
    for p in sorted(folder.glob("*.toml")) if folder.exists() else []:
        if p.name != "default_config.toml":
            out[p.stem.replace("_", " ").capitalize()] = p
    return out


def config_description(path: Path | None) -> str:
    """First comment line of a config file, plus the rules it accepts."""
    if path is None:
        return "Every inferred value is left for review (amber cells); nothing is accepted automatically."
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "Configuration file cannot be read."
    first = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("#") and ln.strip("# ").strip()), "")
    try:
        from .config import load_config
        rules = load_config(path).get("approvals", {}).get("accepted_rules", [])
    except Exception as exc:  # shown to the operator, never raised
        return f"{first}  -  invalid configuration: {exc}"
    return first + (f"  Accepts: {', '.join(rules)}." if rules else "")


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
        self.geometry("1040x740")
        self.minsize(880, 640)
        self.configure(background=BG)
        self.q: queue.Queue = queue.Queue()
        self.outcomes: dict[str, object] = {}
        self.vars = {k: tk.StringVar() for k in ("reports", "drawing", "out", "prefix", "olm", "config",
                                                  "overrides", "reference")}
        self.configs = regional_configs()
        self._ui_style()
        self._ui_icon()
        self._ui_header()
        self.status = ttk.Label(self, text="Ready", style="Status.TLabel", anchor="w", padding=(16, 3))
        self.status.pack(fill="x", side="bottom")          # packed first: always keeps its line
        body = ttk.Frame(self, style="Body.TFrame", padding=(14, 10, 14, 4))
        body.pack(fill="both", expand=True)
        self._ui_inputs(body)
        self._ui_options(body)
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
            ("base", 10, "normal"), ("bold", 10, "bold"), ("title", 15, "bold"), ("sub", 9, "normal"),
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
        st.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=self.fonts["small"])
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
        self.logo_small = self.logo = None
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
            tk.Label(bar, image=self.logo, background=NAVY).pack(side="left", padx=(16, 10), pady=8)
        txt = tk.Frame(bar, background=NAVY)
        txt.pack(side="left", pady=8, padx=(0 if self.logo else 16, 0))
        tk.Label(txt, text="FTTH Address List Generator", font=self.fonts["title"], foreground="#FFFFFF",
                 background=NAVY).pack(anchor="w")
        tk.Label(txt, text="Splice reports + design drawing  →  OLM address-list workbooks",
                 font=self.fonts["sub"], foreground="#B8C7D9", background=NAVY).pack(anchor="w")
        tk.Label(bar, text=f"v{__version__}", font=self.fonts["small"], foreground="#B8C7D9",
                 background=NAVY_2, padx=10, pady=3).pack(side="right", padx=18)

    def _ui_card(self, parent, title: str, step: str):
        outer = ttk.Frame(parent, style="Card.TFrame", padding=(14, 8, 14, 8))
        outer.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(outer, style="Plain.TFrame", padding=0)
        head.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        tk.Label(head, text=step, background=ACCENT, foreground="#FFFFFF", font=self.fonts["bold"],
                 width=2).pack(side="left", padx=(0, 8))
        ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side="left")
        outer.columnconfigure(1, weight=1)
        return outer

    def _ui_row(self, card, r, label, key, buttons=(), tip=None, required=False):
        lab = ttk.Label(card, text=label + ("  *" if required else ""), style="Card.TLabel", width=30)
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

    # ------------------------------------------------------------------ cards
    def _ui_inputs(self, body):
        c = self._ui_card(body, "Inputs", "1")
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
        self.olm_box = ttk.Combobox(c, textvariable=self.vars["olm"], values=["All OLMs found"])
        self.olm_box.grid(row=5, column=1, sticky="we", pady=2, padx=(0, 6))
        ttk.Button(c, text="Scan reports", command=self.scan).grid(row=5, column=2, sticky="w")
        Tooltip(self.olm_box, "Leave 'All OLMs found' to generate every OLM, or Scan and pick one.")

    def _ui_options(self, body):
        c = self._ui_card(body, "Options", "2")
        ttk.Label(c, text="Regional config", style="Card.TLabel", width=30).grid(row=1, column=0, sticky="w", pady=2)
        self.cfg_box = ttk.Combobox(c, textvariable=self.vars["config"], values=list(self.configs))
        self.cfg_box.grid(row=1, column=1, sticky="we", pady=2, padx=(0, 6))
        self.cfg_box.bind("<<ComboboxSelected>>", lambda _: self._describe_config())
        self.cfg_box.bind("<FocusOut>", lambda _: self._describe_config())
        ttk.Button(c, text="Browse…", command=self._pick_config).grid(row=1, column=2, sticky="w", padx=(0, 4))
        ttk.Button(c, text="Edit", command=lambda: _open(self._config_path())).grid(row=1, column=3, sticky="w")
        self.cfg_hint = ttk.Label(c, text="", style="Hint.TLabel", wraplength=900, justify="left")
        self.cfg_hint.grid(row=2, column=1, columnspan=3, sticky="w", pady=(0, 4))
        c.bind("<Configure>", lambda e: self.cfg_hint.configure(wraplength=max(300, e.width - 330)))
        Tooltip(self.cfg_box, "Regional conventions and the approvals policy. Files in the tool's config folder are "
                              "listed; 'Desk study acceptance' accepts the evidence-based Fiber Splice rules.")
        self._ui_row(c, 3, "Approved overrides (.csv)", "overrides",
                  [("Browse…", lambda: self._ui_file("overrides", [("CSV", "*.csv"), ("All", "*.*")])),
                   ("Clear", lambda: self.vars["overrides"].set(""))],
                  "The review worklist from an earlier run, filled in (action ACCEPT or SET, value, approved_by, "
                  "approved_on, reason). Approved cells are shown in blue as APPROVED.")
        self._ui_row(c, 4, "Completed workbooks to compare", "reference",
                  [("File…", lambda: self._ui_file("reference", [("Excel", "*.xlsx"), ("All", "*.*")])),
                   ("Folder…", lambda: self._ui_dir("reference"))],
                  "Optional. Manually completed address list(s) - a file, or a folder matched by OLM name. The run "
                  "adds comparison_with_reference.xlsx and the match figures in the Results tab.")

    def _ui_actions(self, body):
        bar = ttk.Frame(body, style="Body.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        self.run_btn = ttk.Button(bar, text="▶  Generate address list(s)", style="Accent.TButton",
                                  command=self.start)
        self.run_btn.pack(side="left")
        ttk.Button(bar, text="Open output folder", command=lambda: _open(self.vars["out"].get())).pack(
            side="left", padx=8)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=220)
        self.progress.pack(side="right")
        self.run_state = ttk.Label(bar, text="", foreground=MUTED, background=BG)
        self.run_state.pack(side="right", padx=10)

    def _ui_results(self, body):
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill="both", expand=True)
        res = ttk.Frame(self.tabs, style="Card.TFrame", padding=8)
        cols = ("olm", "result", "rows", "confirmed", "approved", "provisional", "unresolved", "match")
        heads = ("OLM", "Result", "Rows", "Confirmed", "Approved", "Provisional", "Unresolved",
                 "Match with completed list")
        widths = (90, 190, 50, 92, 86, 98, 98, 275)
        self.tree = ttk.Treeview(res, columns=cols, show="headings", height=3, selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w" if c in ("olm", "result", "match") else "center")
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
        use = ttk.Button(btns, text="Use worklist as overrides", command=self._use_worklist)
        use.pack(side="left", padx=(12, 0))
        Tooltip(use, "After filling in the review worklist (ACCEPT / SET + your name and date), select it as the "
                     "overrides file and Generate again.")
        Tooltip(self.tree, "Double-click a row to open its workbook.")
        log = ttk.Frame(self.tabs, padding=0)
        self.log = scrolledtext.ScrolledText(log, height=10, font=("Consolas", 9), background="#FBFCFD", wrap="word",
                                             foreground=TEXT, relief="flat", borderwidth=0)
        self.log.pack(fill="both", expand=True)
        self.tabs.add(res, text="Results")
        self.tabs.add(log, text="Log")

    # ------------------------------------------------------------------ helpers
    def _ui_dir(self, key):
        p = filedialog.askdirectory(initialdir=self.vars[key].get() or None)
        if p:
            self.vars[key].set(p)

    def _ui_file(self, key, types):
        cur = self.vars[key].get()
        p = filedialog.askopenfilename(filetypes=types, initialdir=(str(Path(cur).parent) if cur else None))
        if p:
            self.vars[key].set(p)

    def _pick_config(self):
        p = filedialog.askopenfilename(filetypes=[("Configuration", "*.toml")],
                                       initialdir=str(TOOL_ROOT / "config"))
        if p:
            self.vars["config"].set(p)
            self._describe_config()

    def _config_path(self) -> Path | None:
        v = self.vars["config"].get().strip()
        if not v or v == DEFAULT_CONFIG_LABEL:
            return None
        return self.configs.get(v) or Path(v)

    def _describe_config(self):
        p = self._config_path()
        if p is not None and not p.exists():
            self.cfg_hint.configure(text=f"File not found: {p}", foreground=BAD)
            return
        self.cfg_hint.configure(text=config_description(p), foreground=MUTED)

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
        if not self.vars["reports"].get():
            messagebox.showwarning("Splice reports", "Choose the splice-report folder first.")
            return
        try:
            cfg = load_config(self._config_path())
            reps, issues = load_reports(find_report_files(Path(self.vars["reports"].get())), cfg)
            olms = Network(reps, cfg).olms()
            self.olm_box["values"] = ["All OLMs found"] + olms
            self.say(f"Scan: {len(reps)} report(s) readable; OLMs: {', '.join(olms) or 'none found'}")
            for i in issues:
                if i.severity == "ERROR":
                    self.say(f"  [ERROR] {i.message}")
        except Exception as exc:
            messagebox.showerror("Scan failed", str(exc))

    def _ui_check(self) -> list[str]:
        v = {k: x.get().strip() for k, x in self.vars.items()}
        problems = []
        if not v["reports"] or not Path(v["reports"]).exists():
            problems.append("Splice reports folder: choose an existing folder.")
        if not v["out"]:
            problems.append("Output folder: choose where the results go.")
        if v["drawing"] and (not Path(v["drawing"]).exists() or Path(v["drawing"]).suffix.lower() not in
                             (".dwg", ".dxf")):
            problems.append("Design drawing: the file does not exist or is not a .dwg / .dxf.")
        cp = self._config_path()
        if cp is not None and not cp.exists():
            problems.append(f"Regional config: {cp} not found.")
        if v["overrides"] and (not Path(v["overrides"]).exists() or not v["overrides"].lower().endswith(".csv")):
            problems.append("Approved overrides: the .csv file does not exist.")
        if v["reference"] and not Path(v["reference"]).exists():
            problems.append("Completed workbooks: the file or folder does not exist.")
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
        self.run_state.configure(text="Working…")
        self.tree.delete(*self.tree.get_children())
        self.outcomes.clear()
        self.tabs.select(1)
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        from .pipeline import run
        v = {k: (x.get().strip() or None) for k, x in self.vars.items()}
        olm = v["olm"] if v["olm"] and v["olm"] != "All OLMs found" else None
        try:
            outs = run(v["reports"], v["out"], [olm] if olm else None, self._config_path(), v["overrides"],
                       v["prefix"], v["reference"], v["drawing"], log=self.say)
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
            match = ""
            if o.comparison:
                fs = o.comparison.get("field_stats", {})
                good = sum(s.get("normalised", 0) for s in fs.values())
                tot = sum(s.get("compared", 0) for s in fs.values())
                match = (f"{o.comparison.get('matched')}/{o.comparison.get('ref_rows')} rows \u00b7 "
                         f"{tot - good} cell(s) differ ({100 * good / tot:.1f} %)" if tot else "no rows compared")
            self.tree.insert("", "end", iid=o.olm, tags=(tag,), values=(
                o.olm, result, sum(c.values()) if c else "", c.get("CONFIRMED", ""), c.get("APPROVED", ""),
                c.get("PROVISIONAL", ""), c.get("UNRESOLVED", ""), match))
        drafts = [o.olm for o in outs if not o.final]
        self.run_state.configure(text="Done" if not drafts else f"Done - {len(drafts)} draft(s)",
                                 foreground=OK if not drafts else WARN)
        self.say("Done. " + ("All workbooks FINAL." if not drafts else
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

    def _use_worklist(self):
        o = self._selected()
        if o is not None and o.worklist:
            self.vars["overrides"].set(str(o.worklist))
            self.say(f"Overrides set to {o.worklist}. Fill in action / value / approved_by / approved_on / reason, "
                     f"save, then Generate again.")

    # ------------------------------------------------------------------ settings
    def _load_settings(self):
        data = {}
        try:
            data = json.loads(_settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        for k, var in self.vars.items():
            if isinstance(data.get(k), str):
                var.set(data[k])
        if not self.vars["out"].get():
            self.vars["out"].set(str(Path.home() / "Documents" / "FTTH Address Lists"))
        if not self.vars["config"].get():
            self.vars["config"].set(DEFAULT_CONFIG_LABEL)
        if not self.vars["olm"].get():
            self.vars["olm"].set("All OLMs found")
        self._describe_config()

    def _save_settings(self):
        try:
            p = _settings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({k: v.get() for k, v in self.vars.items()}, indent=1), encoding="utf-8")
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
