"""PortMasterForwarder - gamepad GUI (pygame, 8-bit CRT look, blue theme) for running directly on the handheld (Knulli)."""
import os
import sys
import threading
import traceback
import urllib.request

import pygame

from . import core, __version__

SRC = {"auto": "Auto", "steam": "Steam", "wikipedia": "Wikipedia", "rawg": "RAWG", "google": "Google", "ai": "AI", "keep": "Keep"}
TITLES = {"genre": "Genre", "rating": "Rating 0-10", "desc": "Description", "releasedate": "Release date",
          "developer": "Developer", "publisher": "Publisher"}
IMG_MODES = [("auto", "Auto"), ("web", "Steam"), ("rawg", "RAWG"), ("none", "None")]

# --- 8-bit phosphor palette
# colours taken from the logo: sky/royal blues + navy, orange accent
BG, PANEL = (0, 20, 52), (0, 32, 80)
FG, DIM, ACC, WARN = (96, 200, 240), (56, 128, 184), (240, 144, 16), (240, 96, 16)
SEL, EDGE = (16, 100, 192), (48, 176, 224)

KEYS = ["ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "abcdefghijklm", "nopqrstuvwxyz", "0123456789 .-_:'&!?",
        "áàâãäéêíóôõúüçÁÉÍÓÚÇñ"]
MAXTXT = 60

# SDL controller button -> action (east button = accept, like EmulationStation)
CBTN = {"a": "back", "b": "accept", "x": "y", "y": "x", "leftshoulder": "l", "rightshoulder": "r", "start": "start", "back": "select",
        "dpup": "up", "dpdown": "down", "dpleft": "left", "dpright": "right"}
JBTN = {0: "back", 1: "accept", 2: "y", 3: "x", 4: "l", 5: "r", 6: "select", 7: "start"}  # raw fallback
KEYMAP = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_RETURN: "accept",
          pygame.K_z: "accept", pygame.K_x: "back", pygame.K_ESCAPE: "back", pygame.K_a: "x", pygame.K_s: "y", pygame.K_q: "l",
          pygame.K_w: "r", pygame.K_TAB: "start", pygame.K_BACKSPACE: "select"}
DIRS = ("up", "down", "left", "right")


def make_crt(W, H):
    """Scanlines + vignette baked once into one translucent overlay."""
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(0, H, 3):
        pygame.draw.line(ov, (0, 0, 0, 80), (0, y), (W, y))
    small = pygame.Surface((32, 24), pygame.SRCALPHA)
    for x in range(32):
        for y in range(24):
            d = ((x - 15.5) / 16.0) ** 2 + ((y - 11.5) / 12.0) ** 2
            small.set_at((x, y), (0, 0, 0, int(min(170, max(0, d - 0.5) * 200))))
    ov.blit(pygame.transform.smoothscale(small, (W, H)), (0, 0))
    return ov


