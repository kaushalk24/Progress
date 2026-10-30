"""Simple operator window (Tkinter, part of standard Python on Windows)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__


class App(tk.Tk):
    FIELDS = [
        ("reports", "Splice reports folder *", "dir"),
        ("out", "Output folder *", "dir"),
        ("prefix", "File name prefix (e.g. 123456_Example City ST)", "text"),
        ("olm", "OLM (blank = all found)", "olm"),
        ("drawing", "Design drawing (.dwg / .dxf) - recommended", "file"),
        ("config", "Regional config (.toml) - optional", "file"),
        ("overrides", "Approved overrides (.csv) - optional", "file"),
        ("reference", "Completed workbooks to compare - optional", "dir"),
    ]

    def __init__(self):
        super().__init__()
        self.title(f"FTTH Address List Generator {__version__}")
        self.geometry("860x620")
        self.vars = {}
        self.q: queue.Queue = queue.Queue()
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        for i, (key, label, kind) in enumerate(self.FIELDS):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar()
            self.vars[key] = v
            if kind == "olm":
                self.olm_box = ttk.Combobox(frm, textvariable=v, width=70)
                self.olm_box.grid(row=i, column=1, sticky="we")
                ttk.Button(frm, text="Scan", command=self.scan).grid(row=i, column=2, padx=4)
            else:
                ttk.Entry(frm, textvariable=v, width=72).grid(row=i, column=1, sticky="we")
                if kind != "text":
                    ttk.Button(frm, text="Browse...", command=lambda k=key, t=kind: self.browse(k, t)).grid(
                        row=i, column=2, padx=4)
        self.vars["out"].set(str(Path.home() / "Documents" / "FTTH Address Lists"))
        btns = ttk.Frame(frm)
        btns.grid(row=len(self.FIELDS), column=0, columnspan=3, pady=8, sticky="w")
        self.run_btn = ttk.Button(btns, text="Generate address list(s)", command=self.start)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="Open output folder", command=self.open_out).pack(side="left", padx=8)
        self.log = scrolledtext.ScrolledText(frm, height=22, font=("Consolas", 9))
        self.log.grid(row=len(self.FIELDS) + 1, column=0, columnspan=3, sticky="nsew")
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(len(self.FIELDS) + 1, weight=1)
        self.say("1. Choose the splice-report folder and an output folder.  2. Scan to list OLMs.  3. Generate.\n"
                 "Outputs: address-list workbook per OLM (DRAFT in the name while rows need review), a review "
                 "worklist CSV (fill in and use as the overrides file), an exceptions CSV and a run manifest.\n")
        self.after(150, self.drain)

    def browse(self, key, kind):
        p = filedialog.askdirectory() if kind == "dir" else filedialog.askopenfilename()
        if p:
            self.vars[key].set(p)

    def say(self, text):
        self.q.put(text)

    def drain(self):
        while not self.q.empty():
            self.log.insert("end", self.q.get() + "\n")
            self.log.see("end")
        self.after(150, self.drain)

    def scan(self):
        from .config import load_config
        from .network import Network
        from .pipeline import find_report_files
        from .splice_reports import load_reports
        try:
            cfg = load_config(self.vars["config"].get() or None)
            reps, issues = load_reports(find_report_files(Path(self.vars["reports"].get())), cfg)
            olms = Network(reps, cfg).olms()
            self.olm_box["values"] = [""] + olms
            self.say(f"Scan: {len(reps)} report(s) readable; OLMs: {', '.join(olms) or 'none found'}")
            for i in issues:
                if i.severity == "ERROR":
                    self.say(f"  [ERROR] {i.message}")
        except Exception as exc:
            messagebox.showerror("Scan failed", str(exc))

    def start(self):
        if not self.vars["reports"].get() or not self.vars["out"].get():
            messagebox.showwarning("Missing input", "Choose the splice-report folder and the output folder.")
            return
        self.run_btn.state(["disabled"])
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        from .pipeline import run
        v = {k: (x.get().strip() or None) for k, x in self.vars.items()}
        try:
            outs = run(v["reports"], v["out"], [v["olm"]] if v["olm"] else None, v["config"], v["overrides"],
                       v["prefix"], v["reference"], v["drawing"], log=self.say)
            drafts = [o.olm for o in outs if not o.final]
            self.say("Done. " + ("All workbooks FINAL." if not drafts else
                                 f"DRAFT (review required): {', '.join(drafts)} - see Row Status / Exceptions "
                                 f"sheets and the review worklist."))
        except Exception as exc:
            self.say(f"FAILED: {exc}")
        finally:
            self.run_btn.state(["!disabled"])

    def open_out(self):
        p = self.vars["out"].get()
        if p and Path(p).exists():
            if sys.platform.startswith("win"):
                os.startfile(p)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", p])


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
