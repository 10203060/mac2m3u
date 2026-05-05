"""
MAC → M3U PRO  |  Stalker Portal Extractor
Kivy Android App  –  built with Buildozer
"""

import os, sys, json, re, random, asyncio, threading
from datetime import datetime
from urllib.parse import urlparse, quote_plus

# ── Kivy setup (must be before any kivy import) ──────────
os.environ.setdefault("KIVY_ORIENTATION", "PORTRAIT")
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivy.utils import get_color_from_hex as hex_

# ── Colors ───────────────────────────────────────────────
BG      = hex_("070b10")
BG2     = hex_("0b1520")
BG3     = hex_("060a0e")
CYAN    = hex_("00fff7")
GREEN   = hex_("39ff14")
GOLD    = hex_("ffd700")
RED     = hex_("ff4455")
GRAY    = hex_("4e7888")
WHITE   = hex_("dff8ff")
CYANFAD = hex_("00fff730")

Window.clearcolor = BG

# ══════════════════════════════════════════════════════════
#  STALKER CLIENT  (aiohttp)
# ══════════════════════════════════════════════════════════
UAS = [
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG250 stbapp ver: 2 rev: 250 Safari/533.3",
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG256 stbapp ver: 2 rev: 250 Safari/533.3",
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG322 stbapp ver: 2 rev: 250 Safari/533.3",
    "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 Chrome/85.0.4183.102 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; MAG322) AppleWebKit/537.36 Chrome/94.0.4606.85 Safari/537.36",
]

def normalize_base(url):
    url = url.strip().rstrip("/")
    url = re.sub(r"/(stalker_portal/)?c/?$", "", url, flags=re.IGNORECASE)
    p = urlparse(url)
    scheme = p.scheme or "http"
    host   = p.hostname or p.path.split("/")[0]
    port   = p.port
    if port and not ((scheme=="http" and port==80) or (scheme=="https" and port==443)):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"

def safe_json(text):
    if not text: return None
    t = text.strip().lstrip("\ufeff").replace("\\/", "/")
    if not (t.startswith("{") or t.startswith("[")): return None
    try: return json.loads(t)
    except: return None

def extract_url(s):
    if not s: return None
    s = re.sub(r"^(ffmpeg|auto)\s+","", s.replace("\\/","/").strip())
    if re.match(r"https?://|rtsp://", s): return s.split()[0]
    m = re.search(r"(https?://[^\s'\"<>\\]+)", s)
    return m.group(1) if m else None

def jitter(base, f=0.3):
    return base*(1+random.uniform(-f,f))

def out_dir():
    for d in ["/sdcard/Download", os.path.expanduser("~/storage/downloads"),
              os.path.expanduser("~/Downloads"), "."]:
        if os.path.isdir(d): return d
    return "."