class App:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.pads = []
        for i in range(pygame.joystick.get_count()):
            try:
                p = pygame.joystick.Joystick(i)
                p.init()
                self.pads.append(p)
            except pygame.error:
                pass
        self.ctrl = []
        try:
            from pygame._sdl2 import controller as ctl
            ctl.init()
            self.ctrl = [ctl.Controller(i) for i in range(ctl.get_count()) if ctl.is_controller(i)]
        except Exception:
            self.ctrl = []
        windowed = bool(os.environ.get("PMF_WINDOW")) or sys.platform in ("win32", "darwin")
        if windowed:
            self.screen = pygame.display.set_mode((640, 480))
        else:
            info = pygame.display.Info()
            size = (info.current_w, info.current_h) if info.current_w > 0 else (0, 0)
            self.screen = pygame.display.set_mode(size, pygame.FULLSCREEN)
        pygame.display.set_caption("PortMasterForwarder")
        pygame.mouse.set_visible(False)
        self.W, self.H = self.screen.get_size()
        u = max(14, self.H // 24)                     # font sizes unchanged from the previous look
        self.f, self.fs, self.fb = pygame.font.Font(None, u * 2), pygame.font.Font(None, int(u * 1.6)), pygame.font.Font(None, int(u * 2.6))
        self.lh = int(u * 2.1)
        self.fx = pygame.font.Font(None, int(u * 1.15))       # small font for the button guide
        self.fh = self.fx.get_height() + 10
        self.top = int(u * 3.4)
        self.crt = make_crt(self.W, self.H)
        self.icon = None
        try:
            ic = pygame.image.load(str(core.resource_path("assets/icon.png")))
            n = self.top - 16
            self.icon = pygame.transform.scale(ic, (n, n))   # nearest-neighbour = chunky pixels
        except Exception:
            pass
        self.cfg = core.load_config(core.config_path())
        if not self.cfg.get("share"):
            self.cfg["share"] = os.environ.get("PMF_SHARE", "/userdata" if os.path.isdir("/userdata/roms") else "")
        self.stack, self.log, self.games = [], [], []
        self.busy = None
        self.job_done = None
        self.job_gen = 0
        self.toast = ""
        self.running = True
        self.fetched = {}
        self.axis = {}
        self.imgs = {}
        try:
            self.refresh()
        except Exception as e:
            traceback.print_exc()
            self.toast = "Error reading games: %s" % e
        self.stack.append(ListScreen(self))

    # ---------------------------------------------------------------- state
    def save(self):
        try:
            core.save_config(self.cfg, core.config_path())
        except OSError as e:
            self.toast = "Could not save settings: %s" % e

    def refresh(self):
        self.games = core.list_games(self.cfg)
        added = core.discover_folders(self.cfg, set(self.games))
        if added:
            self.save()
            self.toast = "Found saved categories: " + ", ".join(added)
        ex = core.scan_existing(self.cfg)
        for g in self.games:
            st = self.cfg["games"].setdefault(g, {})
            if not st.get("cat") and g in ex:
                st["cat"] = ex[g]

    def say(self, m):
        self.log.append(str(m))
        self.log = self.log[-50:]
        self.toast = str(m)

    def job(self, text, fn, done=None):
        """Run fn in a thread. B cancels (the result is then ignored). done(result) only runs on success."""
        if self.busy:
            return
        self.busy = text
        self.job_gen += 1
        gen = self.job_gen

        def run():
            try:
                res, err = fn(), None
            except Exception as e:
                traceback.print_exc()
                res, err = None, e
            if gen == self.job_gen:
                self.job_done = (done, res, err)
        threading.Thread(target=run, daemon=True).start()

    def push(self, s):
        self.stack.append(s)

    # ---------------------------------------------------------------- input
    def action_of(self, e):
        t = e.type
        if t == pygame.KEYDOWN:
            return KEYMAP.get(e.key)
        if t == getattr(pygame, "CONTROLLERBUTTONDOWN", -1):
            return self._swap(self._cb(e.button))
        if t == getattr(pygame, "CONTROLLERAXISMOTION", -1):
            return self._axis(("c", e.axis), e.value / 32768.0, e.axis)
        if self.ctrl:
            return None
        if t == pygame.JOYBUTTONDOWN:
            return self._swap(JBTN.get(e.button))
        if t == pygame.JOYHATMOTION:
            x, y = e.value
            return "left" if x < 0 else "right" if x > 0 else "up" if y > 0 else "down" if y < 0 else None
        if t == pygame.JOYAXISMOTION:
            return self._axis(("j", e.joy if hasattr(e, "joy") else 0, e.axis), e.value, e.axis)
        return None

    def _swap(self, a):
        return {"accept": "back", "back": "accept"}.get(a, a) if self.cfg.get("swap_ab") else a

    def _axis(self, key, v, axis):
        """Left stick as a d-pad (edge-triggered; held state is kept in self.axis for auto-repeat)."""
        if axis == 0:
            d = "left" if v < -0.6 else "right" if v > 0.6 else None
        elif axis == 1:
            d = "up" if v < -0.6 else "down" if v > 0.6 else None
        else:
            return None
        prev = self.axis.get(key)
        self.axis[key] = d
        return d if d and d != prev else None

    def _cb(self, b):
        P = pygame
        names = {P.CONTROLLER_BUTTON_A: "a", P.CONTROLLER_BUTTON_B: "b", P.CONTROLLER_BUTTON_X: "x", P.CONTROLLER_BUTTON_Y: "y",
                 P.CONTROLLER_BUTTON_LEFTSHOULDER: "leftshoulder", P.CONTROLLER_BUTTON_RIGHTSHOULDER: "rightshoulder",
                 P.CONTROLLER_BUTTON_START: "start", P.CONTROLLER_BUTTON_BACK: "back",
                 P.CONTROLLER_BUTTON_DPAD_UP: "dpup", P.CONTROLLER_BUTTON_DPAD_DOWN: "dpdown",
                 P.CONTROLLER_BUTTON_DPAD_LEFT: "dpleft", P.CONTROLLER_BUTTON_DPAD_RIGHT: "dpright"}
        return CBTN.get(names.get(b, ""))

    def _held(self, a):
        """Is direction `a` still held? (for auto-repeat)"""
        k = pygame.key.get_pressed()
        if any(k[key] for key, v in KEYMAP.items() if v == a):
            return True
        if any(d == a for d in self.axis.values()):
            return True
        for p in self.pads:
            try:
                if p.get_numhats():
                    hx, hy = p.get_hat(0)
                    if (a == "up" and hy > 0) or (a == "down" and hy < 0) or (a == "left" and hx < 0) or (a == "right" and hx > 0):
                        return True
            except pygame.error:
                pass
        for c in self.ctrl:
            try:
                b = {"up": pygame.CONTROLLER_BUTTON_DPAD_UP, "down": pygame.CONTROLLER_BUTTON_DPAD_DOWN,
                     "left": pygame.CONTROLLER_BUTTON_DPAD_LEFT, "right": pygame.CONTROLLER_BUTTON_DPAD_RIGHT}[a]
                if c.get_button(b):
                    return True
            except Exception:
                pass
        return False

    def safe(self, fn, *args):
        """Run a screen callback; log errors (data/log.txt) and keep the app alive."""
        try:
            return fn(*args)
        except Exception as e:
            traceback.print_exc()
            sys.stderr.flush()
            self.toast = "Error: %s" % e
            return False

    # ---------------------------------------------------------------- drawing helpers
    def text(self, s, x, y, col=FG, font=None, maxw=None):
        font = font or self.f
        s = str(s).replace("\n", " ")
        if maxw is not None and font.size(s)[0] > maxw:
            while s and font.size(s + "..")[0] > maxw:
                s = s[:-1]
            s += ".."
        self.screen.blit(font.render(s, False, col), (int(x), int(y)))     # antialias off = 8-bit edges

    def wrap(self, s, x, y, w, col=FG, lines=3):
        words, line, n, lh = str(s).split(), "", 0, self.fs.get_linesize()
        for wd in words:
            t = (line + " " + wd).strip()
            if self.fs.size(t)[0] > w and line:
                self.text(line, x, y + n * lh, col, self.fs)
                line, n = wd, n + 1
                if n >= lines:
                    return
            else:
                line = t
        if line and n < lines:
            self.text(line, x, y + n * lh, col, self.fs)

    def box(self, x, y, w, h, fill=PANEL, edge=EDGE):
        pygame.draw.rect(self.screen, fill, (x, y, w, h))
        pygame.draw.rect(self.screen, edge, (x, y, w, h), 2)

    def header(self, title, right=""):
        pygame.draw.rect(self.screen, PANEL, (0, 0, self.W, self.top))
        pygame.draw.rect(self.screen, EDGE, (0, self.top - 4, self.W, 2))
        x = 12
        if self.icon:
            self.screen.blit(self.icon, (x, (self.top - 4 - self.icon.get_height()) // 2))
            x += self.icon.get_width() + 10
        ty = (self.top - 4 - self.fb.get_height()) // 2
        r = self.fs.size(right)[0] + 16 if right else 0
        self.text(title.upper(), x, ty, ACC, self.fb, self.W - x - 12 - r)
        if right:
            self.text(right, self.W - r + 6, (self.top - 4 - self.fs.get_height()) // 2, DIM, self.fs)

    def footer(self, hints=""):
        """Small button guide at the bottom: 'A:Edit  X:New' -> key in orange, label in blue."""
        y0 = self.H - self.fh
        pygame.draw.rect(self.screen, PANEL, (0, y0, self.W, self.fh))
        pygame.draw.rect(self.screen, EDGE, (0, y0, self.W, 2))
        x, y = 8, y0 + 5
        for part in hints.split("  "):
            key, _, lab = part.partition(":")
            if not key:
                continue
            w = self.fx.size(key + " " + lab)[0] + 14
            if x + w > self.W:
                break
            self.text(key, x, y, ACC, self.fx)
            self.text(lab, x + self.fx.size(key + " ")[0], y, FG, self.fx)
            x += w

    def image(self, path, w, h):
        """Scaled-to-fit surface for a game image (cached)."""
        key = (str(path), w, h)
        if key not in self.imgs:
            if len(self.imgs) > 12:
                self.imgs.clear()
            try:
                im = pygame.image.load(str(path)).convert()
                iw, ih = im.get_size()
                k = min(w / iw, h / ih)
                self.imgs[key] = pygame.transform.scale(im, (max(1, int(iw * k)), max(1, int(ih * k))))
            except Exception:
                self.imgs[key] = None
        return self.imgs[key]

    # ---------------------------------------------------------------- main loop
    def run(self):
        clock = pygame.time.Clock()
        held, hold_t = None, 0
        while self.running:
            now = pygame.time.get_ticks()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                a = self.action_of(e)
                if not a:
                    continue
                if self.busy:
                    if a == "back":
                        self.job_gen += 1          # abandon the running job
                        self.busy = None
                        self.toast = "Cancelled"
                    continue
                self.toast = ""
                self.safe(self.stack[-1].handle, a)
                held, hold_t = (a if a in DIRS else None), now + 350
            if held and not self.busy:
                if not self._held(held):
                    held = None
                elif now > hold_t:
                    self.safe(self.stack[-1].handle, held)
                    hold_t = now + 70
            if self.job_done:
                done, res, err = self.job_done
                self.job_done, self.busy = None, None
                if err is not None:
                    self.toast = "Error: %s" % err
                elif done:
                    self.safe(done, res)
            self.screen.fill(BG)
            if self.safe(self.stack[-1].draw) is False and len(self.stack) > 1:
                self.stack.pop()
            if self.toast:
                self.box(0, self.H - self.fh - self.lh, self.W, self.lh, (56, 28, 0), ACC)
                self.text(self.toast, 10, self.H - self.fh - self.lh + (self.lh - self.fs.get_height()) // 2, ACC, self.fs, self.W - 20)
            if self.busy:
                bw, bh = self.W * 3 // 4, self.H // 4
                self.box((self.W - bw) // 2, self.H // 3, bw, bh, BG)
                dots = "." * (1 + (now // 400) % 3)
                self.text(self.busy + dots, (self.W - bw) // 2 + 16, self.H // 3 + 16, ACC, self.fb, bw - 32)
                if self.log:
                    self.text(self.log[-1], (self.W - bw) // 2 + 16, self.H // 3 + 16 + self.fb.get_height() + 8, DIM, self.fs, bw - 32)
                self.text("(B cancels)", (self.W - bw) // 2 + 16, self.H // 3 + bh - self.fs.get_height() - 10, DIM, self.fs)
            self.screen.blit(self.crt, (0, 0))
            pygame.display.flip()
            clock.tick(30)
        self.save()
        pygame.quit()


# ==================================================================== screens
class Menu:
    """Vertical list with scrolling."""
    reserve = 0

    def __init__(self, app):
        self.app, self.i, self.top = app, 0, 0

    def rows_visible(self):
        return max(3, (self.app.H - self.app.top - 12 - self.app.fh - self.reserve) // self.app.lh)

    def move(self, d, n):
        if n:
            self.i = (self.i + d) % n
            v = self.rows_visible()
            if self.i < self.top:
                self.top = self.i
            if self.i >= self.top + v:
                self.top = self.i - v + 1

    def draw_rows(self, rows, width, lx=0.0, rx=0.45):
        """rows = [(left, right, colour)]; drawn inside `width` pixels."""
        a, y0 = self.app, self.app.top + 8
        blink = (pygame.time.get_ticks() // 400) % 2 == 0
        for k in range(self.top, min(len(rows), self.top + self.rows_visible())):
            y = y0 + (k - self.top) * a.lh
            left, right, col = rows[k]
            if k == self.i:
                a.box(6, y - 2, width - 12, a.lh, SEL, EDGE)
                if blink:
                    a.text(">", 12, y + 4, ACC)
            a.text(left, 34, y + 4, col if col != FG else FG, a.f, int(width * (rx - 0.02)) - 34)
            if right:
                a.text(right, int(width * rx), y + 6, DIM if col == FG else col, a.fs, int(width * (1 - rx)) - 12)


class ListScreen(Menu):
    def __init__(self, app):
        super().__init__(app)
        self.sel_name, self.sel_t, self.img_path, self.path_done = None, 0, None, False

    def cats(self):
        return [""] + [c["folder"] for c in self.app.cfg["categories"]]

    def cname(self, folder):
        c = core.cat_by_folder(self.app.cfg, folder)
        return c["name"] if c else "- no category -"

    def handle(self, a):
        app, g = self.app, self.app.games
        if a in ("up", "down"):
            self.move(-1 if a == "up" else 1, len(g))
        elif a in ("l", "r") and g:
            self.move(-8 if a == "l" else 8, len(g))
        elif a in ("left", "right") and g:
            st = app.cfg["games"].setdefault(g[self.i], {})
            cs, cur = self.cats(), st.get("cat", "")
            st["cat"] = cs[(cs.index(cur) + (1 if a == "right" else -1)) % len(cs)] if cur in cs else ""
            app.save()
        elif a == "accept" and g:
            app.push(GameScreen(app, g[self.i]))
        elif a == "x":
            NewCategory(app)          # pushes its own keyboard screen
        elif a == "y" and g:
            cat = app.cfg["games"].get(g[self.i], {}).get("cat", "")
            if cat:
                app.push(Confirm(app, "Put ALL games without category in '%s'?" % self.cname(cat), lambda: self.fill(cat)))
            else:
                app.toast = "Give this game a category first (left/right)"
        elif a in ("start", "select"):
            app.push(MainMenu(app))
        elif a == "back":
            self.quit_ask()

    def fill(self, cat):
        for gm in self.app.games:
            st = self.app.cfg["games"].setdefault(gm, {})
            if not st.get("cat"):
                st["cat"] = cat
        self.app.save()

    def quit_ask(self):
        self.app.push(Confirm(self.app, "Quit PortMasterForwarder?", lambda: setattr(self.app, "running", False)))

    def draw(self):
        a = self.app
        g = a.games
        a.header("PortMasterForwarder", "%d games" % len(g))
        if not g:
            a.footer("X:New cat  START:Menu")
            a.text("No PortMaster ports found in:", 14, a.top + 14, WARN, a.fs)
            a.text(str(core.get_path(a.cfg, "ports_dir") or "(games folder not found)"), 14, a.top + 14 + a.lh, DIM, a.fs, a.W - 28)
            return
        self.i = min(self.i, len(g) - 1)
        lw = int(a.W * 0.62)
        rows = []
        for gm in g:
            c = a.cfg["games"].get(gm, {}).get("cat", "")
            rows.append((gm[:-3] if gm.endswith(".sh") else gm, self.cname(c), FG if c else DIM))
        self.draw_rows(rows, lw, rx=0.58)
        self.preview(g[self.i], lw + 4)
        a.footer("</>:Category  A:Edit  X:New cat  Y:Fill empty  START:Menu")

    def preview(self, name, x):
        """Game image, top-right corner."""
        a = self.app
        now = pygame.time.get_ticks()
        if name != self.sel_name:
            self.sel_name, self.sel_t, self.img_path = name, now, None
            self.path_done = False
        w = a.W - x - 10
        h = int(w * 0.8)
        y = a.top + 8
        a.box(x, y, w, h, BG)
        if now - self.sel_t > 150:                     # wait until the cursor rests (fast scrolling stays smooth)
            if not self.path_done:
                try:
                    self.img_path = core.existing_image_path(a.cfg, name)
                except Exception:
                    self.img_path = None
                self.path_done = True
            im = a.image(self.img_path, w - 8, h - 8) if self.img_path else None
            if im:
                a.screen.blit(im, (x + (w - im.get_width()) // 2, y + (h - im.get_height()) // 2))
            else:
                a.text("NO IMAGE", x + 10, y + h // 2 - 8, DIM, a.fs, w - 20)


class Confirm:
    def __init__(self, app, msg, yes):
        self.app, self.msg, self.yes = app, msg, yes

    def handle(self, a):
        if a == "accept":
            self.app.stack.pop()
            self.yes()
        elif a == "back":
            self.app.stack.pop()

    def draw(self):
        a = self.app
        if len(a.stack) > 1:
            a.stack[-2].draw()
        w, h, x, y = a.W * 8 // 10, a.H // 3, a.W // 10, a.H // 3
        a.box(x, y, w, h, BG, ACC)
        a.wrap(self.msg, x + 16, y + 14, w - 32, FG, 3)
        a.text("[A] YES    [B] NO", x + 16, y + h - 36, ACC, a.fs)


class Keyboard:
    """On-screen keyboard; cb(text) on OK."""
    def __init__(self, app, title, text, cb):
        self.app, self.title, self.t, self.cb = app, title, text[:MAXTXT], cb
        self.r = self.c = 0

    def handle(self, a):
        rows = len(KEYS) + 1
        if a == "up":
            self.r = (self.r - 1) % rows
        elif a == "down":
            self.r = (self.r + 1) % rows
        elif a in ("left", "right"):
            n = len(KEYS[self.r]) if self.r < len(KEYS) else 2
            self.c = (self.c + (1 if a == "right" else -1)) % n
        elif a == "x":
            self.t = self.t[:-1]
        elif a == "y" and len(self.t) < MAXTXT:
            self.t += " "
        elif a == "back":
            self.app.stack.pop()
            return
        elif a in ("accept", "start"):
            if a == "start" or self.r == len(KEYS):
                if a == "start" or self.c == 1:
                    self.app.stack.pop()
                    self.cb(self.t)
                    return
                self.t = self.t[:-1]
            elif len(self.t) < MAXTXT:
                self.t += KEYS[self.r][min(self.c, len(KEYS[self.r]) - 1)]
        self.c = min(self.c, (len(KEYS[self.r]) if self.r < len(KEYS) else 2) - 1)

    def draw(self):
        a = self.app
        a.header(self.title)
        blink = "_" if (pygame.time.get_ticks() // 400) % 2 == 0 else " "
        a.text(self.t + blink, 14, a.top + 10, ACC, a.fb, a.W - 28)
        y = a.top + int(a.lh * 1.8)
        cw = min(a.W // (max(map(len, KEYS)) + 2), 60)
        for r, row in enumerate(KEYS):
            for c, ch in enumerate(row):
                x = 12 + c * cw
                if (r, c) == (self.r, self.c):
                    a.box(x - 3, y - 2, cw, a.lh, SEL, EDGE)
                a.text(ch if ch != " " else "_", x + 2, y + 4)
            y += a.lh
        for c, lab in enumerate(("DEL", "OK")):
            x = 12 + c * cw * 4
            if (self.r, self.c) == (len(KEYS), c):
                a.box(x - 3, y - 2, cw * 3, a.lh, SEL, EDGE)
            a.text(lab, x + 2, y + 4, ACC)
        a.footer("A:Type  X:Del  Y:Space  START:Done  B:Cancel")


class NewCategory:
    """Name -> icon/theme."""
    def __init__(self, app):
        self.app, self.i, self.name = app, 0, None
        app.push(Keyboard(app, "New category name", "", self.got))

    def got(self, text):
        if not text.strip():
            return
        self.name = text.strip()
        self.app.push(self)

    def handle(self, a):
        n = len(core.FRIENDLY_THEMES)
        if a in ("up", "down"):
            self.i = (self.i + (1 if a == "down" else -1)) % n
        elif a in ("l", "r"):
            self.i = max(0, min(n - 1, self.i + (8 if a == "r" else -8)))
        elif a == "accept":
            core.add_category(self.app.cfg, self.name, core.FRIENDLY_THEMES[self.i][1])
            self.app.save()
            self.app.stack.pop()
            self.app.toast = "Category created. Use APPLY (START menu) to install it."
        elif a == "back":
            self.app.stack.pop()

    def draw(self):
        a = self.app
        a.header("Icon for '%s'" % self.name)
        vis = max(3, (a.H - a.top - 12 - a.fh) // a.lh)
        first = max(0, min(self.i - vis // 2, len(core.FRIENDLY_THEMES) - vis))
        for k in range(first, min(len(core.FRIENDLY_THEMES), first + vis)):
            label, key = core.FRIENDLY_THEMES[k]
            y = a.top + 8 + (k - first) * a.lh
            if k == self.i:
                a.box(6, y - 2, a.W - 12, a.lh, SEL, EDGE)
            a.text("%s  (%s)" % (label, key), 34, y + 4, FG, a.f, a.W - 50)
        a.footer("Up/Down:Icon  L/R:Page  A:Create  B:Cancel")


class IconPicker:
    """Pick an icon (theme) from the list; cb(key)."""
    def __init__(self, app, title, current, cb):
        self.app, self.title, self.cb = app, title, cb
        keys = [k for _, k in core.FRIENDLY_THEMES]
        self.i = keys.index(current) if current in keys else 0

    def handle(self, a):
        n = len(core.FRIENDLY_THEMES)
        if a in ("up", "down"):
            self.i = (self.i + (1 if a == "down" else -1)) % n
        elif a in ("l", "r"):
            self.i = max(0, min(n - 1, self.i + (8 if a == "r" else -8)))
        elif a == "accept":
            self.app.stack.pop()
            self.cb(core.FRIENDLY_THEMES[self.i][1])
        elif a == "back":
            self.app.stack.pop()

    def draw(self):
        a = self.app
        a.header(self.title)
        vis = max(3, (a.H - a.top - 12 - a.fh) // a.lh)
        first = max(0, min(self.i - vis // 2, len(core.FRIENDLY_THEMES) - vis))
        for k in range(first, min(len(core.FRIENDLY_THEMES), first + vis)):
            label, key = core.FRIENDLY_THEMES[k]
            y = a.top + 8 + (k - first) * a.lh
            if k == self.i:
                a.box(6, y - 2, a.W - 12, a.lh, SEL, EDGE)
            a.text("%s  (%s)" % (label, key), 34, y + 4, FG, a.f, a.W - 50)
        a.footer("Up/Down:Icon  L/R:Page  A:Choose  B:Cancel")


class CategoryList(Menu):
    """Edit the name and icon of your categories."""
    def cats(self):
        return self.app.cfg["categories"]

    def handle(self, a):
        app, cs = self.app, self.cats()
        if a in ("up", "down"):
            self.move(-1 if a == "up" else 1, len(cs))
        elif not cs:
            if a == "back":
                app.stack.pop()
        elif a == "accept":
            c = cs[self.i]
            app.push(Keyboard(app, "Name of '%s'" % c["name"], c["name"], lambda t, f=c["folder"]: self.change(f, name=t)))
        elif a == "x":
            c = cs[self.i]
            app.push(IconPicker(app, "Icon of '%s'" % c["name"], c.get("theme", ""), lambda k, f=c["folder"]: self.change(f, theme=k)))
        elif a == "back":
            app.stack.pop()

    def change(self, folder, name=None, theme=None):
        app = self.app
        if name is not None and not name.strip():
            return
        core.update_category(app.cfg, folder, name, theme)
        app.save()
        app.job("Updating menu", lambda: (core.install_systems(app.cfg, True, app.say, only=folder), reload_es(app)),
                lambda r: setattr(app, "toast", "Category updated"))

    def draw(self):
        a = self.app
        a.header("Edit categories")
        self.draw_rows([(c["name"], c.get("theme", ""), FG) for c in self.cats()], a.W, rx=0.66)
        a.footer("A:Rename  X:Icon  B:Back")


class MainMenu(Menu):
    def items(self):
        c = self.app.cfg
        s = c["sources"]
        app = self.app
        return [("APPLY ALL (shortcuts + metadata + menus)", self.apply),
                ("Edit categories (name / icon)", lambda: app.push(CategoryList(app))),
                ("Install category menus only", lambda: self.run("Installing menus", lambda: core.install_systems(c, False, app.say))),
                ("Metadata mode: " + c["meta_global"].upper() + "  (fill/replace)", self.mode),
                ("Source Steam: %s" % ("on" if s.get("steam") else "off"), lambda: self.tog("steam")),
                ("Source Wikipedia: %s" % ("on" if s.get("wikipedia") else "off"), lambda: self.tog("wikipedia")),
                ("Source RAWG: %s  (key: %s)" % ("on" if s.get("rawg") else "off", "set" if c["rawg_key"] else "none"), lambda: self.tog("rawg")),
                ("Type RAWG key", lambda: app.push(Keyboard(app, "RAWG key", c["rawg_key"], self.setkey))),
                ("One shortcut per MCPE version: %s" % ("on" if c.get("mcpe_versions", True) else "off"), self.mcpe),
                ("Swap A/B buttons: %s" % ("yes" if c.get("swap_ab") else "no"), self.swap),
                ("Remove my shortcuts", lambda: app.push(Confirm(app, "Delete shortcuts created by this tool?", lambda: self.run("Removing", lambda: core.remove_wrappers(c, app.say))))),
                ("Remove my category menus", lambda: app.push(Confirm(app, "Delete category menus created by this tool?", lambda: self.run("Removing", lambda: (core.remove_systems(c, False, app.say), reload_es(app)))))),
                ("Reload EmulationStation lists", lambda: self.run("Reloading", lambda: reload_es(app))),
                ("Quit", lambda: setattr(app, "running", False))]

    def run(self, text, fn):
        self.app.job(text, fn, lambda r: setattr(self.app, "toast", "Done. If categories do not show, restart the system."))

    def apply(self):
        app, c = self.app, self.app.cfg

        def work():
            core.install_systems(c, False, app.say)
            res = core.apply_all(c, app.say)
            reload_es(app)
            return res

        def done(res):
            for n, u in (res or {}).items():
                c["games"].setdefault(n, {}).update(u or {})
            app.save()
            app.toast = "Applied. Restart if the categories do not appear."
        app.job("Applying", work, done)

    def mode(self):
        c = self.app.cfg
        c["meta_global"] = "replace" if c["meta_global"] == "fill" else "fill"
        self.app.save()

    def tog(self, k):
        s = self.app.cfg["sources"]
        s[k] = not s.get(k)
        self.app.save()

    def mcpe(self):
        c = self.app.cfg
        c["mcpe_versions"] = not c.get("mcpe_versions", True)
        self.app.save()
        self.app.refresh()

    def swap(self):
        self.app.cfg["swap_ab"] = not self.app.cfg.get("swap_ab")
        self.app.save()

    def setkey(self, t):
        self.app.cfg["rawg_key"] = t.strip()
        self.app.save()

    def handle(self, a):
        it = self.items()
        if a in ("up", "down"):
            self.move(-1 if a == "up" else 1, len(it))
        elif a == "accept":
            it[self.i][1]()
        elif a in ("back", "start"):
            self.app.stack.pop()

    def draw(self):
        self.app.header("Menu")
        self.draw_rows([(t, "", FG) for t, _ in self.items()], self.app.W, rx=1.0)
        self.app.footer("A:Select  B:Back")


def reload_es(app):
    try:
        urllib.request.urlopen("http://127.0.0.1:1234/reloadgames", timeout=5).read()
        app.say("EmulationStation reloaded.")
    except Exception:
        app.say("Could not reload automatically - restart the system.")


class GameScreen(Menu):
    reserve = 0

    def __init__(self, app, name):
        super().__init__(app)
        self.name = name
        self.presets = list(core.all_presets(app.cfg))
        self.p = 0
        self.cur = self.read_cur()
        self.reserve = app.fs.get_linesize() * 3 + 14      # bottom panel with the full text of the selected row

    def read_cur(self):
        try:
            return core.existing_entry(self.app.cfg, self.name)      # read once, not every frame
        except Exception:
            return {}

    @property
    def st(self):
        return self.app.cfg["games"].setdefault(self.name, {})

    def row_tags(self):
        return ["cat", "preset"] + list(core.BLOCK_FIELDS) + ["image", "save"]

    def src(self, tag):
        return (self.st.get("src") or {}).get(tag, "auto")

    def value(self, tag):
        a = self.app
        v = core.manual_value(core.game_state(a.cfg, self.name), tag)
        if v:
            return core.display_value(tag, v), True
        f = a.fetched.get(self.name, {}).get(tag)
        if f:
            return core.display_value(tag, f), True
        return core.display_value(tag, self.cur.get(tag, "")), False

    def handle(self, a):
        app, tags = self.app, self.row_tags()
        tag = tags[self.i]
        if a in ("up", "down"):
            self.move(-1 if a == "up" else 1, len(tags))
        elif a in ("left", "right"):
            d = 1 if a == "right" else -1
            if tag == "cat":
                cs = [""] + [c["folder"] for c in app.cfg["categories"]]
                cur = self.st.get("cat", "")
                self.st["cat"] = cs[(cs.index(cur) + d) % len(cs)] if cur in cs else ""
            elif tag == "preset":
                self.p = (self.p + d) % len(self.presets)
            elif tag in core.BLOCK_FIELDS:
                opts = core.sources_for_field(tag)
                cur = self.src(tag)
                self.st.setdefault("src", {})[tag] = opts[(opts.index(cur) + d) % len(opts)] if cur in opts else "auto"
            elif tag == "image":
                ids = [m for m, _ in IMG_MODES]
                cur = self.st.get("shot_mode", "auto")
                self.st["shot_mode"] = ids[(ids.index(cur) + d) % len(ids)] if cur in ids else "auto"
            app.save()
        elif a == "accept":
            if tag == "preset":
                core.apply_preset(self.st, core.all_presets(app.cfg)[self.presets[self.p]])
                app.fetched.pop(self.name, None)
                app.save()
                app.toast = "Preset applied: " + self.presets[self.p]
            elif tag in core.BLOCK_FIELDS:
                self.fetch(tag)
            elif tag == "save":
                self.save_game()
            elif tag == "cat":
                app.toast = "Use left/right to change the category"
        elif a == "x" and tag in core.BLOCK_FIELDS:
            app.push(Keyboard(app, TITLES[tag], self.value(tag)[0] or "", lambda t, tg=tag: self.pin(tg, t)))
        elif a == "y" and tag in core.BLOCK_FIELDS:
            self.st.setdefault("manual", {}).pop(tag, None)
            app.fetched.get(self.name, {}).pop(tag, None)
            app.save()
        elif a == "start":
            self.save_game()
        elif a == "back":
            app.stack.pop()

    def save_game(self):
        """Apply ONLY this game: shortcut + gamelist entry + image."""
        app, name = self.app, self.name
        if not self.st.get("cat"):
            app.toast = "Choose a category first"
            return

        def work():
            core.install_systems(app.cfg, False, app.say)
            upd = core.apply_game(app.cfg, name, app.say, rewrite=True)   # typed values overwrite existing metadata
            reload_es(app)
            return upd or {}

        def done(upd):
            self.st.update(upd)
            app.fetched.pop(name, None)
            self.cur = self.read_cur()
            app.save()
            app.toast = "Saved: " + name[:-3]
        app.job("Saving " + name[:-3], work, done)

    def pin(self, tag, text):
        v = core.normalize_manual(tag, text)
        if v is None:
            self.app.toast = "Invalid value for " + TITLES[tag]
            return
        self.st.setdefault("manual", {})[tag] = v
        self.app.save()

    def fetch(self, tag):
        app, name, src = self.app, self.name, self.src(tag)
        if src == "keep":
            app.toast = "Source is 'Keep current'"
            return

        def done(res):
            val, upd = res or (None, None)
            self.st.update(upd or {})
            if val:
                app.fetched.setdefault(name, {})[tag] = val
                pin = core.normalize_manual(tag, core.display_value(tag, val))
                if pin is not None:                       # keep it: it is written when you save this game
                    self.st.setdefault("manual", {})[tag] = pin
            else:
                app.toast = "Nothing found for " + TITLES[tag]
            app.save()
        app.job("Fetching " + TITLES[tag], lambda: core.fetch_field(app.cfg, name, tag, src, app.say), done)

    def draw(self):
        a = self.app
        tags = self.row_tags()
        a.header(self.name[:-3] if self.name.endswith(".sh") else self.name)
        rows = []
        for t in tags:
            if t == "cat":
                c = core.cat_by_folder(a.cfg, self.st.get("cat", ""))
                rows.append(("Category", c["name"] if c else "- none -", FG))
            elif t == "preset":
                rows.append(("Preset (A applies)", "< %s >" % self.presets[self.p], FG))
            elif t == "image":
                rows.append(("Image", "< %s >" % dict(IMG_MODES).get(self.st.get("shot_mode", "auto"), "Auto"), FG))
            elif t == "save":
                rows.append(("SAVE THIS GAME", "", ACC))
            else:
                v, pinned = self.value(t)
                rows.append(("%s <%s>" % (TITLES[t], SRC.get(self.src(t), self.src(t))), v or "-", ACC if pinned else FG))
        self.draw_rows(rows, a.W, rx=0.46)
        t = tags[self.i]
        if t in core.BLOCK_FIELDS:
            py = a.H - a.fh - self.reserve
            a.box(6, py, a.W - 12, self.reserve - 4, BG, DIM)
            a.wrap(self.value(t)[0] or "-", 14, py + 6, a.W - 28, DIM, 3)
        a.footer("</>:Source  A:Fetch  X:Edit  Y:Clear  START:Save game  B:Back")


def main():
    if "--version" in sys.argv:
        print("PortMasterForwarder %s" % __version__)
        return
    if os.environ.get("PMF_SELFTEST"):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    App().run()
