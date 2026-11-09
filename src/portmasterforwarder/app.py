"""
PortMasterForwarder - Your games. Properly organized.

Run:  PortMasterForwarder.exe   (or from source: python -m portmasterforwarder)
Layout: games on the left (pick a category), the selected game's metadata BLOCKS in the middle
(each block has its own source, a Fetch button and your own value) and a live PREVIEW on the right.
All logic lives in portmasterforwarder/core.py and portmasterforwarder/meta.py; this module only contains the screens.
"""
import io
import json
import queue
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from . import core
from . import meta as pm

if core.HAS_PIL:
    from PIL import Image, ImageTk

CONFIG_FILE = core.config_path()
NONE_LABEL = "— hidden —"
NEW_CAT_LABEL = "+ New category..."
NO_GENRE = "—"
TAG_LABELS = {"desc": "description", "rating": "rating", "releasedate": "release date", "genre": "genre",
              "developer": "developer", "publisher": "publisher"}
BLOCK_TITLES = {"genre": "Genre", "rating": "Rating (0 to 10)", "desc": "Description (gameplay only)",
                "releasedate": "Release date", "developer": "Developer", "publisher": "Publisher"}
SOURCE_LABELS = {"auto": "Auto (all sources)", "steam": "Steam", "wikipedia": "Wikipedia", "rawg": "RAWG",
                 "google": "Google", "ai": "AI evaluation", "keep": "Keep current"}
LABEL_TO_SOURCE = {v: k for k, v in SOURCE_LABELS.items()}
IMAGE_SOURCES = [("auto", "Auto (keep current, else online)"), ("web", "Steam"), ("rawg", "RAWG"),
                 ("local", "My computer"), ("none", "Don't change")]
META_GLOBAL = [("Complete only what is missing", "fill"), ("Replace everything", "replace")]
SELECTED_BG, NORMAL_BG = "#d7e9ff", "#f0f0f0"


def make_modal(win, parent):
    win.transient(parent)
    try:
        win.wait_visibility()
        win.grab_set()
    except tk.TclError:
        pass


def trace_write(var, callback):
    try:
        var.trace_add("write", lambda *_a: callback())
    except AttributeError:      # very old Tk
        var.trace("w", lambda *_a: callback())


# ============================================================================ dialogs
class SteamSearchDialog(tk.Toplevel):
    """Type a game name, see the Steam results and pick the right one."""

    def __init__(self, app, parent, term, on_ok):
        super().__init__(parent)
        self.app, self.on_ok, self.results = app, on_ok, []
        self.title("Search Steam")
        self.geometry("520x380")
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Game name:").pack(side="left")
        self.v = tk.StringVar(value=term)
        e = ttk.Entry(top, textvariable=self.v)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Return>", lambda _e: self.search())
        ttk.Button(top, text="Search", command=self.search).pack(side="left")
        self.lb = tk.Listbox(self, activestyle="dotbox")
        self.lb.pack(fill="both", expand=True, padx=8)
        self.lb.bind("<Double-1>", lambda _e: self.ok())
        ttk.Button(self, text="Use the selected game", command=self.ok).pack(pady=8)
        make_modal(self, parent)
        self.search()

    def search(self):
        term = self.v.get().strip()
        if term:
            self.app.bg(lambda: core.steam_search(term), self._fill)

    def _fill(self, res):
        if not self.winfo_exists():
            return
        self.results = res
        self.lb.delete(0, "end")
        for _sid, name in res:
            self.lb.insert("end", name)
        if not res:
            self.lb.insert("end", "nothing found - try another name")

    def ok(self):
        sel = self.lb.curselection()
        if sel and sel[0] < len(self.results):
            self.on_ok(*self.results[sel[0]])
            self.destroy()


class NewCategoryDialog(tk.Toplevel):
    """Create a new category (a new entry on the handheld's home screen) without leaving the game list."""

    def __init__(self, app, on_ok, on_cancel=None):
        super().__init__(app)
        self.on_ok, self.on_cancel, self.done = on_ok, on_cancel, False
        self.title("New category")
        pad = ttk.Frame(self, padding=12)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, wraplength=420, justify="left", text=(
            "A category becomes a folder and a system on the home screen, like GameCube or PC. "
            "Pick the icon (the Art Book Next look) from the list or type a theme name.")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(pad, text="Menu name:").grid(row=1, column=0, sticky="w", pady=3)
        self.v_name = tk.StringVar()
        ttk.Entry(pad, textvariable=self.v_name, width=28).grid(row=1, column=1, padx=6)
        ttk.Label(pad, text="Icon:").grid(row=2, column=0, sticky="w", pady=3)
        self.v_theme = tk.StringVar(value=core.theme_label("ports"))
        ttk.Combobox(pad, textvariable=self.v_theme, values=[core.theme_label(k) for _t, k in core.FRIENDLY_THEMES], width=30).grid(row=2, column=1, padx=6)
        r = ttk.Frame(pad)
        r.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(r, text="Create", command=self.ok).pack(side="right")
        ttk.Button(r, text="Cancel", command=self.cancel).pack(side="right", padx=6)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        make_modal(self, app)

    def ok(self):
        name = self.v_name.get().strip()
        theme = core.theme_from_label(self.v_theme.get())
        if not name:
            messagebox.showerror("Name needed", "Type a name for the category.", parent=self)
            return
        if theme not in core.THEME_KEYS and not messagebox.askyesno(
                "Unknown icon", "'%s' does not exist in Art Book Next, so the category will have no logo. Continue?" % theme, parent=self):
            return
        self.done = True
        self.on_ok(name, theme)
        self.destroy()

    def cancel(self):
        if not self.done and self.on_cancel:
            self.on_cancel()
        self.destroy()