class StalkerClient:
    def __init__(self, base, mac):
        self.base  = normalize_base(base)
        self.mac   = mac.strip().upper()
        self.token = ""
        self._ua_i = 0
        self._n    = 0
        self.session = None

    def _hdr(self):
        ua = UAS[self._ua_i % len(UAS)]
        h = {
            "User-Agent":      ua,
            "X-User-Agent":    f"Model: MAG250; Link: WiFi; MAC:{self.mac}",
            "Accept":          "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control":   "no-cache",
            "Connection":      "keep-alive",
        }
        if self.token: h["Authorization"] = f"Bearer {self.token}"
        return h

    def _rot(self):
        self._ua_i = (self._ua_i+1) % len(UAS)
        if self.session:
            self.session._default_headers.update(self._hdr())

    async def __aenter__(self):
        import aiohttp
        from aiohttp import ClientTimeout, TCPConnector
        conn = TCPConnector(limit=20, ttl_dns_cache=300, enable_cleanup_closed=True)
        to   = ClientTimeout(total=40, connect=12, sock_read=25)
        self.session = aiohttp.ClientSession(
            connector=conn, timeout=to, headers=self._hdr(),
            cookies={"mac":self.mac,"stb_lang":"en","timezone":"GMT"},
            raise_for_status=False)
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.1)

    async def get(self, url):
        last = None
        for attempt in range(6):
            try:
                self._n += 1
                if self._n % 60 == 0: self._rot()
                async with self.session.get(url) as r:
                    txt = await r.text(errors="replace")
                    if r.status == 200: return safe_json(txt)
                    elif r.status == 403:
                        if attempt == 0: await self._hs()
                        else: self._rot()
                        await asyncio.sleep(jitter(1.5*(attempt+1)))
                    elif r.status == 429:
                        await asyncio.sleep(jitter(3*(attempt+1)))
                    elif r.status >= 500:
                        await asyncio.sleep(jitter(1*(2**attempt)))
                    else: return safe_json(txt)
            except Exception as e:
                last = e
                await asyncio.sleep(jitter(0.8*(2**attempt)))
        raise RuntimeError(f"Max retries: {last}")

    async def _hs(self):
        url = (f"{self.base}/portal.php?type=stb&action=handshake"
               f"&mac={quote_plus(self.mac)}&token=&JsHttpRequest=1-xml")
        d = await self.get(url)
        if not d: raise RuntimeError("Handshake empty")
        js = d.get("js",{})
        if isinstance(js,list) and js: js=js[0]
        tok = js.get("token","") if isinstance(js,dict) else ""
        if not tok: raise RuntimeError("No token")
        self.token = tok
        if self.session: self.session._default_headers.update(self._hdr())
        return tok

    async def handshake(self):
        return await self._hs()

    async def account_info(self):
        url = (f"{self.base}/portal.php?type=account_info"
               f"&action=get_main_info&mac={quote_plus(self.mac)}"
               f"&token={self.token}&JsHttpRequest=1-xml")
        d = await self.get(url) or {}
        js = d.get("js",{})
        if isinstance(js,list) and js: js=js[0]
        return js if isinstance(js,dict) else {}

    async def all_channels(self, progress_cb=None):
        all_ch, page, total = [], 0, 9999
        while len(all_ch) < total:
            page += 1
            url = (f"{self.base}/portal.php?type=itv"
                   f"&action=get_all_channels&fav=0&genre=*&sortby=number"
                   f"&JsHttpRequest=1-xml&mac={quote_plus(self.mac)}"
                   f"&token={self.token}&p={page}")
            d = await self.get(url) or {}
            js = d.get("js",{})
            data = (js.get("data",[]) if isinstance(js,dict) else
                    (js if isinstance(js,list) else []))
            if not data: break
            if isinstance(js,dict):
                total = int(js.get("total_items",len(data)) or len(data))
            all_ch += [x for x in data if isinstance(x,dict)]
            if progress_cb:
                progress_cb(len(all_ch), total)
            if len(all_ch) >= total: break
        return all_ch

    async def channels_by_genre(self, progress_cb=None):
        url = (f"{self.base}/portal.php?type=itv&action=get_genres"
               f"&JsHttpRequest=1-xml&mac={quote_plus(self.mac)}&token={self.token}")
        d = await self.get(url) or {}
        genres = d.get("js",[])
        if isinstance(genres,dict): genres = list(genres.values())
        if not isinstance(genres,list): genres = []

        all_ch = []
        for g in genres:
            gid = str(g.get("id","*"))
            page, total = 0, 9999
            while True:
                page += 1
                url2 = (f"{self.base}/portal.php?type=itv&action=get_ordered_list"
                        f"&genre={gid}&p={page}&fav=0&sortby=number"
                        f"&JsHttpRequest=1-xml&mac={quote_plus(self.mac)}&token={self.token}")
                d2 = await self.get(url2) or {}
                js = d2.get("js",{})
                data = js.get("data",[]) if isinstance(js,dict) else []
                if not data: break
                total = int(js.get("total_items",len(data)) or len(data))
                all_ch += [x for x in data if isinstance(x,dict)]
                if progress_cb: progress_cb(len(all_ch), max(total*len(genres),1))
                if page*14 >= total: break
        return all_ch


def build_m3u(channels, base, mac, token):
    lines = ["#EXTM3U"]
    mac_enc = quote_plus(mac)
    host = urlparse(base).hostname or ""
    for ch in channels:
        name  = (ch.get("name") or "Channel").strip().replace(",","")
        logo  = ch.get("logo","")
        group = ch.get("tv_genre_id") or ch.get("genre_id","")
        num   = ch.get("number") or ch.get("ch_num","")
        ch_id = ch.get("id","")
        cmd   = re.sub(r"^(ffmpeg|auto)\s+","", (ch.get("cmd") or "").strip())

        if re.match(r"https?://|rtsp://", cmd):
            link = cmd.replace("localhost", host)
        elif cmd:
            link = (f"{base}/play/live.php?mac={mac_enc}"
                    f"&stream={ch_id}&link_id={ch.get('link_id',ch_id)}"
                    f"&type=m3u8&output=ts&token={token}")
        else:
            link = (f"{base}/play/live.php?mac={mac_enc}"
                    f"&stream={ch_id}&type=m3u8&output=ts&token={token}")

        lines.append(f'#EXTINF:-1 tvg-id="{ch_id}" tvg-logo="{logo}"'
                     f' tvg-chno="{num}" group-title="{group}",{name}')
        lines.append(link)
    return "\n".join(lines)+"\n"


# ══════════════════════════════════════════════════════════
#  UI WIDGETS
# ══════════════════════════════════════════════════════════

class DarkBox(BoxLayout):
    """BoxLayout with a dark rounded background"""
    def __init__(self, radius=12, border_color=None, **kw):
        super().__init__(**kw)
        self._radius = radius
        self._border = border_color or CYANFAD
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*BG2)
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[dp(self._radius)])
            Color(*self._border)
            Line(rounded_rectangle=[self.x, self.y, self.width, self.height,
                                    dp(self._radius)], width=1.2)


class CyanLabel(Label):
    def __init__(self, **kw):
        kw.setdefault("color", CYAN)
        kw.setdefault("font_size", dp(11))
        kw.setdefault("font_name", "RobotoMono")
        super().__init__(**kw)


class SectionHeader(BoxLayout):
    def __init__(self, icon, label, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(36), spacing=dp(8), **kw)
        ico = Label(text=icon, font_size=dp(18), size_hint_x=None, width=dp(32))
        lbl = Label(text=label, color=CYAN, font_size=dp(11),
                    font_name="RobotoMono", bold=True, size_hint_x=None,
                    width=dp(130))
        line = Widget()
        with line.canvas:
            Color(0, 1, 0.97, 0.25)
            self._line_rect = Rectangle(pos=line.pos, size=(line.width, dp(1)))
        line.bind(pos=lambda *_: setattr(self._line_rect, "pos",
                  (line.x, line.center_y)),
                  size=lambda *_: setattr(self._line_rect, "size",
                  (line.width, dp(1))))
        self.add_widget(ico); self.add_widget(lbl); self.add_widget(line)


class DarkInput(TextInput):
    def __init__(self, **kw):
        kw.setdefault("background_color", [0, 0, 0, 0])
        kw.setdefault("foreground_color", list(WHITE))
        kw.setdefault("cursor_color", list(CYAN))
        kw.setdefault("hint_text_color", [0, 1, 0.97, 0.25])
        kw.setdefault("font_name", "RobotoMono")
        kw.setdefault("font_size", dp(12))
        kw.setdefault("multiline", False)
        kw.setdefault("padding", [dp(12), dp(10)])
        super().__init__(**kw)
        self.background_normal = ""
        self.background_active = ""


class GlowButton(Button):
    def __init__(self, color=None, **kw):
        self._glow_color = color or CYAN
        kw.setdefault("font_name", "RobotoMono")
        kw.setdefault("font_size", dp(12))
        kw.setdefault("color", list(self._glow_color))
        kw.setdefault("background_color", [0, 0, 0, 0])
        super().__init__(**kw)
        self.background_normal = ""
        self.background_down   = ""
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            r, g, b, a = self._glow_color
            Color(r*0.15, g*0.15, b*0.15, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(9)])
            Color(r, g, b, 0.8 if self.disabled else 1)
            Line(rounded_rectangle=[self.x, self.y, self.width, self.height,
                                    dp(9)], width=1.4)


# ══════════════════════════════════════════════════════════
#  MAIN SCREEN
# ══════════════════════════════════════════════════════════