class CategoriesDialog(tk.Toplevel):
    """Rename the categories, change the icon, add or remove."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Customize categories")
        pad = ttk.Frame(self, padding=12)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, wraplength=560, justify="left", text=(
            "Each row is an entry on the handheld's home screen.\n"
            "• Name: what appears in the menu.\n"
            "• Icon: the look (logo and artwork) from the Art Book Next theme. Pick from the list or type a theme name.")
        ).pack(anchor="w", pady=(0, 8))
        self.grid_frame = ttk.Frame(pad)
        self.grid_frame.pack(anchor="w")
        self.items = [{"cat": dict(c), "name": tk.StringVar(value=c["name"]),
                       "theme": tk.StringVar(value=core.theme_label(c["theme"]))} for c in app.cfg["categories"]]
        self.render()
        r = ttk.Frame(pad)
        r.pack(fill="x", pady=(10, 0))
        ttk.Button(r, text="+ Add category", command=self.add).pack(side="left")
        ttk.Button(r, text="Save", command=self.save).pack(side="right")
        ttk.Button(r, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        make_modal(self, app)

    def render(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        ttk.Label(self.grid_frame, text="Menu name", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(self.grid_frame, text="Icon", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=4)
        labels = [core.theme_label(k) for _t, k in core.FRIENDLY_THEMES]
        for i, it in enumerate(self.items, start=1):
            ttk.Entry(self.grid_frame, textvariable=it["name"], width=22).grid(row=i, column=0, padx=4, pady=3)
            ttk.Combobox(self.grid_frame, textvariable=it["theme"], values=labels, width=30).grid(row=i, column=1, padx=4)
            ttk.Button(self.grid_frame, text="Remove", command=lambda idx=i - 1: self.remove(idx)).grid(row=i, column=2, padx=4)

    def add(self):
        self.items.append({"cat": None, "name": tk.StringVar(value="New"), "theme": tk.StringVar(value=core.theme_label("ports"))})
        self.render()

    def remove(self, idx):
        self.items.pop(idx)
        self.render()

    def save(self):
        cats, used = [], set()
        for it in self.items:
            name = it["name"].get().strip()
            theme = core.theme_from_label(it["theme"].get())
            if not name or not theme:
                messagebox.showerror("Something is missing", "Every row needs a name and an icon.", parent=self)
                return
            old = it["cat"]
            folder = old["folder"] if old else core.slug_folder(name, used | {c["folder"] for c in self.app.cfg["categories"]})
            used.add(folder)
            cats.append({"folder": folder, "name": name, "theme": theme, "platform": core.platform_for_theme(theme),
                         "manufacturer": old["manufacturer"] if old else "Various", "release": old["release"] if old else "2000"})
        unknown = [c["theme"] for c in cats if c["theme"] not in core.THEME_KEYS]
        if unknown and not messagebox.askyesno("Unknown icon", "These icons do not exist in Art Book Next:\n\n" + ", ".join(unknown) +
                                               "\n\nThe category will have no logo. Continue?", parent=self):
            return
        keep = {c["folder"] for c in cats}
        for st in self.app.cfg["games"].values():
            if st.get("cat") and st["cat"] not in keep:
                st["cat"] = ""
        self.app.cfg["categories"] = cats
        self.app.rebuild()
        self.app.save()
        self.destroy()


class OptionsDialog(tk.Toplevel):
    """Paths, metadata sources and the optional AI evaluator."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Options")
        pad = ttk.Frame(self, padding=12)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, wraplength=640, justify="left", text=(
            "You normally do not need to change anything here: PortMasterForwarder works everything out from the SD card folder. "
            "Fill a path only if your folders are organized differently.")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.vars = {}
        rows = (("share", "SD card folder (SHARE)", ""),
                ("ports_dir", "Games folder (ports)", "empty = roms\\ports"),
                ("roms_dir", "Categories folder (roms)", "empty = roms"),
                ("es_cfg_dir", "Menu systems folder", "empty = system\\configs\\emulationstation"))
        for i, (k, label, hint) in enumerate(rows, start=1):
            ttk.Label(pad, text=label).grid(row=i, column=0, sticky="w", pady=3)
            self.vars[k] = tk.StringVar(value=app.cfg[k])
            ttk.Entry(pad, textvariable=self.vars[k], width=48).grid(row=i, column=1, padx=6)
            ttk.Button(pad, text="Browse...", command=lambda v=self.vars[k]: self.browse(v)).grid(row=i, column=2)
            if hint:
                ttk.Label(pad, text=hint, foreground="#777").grid(row=i, column=3, sticky="w", padx=6)
        n = len(rows) + 1
        ttk.Label(pad, text="Max image width (px)").grid(row=n, column=0, sticky="w", pady=3)
        self.v_w = tk.StringVar(value=str(app.cfg["screenshot_max_width"]))
        ttk.Entry(pad, textvariable=self.v_w, width=8).grid(row=n, column=1, sticky="w", padx=6)
        self.v_mcpe = tk.BooleanVar(value=bool(app.cfg.get("mcpe_versions", True)))
        ttk.Checkbutton(pad, text="One shortcut per MCPE version", variable=self.v_mcpe).grid(row=n, column=2, columnspan=2, sticky="w", padx=12)
        ttk.Label(pad, text="Ignore these files").grid(row=n + 1, column=0, sticky="w", pady=3)
        self.v_ign = tk.StringVar(value=", ".join(app.cfg["ignore"]))
        ttk.Entry(pad, textvariable=self.v_ign, width=48).grid(row=n + 1, column=1, padx=6)
        ttk.Label(pad, text="comma separated", foreground="#777").grid(row=n + 1, column=3, sticky="w", padx=6)

        sf = ttk.LabelFrame(pad, text="Information sources (used in this order; each one only fills what is still missing)", padding=8)
        sf.grid(row=n + 2, column=0, columnspan=4, sticky="we", pady=(12, 0))
        self.v_src = {k: tk.BooleanVar(value=core.source_on(app.cfg, k)) for k in ("steam", "wikipedia", "rawg", "google")}
        ttk.Checkbutton(sf, text="Steam", variable=self.v_src["steam"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(sf, text="Wikipedia / Wikidata (no key needed; great for console games)", variable=self.v_src["wikipedia"]).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(sf, text="RAWG", variable=self.v_src["rawg"]).grid(row=2, column=0, sticky="w")
        ttk.Label(sf, text="free key (rawg.io/apidocs):").grid(row=2, column=1, sticky="e", padx=4)
        self.v_rawg = tk.StringVar(value=app.cfg["rawg_key"])
        ttk.Entry(sf, textvariable=self.v_rawg, width=34).grid(row=2, column=2, sticky="w")
        ttk.Checkbutton(sf, text="Google", variable=self.v_src["google"]).grid(row=3, column=0, sticky="w")
        ttk.Label(sf, text="API key:").grid(row=3, column=1, sticky="e", padx=4)
        self.v_gkey = tk.StringVar(value=app.cfg["google_key"])
        ttk.Entry(sf, textvariable=self.v_gkey, width=34).grid(row=3, column=2, sticky="w")
        ttk.Label(sf, text="Search engine ID (cx):").grid(row=4, column=1, sticky="e", padx=4)
        self.v_gcx = tk.StringVar(value=app.cfg["google_cx"])
        ttk.Entry(sf, textvariable=self.v_gcx, width=34).grid(row=4, column=2, sticky="w")
        ttk.Label(sf, foreground="#777", wraplength=600, justify="left", text=(
            "Google has no free keyless search. With a key and a 'Programmable Search Engine' (free up to 100 searches per day) "
            "the app tries to read a rating and short text from the results. All metadata is generated in English.")).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        af = ttk.LabelFrame(pad, text="AI evaluation (optional)", padding=8)
        af.grid(row=n + 3, column=0, columnspan=4, sticky="we", pady=(10, 0))
        self.v_ai = tk.BooleanVar(value=bool(app.cfg["ai_enabled"]))
        ttk.Checkbutton(af, text="Use AI to write the genre, gameplay description and rating", variable=self.v_ai).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(af, text="Anthropic API key:").grid(row=1, column=0, sticky="e", padx=4)
        self.v_akey = tk.StringVar(value=app.cfg["anthropic_key"])
        ttk.Entry(af, textvariable=self.v_akey, width=40, show="*").grid(row=1, column=1, sticky="w")
        ttk.Label(af, text="Model:").grid(row=2, column=0, sticky="e", padx=4)
        self.v_model = tk.StringVar(value=app.cfg["ai_model"])
        ttk.Entry(af, textvariable=self.v_model, width=40).grid(row=2, column=1, sticky="w")
        ttk.Label(af, foreground="#777", wraplength=600, justify="left", text=(
            "Without AI, descriptions are built only from gameplay sentences found in the sources and ratings are a balanced estimate from several "
            "scores. With AI, the collected source texts (never invented facts) are sent to the Anthropic API, which judges the game "
            "itself and may answer 'not enough information'. Results are always validated before they are saved.")).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        r = ttk.Frame(pad)
        r.grid(row=n + 4, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(r, text="Save", command=self.save).pack(side="right")
        ttk.Button(r, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        make_modal(self, app)

    def browse(self, var):
        d = filedialog.askdirectory(parent=self)
        if d:
            var.set(d)

    def save(self):
        cfg = self.app.cfg
        for k, v in self.vars.items():
            cfg[k] = v.get().strip()
        try:
            cfg["screenshot_max_width"] = max(160, int(self.v_w.get()))
        except ValueError:
            cfg["screenshot_max_width"] = 640
        cfg["mcpe_versions"] = bool(self.v_mcpe.get())
        cfg["ignore"] = [x.strip() for x in self.v_ign.get().split(",") if x.strip()]
        cfg["sources"] = {k: bool(v.get()) for k, v in self.v_src.items()}
        cfg["rawg_key"], cfg["google_key"], cfg["google_cx"] = self.v_rawg.get().strip(), self.v_gkey.get().strip(), self.v_gcx.get().strip()
        cfg["ai_enabled"] = bool(self.v_ai.get())
        cfg["anthropic_key"] = self.v_akey.get().strip()
        cfg["ai_model"] = self.v_model.get().strip() or pm.AI_DEFAULT_MODEL
        self.app.v_share.set(cfg["share"])
        self.app.save()
        self.app.reload_games()
        self.destroy()


class AboutDialog(tk.Toplevel):
    """Version, license and the compatibility notice."""

    def __init__(self, app):
        super().__init__(app)
        self.title("About %s" % core.APP_NAME)
        self.resizable(False, False)
        pad = ttk.Frame(self, padding=16)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="%s %s" % (core.APP_NAME, core.VERSION), font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(pad, text=core.TAGLINE, foreground="#666").pack(anchor="w", pady=(0, 10))
        ttk.Label(pad, wraplength=460, justify="left", text=(
            "Compatibility: %s Verified with %s. It may work with other EmulationStation-based firmware "
            "(Batocera, ROCKNIX...) but that has not been tested, so use it there at your own risk." % (core.COMPAT_NOTICE, core.TESTED_ON))).pack(anchor="w")
        ttk.Label(pad, wraplength=460, justify="left", text=(
            "\n%s\n\nFree and open-source software (%s). No warranty. Back up your SD card before using it; "
            "'Undo everything' removes what PortMasterForwarder created.\n\n"
            "Also not affiliated with or endorsed by Knulli, Batocera, Anbernic, Valve (Steam), Nintendo, Sony, "
            "Wikimedia, RAWG, Google or Anthropic. All product names belong to their owners." % (core.INDEPENDENCE_NOTICE, core.LICENSE_NAME))).pack(anchor="w")
        ttk.Button(pad, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        make_modal(self, app)


# ============================================================================ blocks
class FieldBlock(ttk.LabelFrame):
    """One metadata block: choose a source, press Fetch (or type your own value) and see it update live."""

    def __init__(self, parent, app, tag):
        super().__init__(parent, text=BLOCK_TITLES[tag], padding=6)
        self.app, self.tag = app, tag
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.v_src = tk.StringVar(value=SOURCE_LABELS["auto"])
        self.cb_src = ttk.Combobox(top, textvariable=self.v_src, state="readonly", width=15,
                                   values=[SOURCE_LABELS[s] for s in core.sources_for_field(tag)])
        self.cb_src.pack(side="left")
        self.cb_src.bind("<<ComboboxSelected>>", lambda _e: app.on_src_change(tag))
        ttk.Button(top, text="Fetch", width=7, command=lambda: app.fetch_block(tag)).pack(side="left", padx=4)
        ttk.Button(top, text="Reset", width=7, command=lambda: app.reset_block(tag)).pack(side="left")
        self.v_val = tk.StringVar()
        if tag == "desc":
            self.widget = tk.Text(self, height=5, wrap="word")
            self.widget.pack(fill="x", pady=(4, 0))
            self.widget.bind("<KeyRelease>", lambda _e: app.on_block_edit(tag))
        elif tag == "genre":
            self.widget = ttk.Combobox(self, textvariable=self.v_val, values=[NO_GENRE] + pm.GENRES, state="readonly", width=30)
            self.widget.pack(fill="x", pady=(4, 0))
            self.widget.bind("<<ComboboxSelected>>", lambda _e: app.on_block_edit(tag))
        else:
            self.widget = ttk.Entry(self, textvariable=self.v_val)
            self.widget.pack(fill="x", pady=(4, 0))
            trace_write(self.v_val, lambda: app.on_block_edit(tag))
        self.v_note = tk.StringVar()
        ttk.Label(self, textvariable=self.v_note, foreground="#777", wraplength=250).pack(anchor="w")

    def get(self):
        if self.tag == "desc":
            return self.widget.get("1.0", "end").strip()
        v = self.v_val.get().strip()
        return "" if v == NO_GENRE else v

    def set(self, text):
        if self.tag == "desc":
            self.widget.delete("1.0", "end")
            self.widget.insert("1.0", text or "")
        else:
            self.v_val.set(text if (text or self.tag != "genre") else NO_GENRE)

    def src_key(self):
        return LABEL_TO_SOURCE.get(self.v_src.get(), "auto")

    def set_src(self, key):
        self.v_src.set(SOURCE_LABELS.get(key, SOURCE_LABELS["auto"]))

    def note(self, text):
        self.v_note.set(text)


class ImageBlock(ttk.LabelFrame):
    """Image block: pick the source, fetch thumbnails right here and click one (or use a file from your PC)."""

    def __init__(self, parent, app):
        super().__init__(parent, text="Image (screenshot)", padding=6)
        self.app, self.refs = app, []
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.v_src = tk.StringVar(value=IMAGE_SOURCES[0][1])
        self.cb_src = ttk.Combobox(top, textvariable=self.v_src, state="readonly", width=30, values=[t for _k, t in IMAGE_SOURCES])
        self.cb_src.pack(side="left")
        self.cb_src.bind("<<ComboboxSelected>>", lambda _e: app.on_img_src_change())
        ttk.Button(top, text="Fetch", width=6, command=app.fetch_images).pack(side="left", padx=4)
        ttk.Button(top, text="Browse...", width=9, command=app.browse_local).pack(side="left")
        self.strip = ttk.Frame(self)
        self.strip.pack(fill="x", pady=(6, 0))
        self.v_note = tk.StringVar()
        ttk.Label(self, textvariable=self.v_note, foreground="#777", wraplength=480).pack(anchor="w")

    def mode(self):
        return next((k for k, t in IMAGE_SOURCES if t == self.v_src.get()), "auto")

    def set_mode(self, mode):
        self.v_src.set(next((t for k, t in IMAGE_SOURCES if k == mode), IMAGE_SOURCES[0][1]))

    def note(self, text):
        self.v_note.set(text)

    def show_thumbs(self, blobs, selected):
        """blobs: list of image bytes (or None). Click a thumbnail to choose it."""
        for w in self.strip.winfo_children():
            w.destroy()
        self.refs = []
        for i, raw in enumerate(blobs):
            if raw is None or not core.HAS_PIL:
                lbl = tk.Label(self.strip, text="#%d" % (i + 1), width=8, height=3, relief="ridge")
            else:
                try:
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    im.thumbnail((118, 70))
                    ph = ImageTk.PhotoImage(im)
                    self.refs.append(ph)
                    lbl = tk.Label(self.strip, image=ph, relief="solid" if i == selected else "flat", borderwidth=3)
                except Exception:  # noqa: BLE001 - a broken thumbnail must not break the screen
                    lbl = tk.Label(self.strip, text="#%d" % (i + 1), width=8, height=3, relief="ridge")
            lbl.grid(row=i // 4, column=i % 4, padx=3, pady=3)
            lbl.bind("<Button-1>", lambda _e, i=i: self.app.choose_shot(i))


class PreviewPanel(ttk.LabelFrame):
    """How the game will look: image, title, genre, rating, date and description (updates as you edit)."""

    def __init__(self, parent):
        super().__init__(parent, text="Preview", padding=8)
        self.photo = None
        self.img = tk.Label(self, text="no image", width=34, height=9, relief="groove", background="#e8e8e8")
        self.img.pack(fill="x")
        self.v_title, self.v_line1, self.v_line2, self.v_line3 = (tk.StringVar() for _ in range(4))
        ttk.Label(self, textvariable=self.v_title, font=("Segoe UI", 12, "bold"), wraplength=290).pack(anchor="w", pady=(8, 0))
        ttk.Label(self, textvariable=self.v_line1, foreground="#444").pack(anchor="w")
        ttk.Label(self, textvariable=self.v_line2, foreground="#444", wraplength=290).pack(anchor="w")
        ttk.Label(self, textvariable=self.v_line3, foreground="#444", wraplength=290).pack(anchor="w", pady=(0, 6))
        self.v_desc = tk.StringVar()
        ttk.Label(self, textvariable=self.v_desc, wraplength=290, justify="left").pack(anchor="w")

    def show(self, data, image_bytes=None):
        self.v_title.set(data["title"])
        self.v_line1.set(data["line1"])
        self.v_line2.set(data["line2"])
        self.v_line3.set(data["line3"])
        self.v_desc.set(data["desc"])
        if image_bytes and core.HAS_PIL:
            try:
                im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                im.thumbnail((290, 170))
                self.photo = ImageTk.PhotoImage(im)
                self.img.configure(image=self.photo, text="", width=im.width, height=im.height)
                return
            except Exception:  # noqa: BLE001
                pass
        self.photo = None
        self.img.configure(image="", text="no image yet", width=34, height=9)


# ============================================================================ main window
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s %s — %s" % (core.APP_NAME, core.VERSION, core.TAGLINE))
        self.geometry("1380x800")
        self.minsize(1120, 640)
        self._set_icon()
        self.cfg = core.load_config(CONFIG_FILE, core.legacy_config_dirs())
        self.q = queue.Queue()
        self.busy = False
        self.names = []
        self.rows = {}
        self.looking = set()
        self.log_lines = []
        self.log_txt = None
        self.cur = None
        self._loading = False
        self._wheel = None
        self.shot_urls, self.shot_blobs = [], []
        self.v_share = tk.StringVar(value=self.cfg["share"])
        self.v_status = tk.StringVar(value="Step 1: choose the SD card folder.")

        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=8)

        self._build_header()
        self._build_body()
        self._build_footer()
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._poll)

        if not self.cfg["share"]:
            found = core.find_share_candidates()
            if len(found) == 1:
                self.v_share.set(found[0])
        if self.v_share.get().strip():
            self.reload_games()

    def _set_icon(self):
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(str(core.resource_path("assets/icon.ico")))
            else:
                self.iconphoto(True, tk.PhotoImage(file=str(core.resource_path("assets/icon.png"))))
        except (tk.TclError, OSError):
            pass                      # a missing icon must never stop the app

    # ------------------------------------------------------------ infrastructure
    def log(self, msg):
        self.q.put(("log", str(msg)))

    def bg(self, fn, done=None, fail=None):
        def run():
            try:
                res, err = fn(), None
            except Exception as e:  # noqa: BLE001
                res, err = None, e
            self.q.put(("done", done, res, err, fail))
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "log":
                    self.log_lines.append(item[1])
                    self.v_status.set(item[1][:160])
                    if self.log_txt is not None:
                        try:
                            self.log_txt.configure(state="normal")
                            self.log_txt.insert("end", item[1] + "\n")
                            self.log_txt.see("end")
                            self.log_txt.configure(state="disabled")
                        except tk.TclError:
                            self.log_txt = None
                else:
                    _, done, res, err, fail = item
                    if err is not None:
                        self.log("ERROR: %s" % err)
                        if fail:
                            fail()
                    elif done:
                        done(res)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_wheel(self, e):
        if self._wheel is not None:
            self._wheel.yview_scroll(int(-e.delta / 120), "units")

    def save(self):
        try:
            core.save_config(self.cfg, CONFIG_FILE)
        except OSError as e:
            self.log("Could not save settings: %s" % e)

    def ready(self):
        ports = core.get_path(self.cfg, "ports_dir")
        if not ports or not ports.is_dir():
            messagebox.showinfo("Choose the SD card", "First choose the SD card folder (the one that contains 'roms' and 'system').")
            return False
        return True

    def set_busy(self, b):
        self.busy = b
        self.btn_apply.configure(state="disabled" if b else "normal")

    def state(self, n):
        return core.game_state(self.cfg, n)

    def store(self, n, st):
        self.cfg["games"][n] = st

    # ------------------------------------------------------------ screen
    def _build_header(self):
        t = ttk.Frame(self, padding=(10, 8, 10, 0))
        t.pack(fill="x")
        ttk.Label(t, text=core.APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(t, text="   " + core.TAGLINE, foreground="#666").pack(side="left")
        ttk.Button(t, text="About", command=lambda: AboutDialog(self)).pack(side="right")
        ttk.Label(t, text="Tested on Knulli only", foreground="#a05a00").pack(side="right", padx=10)

        f = ttk.Frame(self, padding=(10, 8, 10, 0))
        f.pack(fill="x")
        ttk.Label(f, text="1. SD card (the folder with 'roms' and 'system'):", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Entry(f, textvariable=self.v_share).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(f, text="Browse...", command=self.pick_share).pack(side="left")
        ttk.Button(f, text="Refresh list", command=self.reload_games).pack(side="left", padx=6)

        f = ttk.Frame(self, padding=(10, 8, 10, 0))
        f.pack(fill="x")
        ttk.Label(f, text="2. Pick a category for each game, then click a game to edit its metadata.", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.meta_cb = ttk.Combobox(f, state="readonly", width=28, values=[t for t, _v in META_GLOBAL])
        self.meta_cb.set(next((t for t, v in META_GLOBAL if v == self.cfg["meta_global"]), META_GLOBAL[0][0]))
        self.meta_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_meta_global())
        self.meta_cb.pack(side="right")
        ttk.Label(f, text="Blocks set to Auto:").pack(side="right", padx=6)

    def _scroll_area(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind("<Enter>", lambda _e: setattr(self, "_wheel", canvas))
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        return canvas, inner

    def _build_body(self):
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        left, mid, right = ttk.Frame(pw), ttk.Frame(pw), ttk.Frame(pw)
        pw.add(left, weight=3)
        pw.add(mid, weight=4)
        pw.add(right, weight=2)

        bar = ttk.Frame(left)
        bar.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(bar, text="Put all games without a category in").pack(side="left")
        self.bulk = ttk.Combobox(bar, state="readonly", width=14)
        self.bulk.pack(side="left", padx=4)
        ttk.Button(bar, text="Apply", command=self.bulk_apply).pack(side="left")
        _c, self.inner = self._scroll_area(left)

        _c, edit = self._scroll_area(mid)
        self._build_editor(edit)

        self.preview = PreviewPanel(right)
        self.preview.pack(fill="both", expand=True, padx=(8, 0))

    def _build_editor(self, parent):
        parent = ttk.Frame(parent, padding=(8, 0, 4, 8))
        parent.pack(fill="both", expand=True)
        self.lbl_game = ttk.Label(parent, text="Select a game on the left", font=("Segoe UI", 12, "bold"))
        self.lbl_game.pack(anchor="w")
        self.v_editor_status = tk.StringVar()
        ttk.Label(parent, textvariable=self.v_editor_status, foreground="#555", wraplength=560).pack(anchor="w", pady=(0, 6))

        pf = ttk.LabelFrame(parent, text="Presets (set the source of every block at once)", padding=6)
        pf.pack(fill="x", pady=3)
        self.preset_cb = ttk.Combobox(pf, state="readonly", width=24)
        self.preset_cb.pack(side="left")
        ttk.Button(pf, text="This game", command=self.preset_this).pack(side="left", padx=4)
        ttk.Button(pf, text="All games", command=self.preset_all).pack(side="left")
        ttk.Button(pf, text="Save current as...", command=self.save_preset).pack(side="left", padx=4)
        self.refresh_presets()

        sf = ttk.LabelFrame(parent, text="Which game is this? (name used to search the sources)", padding=6)
        sf.pack(fill="x", pady=3)
        r = ttk.Frame(sf)
        r.pack(fill="x")
        self.v_term = tk.StringVar()
        ttk.Entry(r, textvariable=self.v_term).pack(side="left", fill="x", expand=True)
        trace_write(self.v_term, self.on_term_edit)
        ttk.Button(r, text="Search Steam...", command=self.search_steam).pack(side="left", padx=4)
        ttk.Button(r, text="Not on Steam", command=self.no_steam).pack(side="left")
        self.v_steam = tk.StringVar()
        ttk.Label(sf, textvariable=self.v_steam, foreground="#555").pack(anchor="w", pady=(4, 0))

        grid = ttk.Frame(parent)
        grid.pack(fill="x", pady=3)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.blocks = {tag: FieldBlock(grid, self, tag) for tag in core.BLOCK_FIELDS}
        self.blocks["genre"].grid(row=0, column=0, sticky="we", padx=(0, 4), pady=3)
        self.blocks["rating"].grid(row=0, column=1, sticky="we", padx=(4, 0), pady=3)
        self.blocks["releasedate"].grid(row=1, column=0, sticky="we", padx=(0, 4), pady=3)
        self.blocks["developer"].grid(row=1, column=1, sticky="we", padx=(4, 0), pady=3)
        self.blocks["publisher"].grid(row=2, column=0, sticky="we", padx=(0, 4), pady=3)
        self.blocks["desc"].grid(row=3, column=0, columnspan=2, sticky="we", pady=3)
        self.img_block = ImageBlock(parent, self)
        self.img_block.pack(fill="x", pady=3)
        ttk.Button(parent, text="Fetch all blocks", command=self.fetch_all).pack(anchor="e", pady=6)

    def _build_footer(self):
        f = ttk.Frame(self, padding=10)
        f.pack(fill="x")
        ttk.Button(f, text="Customize categories...", command=lambda: CategoriesDialog(self)).pack(side="left")
        ttk.Button(f, text="Options...", command=lambda: OptionsDialog(self)).pack(side="left", padx=6)
        ttk.Button(f, text="Undo everything...", command=self.undo).pack(side="left")
        ttk.Button(f, text="View details", command=self.show_log).pack(side="left", padx=6)
        self.btn_apply = ttk.Button(f, text="3. APPLY", style="Big.TButton", command=self.apply)
        self.btn_apply.pack(side="right")
        ttk.Label(self, textvariable=self.v_status, anchor="w", foreground="#444").pack(fill="x", padx=12, pady=(0, 2))
        ttk.Label(self, text=core.INDEPENDENCE_SHORT, anchor="e", foreground="#888").pack(fill="x", padx=12, pady=(0, 8))

    def show_log(self):
        win = tk.Toplevel(self)
        win.title("Details")
        win.geometry("760x380")
        self.log_txt = scrolledtext.ScrolledText(win, font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True)
        self.log_txt.insert("end", "\n".join(self.log_lines) + "\n")
        self.log_txt.configure(state="disabled")

    # ------------------------------------------------------------ game list
    def cat_names(self):
        return [c["name"] for c in self.cfg["categories"]]

    def cat_values(self):
        return [NONE_LABEL] + self.cat_names() + [NEW_CAT_LABEL]

    def refresh_category_values(self):
        self.bulk.configure(values=self.cat_names())
        for row in self.rows.values():
            row["cb"].configure(values=self.cat_values())

    def rebuild(self):
        self.bulk.configure(values=self.cat_names())
        if self.cat_names() and not self.bulk.get():
            self.bulk.set(self.cat_names()[min(2, len(self.cat_names()) - 1)])
        for w in self.inner.winfo_children():
            w.destroy()
        self.inner.columnconfigure(0, weight=1)
        self.rows = {}
        if not self.names:
            self.lbl_game.configure(text="No games found")
        for i, n in enumerate(self.names):
            row = tk.Frame(self.inner, background=NORMAL_BG)
            row.grid(row=i, column=0, sticky="we", pady=1)
            name = tk.Label(row, text=n[:-3], anchor="w", width=30, background=NORMAL_BG)
            name.pack(side="left", padx=(4, 2))
            cb = ttk.Combobox(row, state="readonly", width=16, values=self.cat_values())
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda _e, n=n: self.on_cat(n))
            badge = tk.Label(row, text="", anchor="w", width=20, foreground="#555", background=NORMAL_BG)
            badge.pack(side="left")
            for w in (row, name, badge):
                w.bind("<Button-1>", lambda _e, n=n: self.select_game(n))
            self.rows[n] = {"frame": row, "name": name, "cb": cb, "badge": badge}
            self.refresh_row(n)
        if self.cur not in self.rows:
            self.cur = None
        if self.cur:
            self.select_game(self.cur)
        elif self.names:
            self.select_game(self.names[0])

    def pinned_tags(self, st):
        return [t for t in core.BLOCK_FIELDS if core.manual_value(st, t)]

    def badge_text(self, n):
        st = self.state(n)
        if not st["cat"]:
            return "—"
        have = core.existing_meta(self.cfg, n)
        miss = [t for t in core.GAMELIST_META_TAGS if t not in have]
        parts = ["missing %d" % len(miss) if miss else "complete"]
        pins = self.pinned_tags(st)
        if pins:
            parts.append("%d edited" % len(pins))
        return " · ".join(parts)

    def status_text(self, n):
        st = self.state(n)
        if not st["cat"]:
            return "—"
        parts = []
        if st["steam_id"]:
            parts.append("Steam: %s" % (st["steam_name"] or st["steam_id"]))
        elif st["steam_checked"]:
            parts.append("not on Steam")
        elif n in self.looking:
            parts.append("searching Steam...")
        mode = core.effective_meta_mode(self.cfg, st)
        have = core.existing_meta(self.cfg, n)
        miss = [TAG_LABELS[t] for t in core.GAMELIST_META_TAGS if t not in have]
        if mode == "keep":
            parts.append("metadata: keep")
        elif mode == "replace":
            parts.append("metadata: replace")
        elif not miss:
            parts.append("metadata complete (kept)")
        else:
            parts.append("missing: " + ", ".join(miss))
        if "genre" in core.nonstandard_fields(self.cfg, n):
            parts.append("non-standard genre")
        pins = self.pinned_tags(st)
        if pins:
            parts.append("edited: " + ", ".join(TAG_LABELS[t] for t in pins))
        sm = st["shot_mode"]
        if sm == "auto":
            parts.append("image kept" if "image" in have else "image automatic")
        else:
            parts.append({"web": "image #%d (Steam)" % (int(st["shot_idx"]) + 1), "rawg": "image (RAWG)", "local": "image from PC",
                          "none": "image unchanged"}[sm])
        return "  ·  ".join(parts)

    def refresh_row(self, n):
        row = self.rows.get(n)
        if not row:
            return
        st = self.state(n)
        cat = core.cat_by_folder(self.cfg, st["cat"])
        row["cb"].set(cat["name"] if cat else NONE_LABEL)
        row["badge"].configure(text=self.badge_text(n))
        bg = SELECTED_BG if n == self.cur else NORMAL_BG
        for key in ("frame", "name", "badge"):
            row[key].configure(background=bg)

    def reload_games(self):
        self.cfg["share"] = self.v_share.get().strip()
        ports = core.get_path(self.cfg, "ports_dir")
        self.names = []
        if ports and ports.is_dir():
            self.names = core.list_games(self.cfg)
            for n, folder in core.scan_existing(self.cfg).items():
                if n in self.names:
                    st = self.cfg["games"].setdefault(n, {})
                    if not st.get("cat"):
                        st["cat"] = folder
            self.v_status.set("%d game(s) found. Step 2: choose a category for each one." % len(self.names))
        else:
            self.v_status.set("Could not find the games folder at: %s" % ports)
        self.rebuild()
        self.save()

    def pick_share(self):
        d = filedialog.askdirectory(title="Choose the SD card folder (the one that contains 'roms' and 'system')")
        if d:
            self.v_share.set(d)
            self.reload_games()

    def on_meta_global(self):
        self.cfg["meta_global"] = next((v for t, v in META_GLOBAL if t == self.meta_cb.get()), "fill")
        for n in self.names:
            self.refresh_row(n)
        if self.cur:
            self.v_editor_status.set(self.status_text(self.cur))
        self.save()

    # ---- categories
    def on_cat(self, n):
        i = self.rows[n]["cb"].current()
        if i == len(self.cat_names()) + 1:      # "+ New category..."
            self.new_category(n)
            return
        st = self.state(n)
        st["cat"] = self.cfg["categories"][i - 1]["folder"] if i > 0 else ""
        self.store(n, st)
        self.refresh_row(n)
        self.lookup(n)
        if n == self.cur:
            self.v_editor_status.set(self.status_text(n))
        self.save()

    def new_category(self, n):
        def ok(name, theme):
            cat = core.add_category(self.cfg, name, theme)
            self.refresh_category_values()
            st = self.state(n)
            st["cat"] = cat["folder"]
            self.store(n, st)
            self.refresh_row(n)
            self.lookup(n)
            self.log("New category '%s' created (folder %s). It appears in the menu after APPLY." % (cat["name"], cat["folder"]))
            self.save()
        NewCategoryDialog(self, ok, on_cancel=lambda: self.refresh_row(n))

    def bulk_apply(self):
        i = self.bulk.current()
        if i < 0:
            return
        folder = self.cfg["categories"][i]["folder"]
        for n in self.names:
            st = self.state(n)
            if not st["cat"]:
                st["cat"] = folder
                self.store(n, st)
                self.refresh_row(n)
                self.lookup(n)
        self.save()

    def lookup(self, n):
        """Look the game up on Steam in the background (only if not searched yet)."""
        st = self.state(n)
        if not st["cat"] or st["steam_id"] or st["steam_checked"] or n in self.looking or not core.source_on(self.cfg, "steam"):
            return
        term = st["steam_term"] or core.default_term(n)
        self.looking.add(n)
        self.refresh_row(n)

        def done(m):
            self.looking.discard(n)
            s2 = self.state(n)
            s2["steam_checked"] = True
            if m and not s2["steam_id"]:
                s2["steam_id"], s2["steam_name"] = m
            self.store(n, s2)
            self.refresh_row(n)
            if n == self.cur:
                self.v_steam.set(self.steam_text(s2))
                self.v_editor_status.set(self.status_text(n))
            self.save()

        def fail():
            self.looking.discard(n)
            self.refresh_row(n)
        self.bg(lambda: core.steam_auto_match(term), done, fail)

    # ------------------------------------------------------------ editor (blocks + preview)
    def steam_text(self, st):
        if st["steam_id"]:
            return "Steam match: %s" % (st["steam_name"] or st["steam_id"])
        return "Not on Steam (other sources still work)" if st["steam_checked"] else "Not searched on Steam yet"

    def select_game(self, n):
        prev = self.cur
        self.cur = n
        if prev in self.rows:
            self.refresh_row(prev)
        self.refresh_row(n)
        self.shot_urls, self.shot_blobs = [], []
        self.load_editor(n)

    def block_note(self, tag, st, entry):
        src = (st.get("src") or {}).get(tag, "auto")
        if core.manual_value(st, tag):
            return "your value (pinned) - APPLY writes it"
        if src == "keep":
            return "kept as it is"
        if entry.get(tag):
            return "current value in the game list"
        return "empty - %s will fill it on APPLY (or press Fetch)" % SOURCE_LABELS.get(src, "the source")

    def load_editor(self, n):
        self._loading = True
        try:
            st = self.state(n)
            entry = core.existing_entry(self.cfg, n)
            self.lbl_game.configure(text=n[:-3])
            for tag, blk in self.blocks.items():
                shown = core.manual_value(st, tag) or entry.get(tag, "")
                blk.set(core.display_value(tag, shown))
                blk.set_src((st.get("src") or {}).get(tag, "auto"))
                blk.note(self.block_note(tag, st, entry))
            self.v_term.set(st["steam_term"] or core.default_term(n))
            self.v_steam.set(self.steam_text(st))
            self.img_block.set_mode(st["shot_mode"])
            self.img_block.show_thumbs([], 0)
            self.img_block.note(self.image_note(st))
            self.v_editor_status.set(self.status_text(n))
        finally:
            self._loading = False
        self.refresh_preview()

    def image_note(self, st):
        m = st["shot_mode"]
        return {"auto": "Keeps the image the game already has; otherwise the first one found online.",
                "web": "Steam image #%d is used on APPLY." % (int(st["shot_idx"]) + 1),
                "rawg": "The RAWG image is used on APPLY.",
                "local": "From your computer: %s" % st["shot_local"],
                "none": "The image is not changed."}[m]

    def refresh_preview(self):
        n = self.cur
        if not n:
            return
        st = self.state(n)
        entry = core.existing_entry(self.cfg, n)
        src_map = st.get("src") or {}

        def val(tag):
            v = core.manual_value(st, tag) or entry.get(tag, "")
            if v:
                return core.display_value(tag, v)
            return "" if src_map.get(tag, "auto") == "keep" else None     # None = will be fetched on APPLY

        def show(tag, label=None):
            v = val(tag)
            return v if v else ("(fetched on APPLY)" if v is None else "—")
        rating = val("rating")
        rating_line = "Rating: %s / 10" % rating if rating else "Rating: %s" % show("rating")
        data = {
            "title": entry.get("name") or n[:-3],
            "line1": "%s   ·   %s" % (show("genre"), show("releasedate")),
            "line2": rating_line,
            "line3": "%s  /  %s" % (show("developer"), show("publisher")),
            "desc": show("desc"),
        }
        self.preview.show(data, self.preview_image_bytes(n, st))

    def preview_image_bytes(self, n, st):
        mode = st["shot_mode"]
        try:
            if mode == "local" and st["shot_local"]:
                return Path(st["shot_local"]).read_bytes()
            if mode in ("web", "rawg") and self.shot_blobs:
                i = min(int(st["shot_idx"]), len(self.shot_blobs) - 1) if mode == "web" else 0
                if self.shot_blobs[i]:
                    return self.shot_blobs[i]
            p = core.existing_image_path(self.cfg, n)
            return p.read_bytes() if p else None
        except OSError:
            return None

    # ---- block events
    def on_block_edit(self, tag):
        """The user typed / picked a value: pin it (unless it equals what the game list already has)."""
        if self._loading or not self.cur:
            return
        n = self.cur
        st = self.state(n)
        blk = self.blocks[tag]
        text = blk.get()
        manual = dict(st.get("manual") or {})
        base = core.existing_entry(self.cfg, n).get(tag, "")
        if not text:
            manual.pop(tag, None)
            blk.note("empty - the source will fill it on APPLY")
        else:
            val = core.normalize_manual(tag, text)
            if val is None:
                blk.note({"rating": "not valid - use a number from 0 to 10", "releasedate": "not valid - use YYYY-MM-DD"}.get(tag, "not valid"))
                return
            if val == base:
                manual.pop(tag, None)
                blk.note("current value in the game list")
            else:
                manual[tag] = val
                blk.note("your value (pinned) - APPLY writes it")
        st["manual"] = manual
        if tag in ("desc", "rating", "genre"):
            st[tag] = ""
        self.store(n, st)
        self.refresh_row(n)
        self.v_editor_status.set(self.status_text(n))
        self.refresh_preview()
        self.save()

    def on_src_change(self, tag):
        if self._loading or not self.cur:
            return
        n = self.cur
        st = self.state(n)
        src = dict(st.get("src") or {})
        src[tag] = self.blocks[tag].src_key()
        st["src"] = src
        self.store(n, st)
        self.blocks[tag].note(self.block_note(tag, st, core.existing_entry(self.cfg, n)))
        self.refresh_preview()
        self.save()

    def reset_block(self, tag):
        """Drop your value and go back to what the game list has (and to Auto)."""
        if not self.cur:
            return
        n = self.cur
        st = self.state(n)
        manual = dict(st.get("manual") or {})
        manual.pop(tag, None)
        src = dict(st.get("src") or {})
        src.pop(tag, None)
        st["manual"], st["src"] = manual, src
        if tag in ("desc", "rating", "genre"):
            st[tag] = ""
        self.store(n, st)
        self.load_editor(n)
        self.refresh_row(n)
        self.save()

    def _pin(self, n, tag, es_value, source_label):
        st = self.state(n)
        manual = dict(st.get("manual") or {})
        manual[tag] = es_value
        st["manual"] = manual
        if tag in ("desc", "rating", "genre"):
            st[tag] = ""
        self.store(n, st)
        self.refresh_row(n)
        if n == self.cur:
            self._loading = True
            try:
                self.blocks[tag].set(core.display_value(tag, es_value))
                self.blocks[tag].note("fetched from %s (pinned) - APPLY writes it" % source_label)
            finally:
                self._loading = False
            self.v_editor_status.set(self.status_text(n))
            self.refresh_preview()
        self.save()

    def fetch_block(self, tag):
        self._fetch([tag])

    def fetch_all(self):
        self._fetch([t for t in core.BLOCK_FIELDS if self.blocks[t].src_key() != "keep"])

    def _fetch(self, tags):
        if not self.cur or not tags:
            return
        n = self.cur
        keys = {t: self.blocks[t].src_key() for t in tags}
        keys = {t: k for t, k in keys.items() if k != "keep"}
        if not keys:
            self.blocks[tags[0]].note("source is 'Keep current' - nothing to fetch")
            return
        cfg = json.loads(json.dumps(self.cfg))
        for t in keys:
            self.blocks[t].note("fetching...")

        def work():
            out, upd = {}, {}
            for t, k in keys.items():
                v, u = core.fetch_field(cfg, n, t, k, self.log)
                out[t] = v
                if u:
                    upd.update(u)
                    cfg["games"][n] = dict(core.game_state(cfg, n), **u)     # next blocks reuse the Steam match
            return out, upd

        def done(res):
            out, upd = res
            if upd:
                st = self.state(n)
                st.update(upd)
                self.store(n, st)
                if n == self.cur:
                    self.v_steam.set(self.steam_text(st))
            for t, v in out.items():
                label = SOURCE_LABELS[keys[t]]
                if v:
                    self._pin(n, t, v, label)
                elif n == self.cur:
                    self.blocks[t].note("nothing reliable found from %s" % label)
            self.refresh_row(n)

        def fail():
            for t in keys:
                if n == self.cur:
                    self.blocks[t].note("fetch failed - see 'View details'")
        self.bg(work, done, fail)

    # ---- Steam match
    def on_term_edit(self):
        if self._loading or not self.cur:
            return
        st = self.state(self.cur)
        term = self.v_term.get().strip()
        if term != st["steam_term"]:
            st["steam_term"] = term
            if not st["steam_id"]:
                st["steam_checked"] = False
            self.store(self.cur, st)
            self.save()

    def search_steam(self):
        if not self.cur:
            return
        n = self.cur

        def chosen(sid, name):
            st = self.state(n)
            st.update(steam_id=sid, steam_name=name, steam_checked=True)
            self.store(n, st)
            self.v_steam.set(self.steam_text(st))
            self.refresh_row(n)
            self.v_editor_status.set(self.status_text(n))
            self.save()
        SteamSearchDialog(self, self, self.v_term.get().strip() or core.default_term(n), chosen)

    def no_steam(self):
        if not self.cur:
            return
        n = self.cur
        st = self.state(n)
        st.update(steam_id="", steam_name="", steam_checked=True)
        if st["shot_mode"] == "web":
            st["shot_mode"] = "auto"
            self.img_block.set_mode("auto")
        self.store(n, st)
        self.v_steam.set(self.steam_text(st))
        self.refresh_row(n)
        self.v_editor_status.set(self.status_text(n))
        self.save()

    # ---- image block
    def on_img_src_change(self):
        if self._loading or not self.cur:
            return
        n = self.cur
        st = self.state(n)
        st["shot_mode"] = self.img_block.mode()
        self.store(n, st)
        self.img_block.note(self.image_note(st))
        self.refresh_row(n)
        self.refresh_preview()
        self.save()

    def fetch_images(self):
        if not self.cur:
            return
        mode = self.img_block.mode()
        if mode not in ("web", "rawg"):
            self.img_block.note("Pick Steam or RAWG as the source to see thumbnails, or use Browse... for a file from your computer.")
            return
        n = self.cur
        source = "steam" if mode == "web" else "rawg"
        cfg = json.loads(json.dumps(self.cfg))
        self.img_block.note("fetching thumbnails...")

        def work():
            shots, upd = core.fetch_image_options(cfg, n, source, self.log)
            blobs = []
            for thumb, _full in shots[:8]:
                try:
                    blobs.append(core.http_get(thumb))
                except Exception:  # noqa: BLE001
                    blobs.append(None)
            return shots, blobs, upd

        def done(res):
            shots, blobs, upd = res
            st = self.state(n)
            st.update(upd)
            self.store(n, st)
            if n != self.cur:
                return
            self.shot_urls, self.shot_blobs = shots, blobs
            if not shots:
                self.img_block.note("no images found from %s" % ("Steam" if mode == "web" else "RAWG"))
                return
            self.img_block.show_thumbs(blobs, min(int(st["shot_idx"]), len(blobs) - 1) if mode == "web" else 0)
            self.img_block.note("Click a thumbnail to choose it.")
            self.v_steam.set(self.steam_text(st))
            self.refresh_preview()
        self.bg(work, done, fail=lambda: self.img_block.note("fetch failed - see 'View details'"))

    def choose_shot(self, i):
        if not self.cur:
            return
        n = self.cur
        st = self.state(n)
        st["shot_idx"] = i
        self.store(n, st)
        self.img_block.show_thumbs(self.shot_blobs, i)
        self.img_block.note(self.image_note(st))
        self.refresh_row(n)
        self.refresh_preview()
        self.save()

    def browse_local(self):
        if not self.cur:
            return
        f = filedialog.askopenfilename(title="Choose an image from your computer",
                                       filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if f:
            n = self.cur
            st = self.state(n)
            st.update(shot_mode="local", shot_local=f)
            self.store(n, st)
            self.img_block.set_mode("local")
            self.img_block.note(self.image_note(st))
            self.refresh_row(n)
            self.refresh_preview()
            self.save()

    # ---- presets
    def refresh_presets(self):
        names = list(core.all_presets(self.cfg))
        self.preset_cb.configure(values=names)
        if not self.preset_cb.get():
            self.preset_cb.set(names[0])

    def preset_this(self):
        preset = core.all_presets(self.cfg).get(self.preset_cb.get())
        if not preset or not self.cur:
            return
        n = self.cur
        self.store(n, core.apply_preset(self.state(n), preset))
        self.load_editor(n)
        self.refresh_row(n)
        self.log("[%s] preset '%s' applied" % (n, self.preset_cb.get()))
        self.save()

    def preset_all(self):
        name = self.preset_cb.get()
        preset = core.all_presets(self.cfg).get(name)
        if not preset or not self.names:
            return
        if not messagebox.askyesno("Apply preset to all games", "Set every block of all %d games to the preset '%s'?\n\n"
                                   "Values you typed or fetched are cleared for the blocks the preset defines." % (len(self.names), name)):
            return
        for n in self.names:
            self.store(n, core.apply_preset(self.state(n), preset))
            self.refresh_row(n)
        if self.cur:
            self.load_editor(self.cur)
        self.log("Preset '%s' applied to %d game(s)" % (name, len(self.names)))
        self.save()

    def save_preset(self):
        if not self.cur:
            return
        name = simpledialog.askstring("Save preset", "Name for this preset (the sources of the current blocks):", parent=self)
        name = (name or "").strip()
        if not name:
            return
        if name in core.BUILTIN_PRESETS:
            messagebox.showerror("Name taken", "'%s' is a built-in preset. Choose another name." % name)
            return
        self.cfg.setdefault("presets", {})[name] = core.preset_from_state(self.state(self.cur))
        self.refresh_presets()
        self.preset_cb.set(name)
        self.save()

    # ------------------------------------------------------------ big actions
    def run_job(self, fn, label, done):
        self.set_busy(True)
        self.log("--- %s ---" % label)
        cfg = json.loads(json.dumps(self.cfg))
        self.bg(lambda: fn(cfg), lambda res: (self.set_busy(False), done(res)), fail=lambda: self.set_busy(False))

    def apply(self):
        if self.busy or not self.ready():
            return
        if not any(s.get("cat") for s in self.cfg["games"].values()):
            messagebox.showinfo("Nothing to apply", "Choose a category for at least one game (step 2).")
            return
        over = False
        foreign = core.foreign_cfgs(self.cfg)
        if foreign:
            over = messagebox.askyesno("Replace old system files?", "These system files already exist on the card:\n\n" +
                                       "\n".join(p.name for p in foreign) + "\n\nReplace them with PortMasterForwarder's? (Recommended)")
        self.save()

        def job(cfg):
            core.install_systems(cfg, over, self.log)
            return core.apply_all(cfg, self.log)

        def finished(res):
            for n, u in (res or {}).items():
                if u:
                    st = self.state(n)
                    st.update(u)
                    self.store(n, st)
                    # values written to the game list are no longer "pending": the list itself holds them now
            for n in self.names:
                st = self.state(n)
                if st.get("manual"):
                    st["manual"] = {}
                    for t in ("desc", "rating", "genre"):
                        st[t] = ""
                    self.store(n, st)
                self.refresh_row(n)
            if self.cur:
                self.load_editor(self.cur)
            self.save()
            messagebox.showinfo("Done!", "Everything was written to the card.\n\n1) Eject the card safely.\n"
                                         "2) On Knulli: Menu > Quit > Restart System.\n\n"
                                         "(See the 'View details' button for the full log.)")
        self.run_job(job, "Applying", finished)

    def undo(self):
        if not self.ready():
            return
        if messagebox.askyesno("Undo everything", "This deletes from the card:\n• the shortcuts created by PortMasterForwarder\n• the systems "
                                                  "(GameCube, PC...) from the menu\n\nYour games in roms\\ports, images and gamelists "
                                                  "are NOT deleted. Continue?"):
            core.remove_wrappers(self.cfg, self.log)
            core.remove_systems(self.cfg, True, self.log)
            messagebox.showinfo("Done", "Undone. Restart Knulli so the menu updates.")

    def on_close(self):
        self.save()
        self.destroy()


def run_self_test():
    """Headless check used by CI on the built .exe (no window is opened). Returns 0 when everything is in place."""
    problems = []
    for rel in ("assets/icon.ico", "assets/icon.png", "assets/logo.png"):
        if not core.resource_path(rel).exists():
            problems.append("missing resource: " + rel)
    if not core.HAS_PIL:
        problems.append("Pillow is not available")
    if pm.normalize_genre(["Platform game"]) != pm.PLATFORMER:
        problems.append("genre normalization is broken")
    if core.config_path().name != core.CONFIG_NAME:
        problems.append("unexpected config path")
    if len(core.THEME_KEYS) < 100:
        problems.append("theme key list is incomplete")
    for p in problems:
        _say("SELF-TEST FAILED: " + p)
    if not problems:
        _say("self-test OK (%s %s)" % (core.APP_NAME, core.VERSION))
    return 1 if problems else 0


def _say(text):
    if sys.stdout:                    # windowed executables have no console
        print(text)


def main(argv=None):
    """Entry point used by `python -m portmasterforwarder`, the console script and the .exe."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        _say("%s %s" % (core.APP_NAME, core.VERSION))
        return 0
    if "--self-test" in argv:
        return run_self_test()
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