class MainScreen(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=[dp(14), dp(8)],
                         spacing=dp(6), **kw)
        self._build_ui()

    def _build_ui(self):
        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg,"pos",self.pos),
                  size=lambda *_: setattr(self._bg,"size",self.size))

        # ── header ──────────────────────────────────────
        hdr = BoxLayout(size_hint_y=None, height=dp(52), orientation="vertical")
        hdr.add_widget(Label(text="MAC  →  M3U  PRO", color=CYAN,
                             font_size=dp(17), bold=True, font_name="RobotoMono"))
        hdr.add_widget(Label(text="STALKER PORTAL EXTRACTOR", color=list(CYAN[:3])+[0.4],
                             font_size=dp(9), font_name="RobotoMono"))
        self.add_widget(hdr)

        # ── server section ───────────────────────────────
        self.add_widget(SectionHeader("🖥", "SERVER", size_hint_y=None, height=dp(32)))

        url_box = DarkBox(orientation="horizontal", size_hint_y=None,
                          height=dp(46), padding=[dp(8),0])
        url_box.add_widget(Label(text="🌐", font_size=dp(17), size_hint_x=None, width=dp(30)))
        self.url_input = DarkInput(hint_text="http://server.com:8080/c/",
                                   text="http://777.app1.ssh.de.tx-daym.xyz:80/c/")
        url_box.add_widget(self.url_input)
        self.add_widget(url_box)

        mac_box = DarkBox(orientation="horizontal", size_hint_y=None,
                          height=dp(46), padding=[dp(8),0])
        mac_box.add_widget(Label(text="📡", font_size=dp(17), size_hint_x=None, width=dp(30)))
        self.mac_input = DarkInput(hint_text="00:1A:79:00:00:00",
                                   text="00:1A:79:4E:34:38")
        self.mac_input.bind(text=self._fmt_mac)
        mac_box.add_widget(self.mac_input)
        self.add_widget(mac_box)

        # ── error label ──────────────────────────────────
        self.err_lbl = Label(text="", color=RED, font_size=dp(11),
                             font_name="RobotoMono", size_hint_y=None, height=0)
        self.add_widget(self.err_lbl)

        # ── extract button ───────────────────────────────
        self.extract_btn = GlowButton(text="⬇  EXTRACT CHANNELS",
                                      size_hint_y=None, height=dp(50))
        self.extract_btn.bind(on_press=self._on_extract)
        self.add_widget(self.extract_btn)

        # ── progress bar ─────────────────────────────────
        self.prog = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(6))
        self.add_widget(self.prog)

        # ── subscription ─────────────────────────────────
        self.add_widget(SectionHeader("✅", "SUBSCRIPTION",
                                       size_hint_y=None, height=dp(32)))
        sub_box = DarkBox(orientation="vertical", size_hint_y=None,
                          height=dp(100), padding=[dp(14), dp(10)], spacing=dp(8))
        self.sub_rows = {}
        for k, c in [("MAC",CYAN),("EXPIRY",GOLD),("CHANNELS",GREEN)]:
            row = BoxLayout(orientation="horizontal")
            row.add_widget(Label(text=k, color=GRAY, font_size=dp(11),
                                 font_name="RobotoMono", halign="left",
                                 size_hint_x=0.4, text_size=(dp(120),None)))
            val = Label(text="—", color=c, font_size=dp(11), bold=True,
                        font_name="RobotoMono", halign="right",
                        size_hint_x=0.6)
            row.add_widget(val)
            self.sub_rows[k] = val
            sub_box.add_widget(row)
        self.add_widget(sub_box)

        # ── download button (hidden until done) ──────────
        self.dl_btn = GlowButton(text="⬇  DOWNLOAD M3U FILE", color=GREEN,
                                  size_hint_y=None, height=0, opacity=0)
        self.dl_btn.bind(on_press=self._on_download)
        self.add_widget(self.dl_btn)

        # ── log ──────────────────────────────────────────
        self.add_widget(SectionHeader("📋", "LOG", size_hint_y=None, height=dp(32)))
        scroll = ScrollView()
        self.log_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(3), padding=[dp(10),dp(8)])
        self.log_box.bind(minimum_height=self.log_box.setter("height"))
        scroll.add_widget(self.log_box)
        with scroll.canvas.before:
            Color(*BG3)
            RoundedRectangle(pos=scroll.pos, size=scroll.size, radius=[dp(9)])
        self.scroll = scroll
        self.add_widget(scroll)

        self._m3u_content = None
        self._fname = None

    # ── MAC formatter ────────────────────────────────────
    def _fmt_mac(self, inst, val):
        h = re.sub(r"[^a-fA-F0-9]","", val).upper()[:12]
        fmt = ":".join(h[i:i+2] for i in range(0,len(h),2) if h[i:i+2])
        if inst.text != fmt:
            inst.text = fmt
            inst.cursor = (len(fmt), 0)

    # ── log helper ───────────────────────────────────────
    @mainthread
    def log(self, text, color=None):
        c = color or CYAN
        lbl = Label(text=text, color=c, font_size=dp(10),
                    font_name="RobotoMono", halign="left",
                    size_hint_y=None, height=dp(18), text_size=(dp(400), None))
        self.log_box.add_widget(lbl)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.05)

    @mainthread
    def set_progress(self, val):
        self.prog.value = min(100, max(0, val))

    @mainthread
    def set_sub(self, mac="—", expiry="—", channels="—"):
        self.sub_rows["MAC"].text      = mac
        self.sub_rows["EXPIRY"].text   = expiry
        self.sub_rows["CHANNELS"].text = str(channels)

    @mainthread
    def set_error(self, msg):
        self.err_lbl.text   = f"⚠ {msg}"
        self.err_lbl.height = dp(20)

    @mainthread
    def clear_error(self):
        self.err_lbl.text   = ""
        self.err_lbl.height = 0

    @mainthread
    def show_download_btn(self):
        self.dl_btn.height  = dp(50)
        self.dl_btn.opacity = 1

    @mainthread
    def set_busy(self, busy):
        self.extract_btn.disabled = busy
        self.extract_btn.text = (
            "⏳  EXTRACTING…" if busy else "⬇  EXTRACT CHANNELS")

    # ── extract ──────────────────────────────────────────
    def _on_extract(self, *_):
        url = self.url_input.text.strip()
        mac = self.mac_input.text.strip()
        if not url:
            self.set_error("أدخل IPTV Base URL"); return
        if mac.replace(":","").replace("-","").replace(".","").upper().__len__() < 12:
            self.set_error("أدخل MAC صحيح (12 خانة)"); return

        self.clear_error()
        self.set_sub(); self.set_progress(0)
        self.log_box.clear_widgets()
        self.dl_btn.height = 0; self.dl_btn.opacity = 0
        self._m3u_content = None
        self.set_busy(True)

        t = threading.Thread(target=self._run_extract, args=(url, mac), daemon=True)
        t.start()

    def _run_extract(self, url, mac):
        try:
            asyncio.run(self._extract_async(url, mac))
        except Exception as e:
            self.log(f"✗ {e}", RED)
        finally:
            self.set_busy(False)

    async def _extract_async(self, url, mac):
        try:
            import aiohttp  # noqa – ensure import works
        except ImportError:
            self.log("❌ aiohttp غير مثبت. شغل: pip install aiohttp", RED)
            return

        self.log(f"▶ Connecting to {normalize_base(url)}")
        self.set_progress(5)

        async with StalkerClient(url, mac) as c:
            # handshake
            self.log("▶ Handshake…")
            try:
                tok = await c.handshake()
                self.log(f"✓ Token: {tok[:14]}…", GREEN)
            except Exception as e:
                self.log(f"✗ {e}", RED); return
            self.set_progress(18)

            # account
            self.log("▶ Account info…")
            info   = await c.account_info()
            expiry = info.get("end_date") or info.get("expire_billing_date") or info.get("phone","?")
            self.log(f"✓ Expiry: {expiry}", GREEN)
            self.set_progress(30)

            # channels
            self.log("▶ Fetching channels…")
            channels = []

            def prog_cb(done, total):
                pct = 30 + int(done/max(total,1)*55)
                self.set_progress(pct)
                Clock.schedule_once(lambda dt:
                    self.log(f"  {done}/{total} channels…"), 0)

            try:
                channels = await c.all_channels(prog_cb)
            except Exception as e:
                self.log(f"⚠ Fallback: {e}", GOLD)
                try:
                    channels = await c.channels_by_genre(prog_cb)
                except Exception as e2:
                    self.log(f"✗ {e2}", RED); return

            if not channels:
                self.log("✗ No channels found", RED); return

            self.log(f"✓ {len(channels)} channels", GREEN)
            self.set_progress(88)

            # build m3u
            self.log("▶ Building M3U…")
            m3u = build_m3u(channels, c.base, c.mac, c.token)

            mac_s   = mac.replace(":","_")
            exp_s   = expiry.replace(" ","_").replace(",","").replace(":","_")
            host_s  = c.base.replace("http://","").replace("https://","").replace(":","_").replace("/","_")[:35]
            fname   = f"{host_s}__MAC_{mac_s}__exp_{exp_s}.m3u"
            fpath   = os.path.join(out_dir(), fname)

            with open(fpath,"w",encoding="utf-8") as f:
                f.write(m3u)

            self._m3u_content = m3u
            self._fname       = fpath

            self.log(f"✓ Saved: {fpath}", GREEN)
            self.log(f"  Lines: {m3u.count(chr(10))} | Size: {len(m3u)//1024} KB", GREEN)
            self.set_progress(100)
            self.set_sub(mac, expiry, len(channels))
            self.show_download_btn()
            self.log("══ DONE ══", GREEN)

    # ── download ─────────────────────────────────────────
    def _on_download(self, *_):
        if self._fname and os.path.exists(self._fname):
            self.log(f"✓ File at: {self._fname}", GREEN)
        else:
            self.log("✗ File not found", RED)


# ══════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════

class MacToM3UApp(App):
    def build(self):
        self.title = "MAC → M3U PRO"
        root = ScrollView()
        screen = MainScreen(size_hint_y=None, height=dp(820))
        root.add_widget(screen)
        return root


if __name__ == "__main__":
    MacToM3UApp().run()
