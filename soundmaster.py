#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk, Pango
import subprocess
import os
import threading
import json

SOUND_FILE = "/usr/share/sounds/freedesktop/stereo/audio-test-signal.oga"
DOT_SIZE = 20
CONFIG_DIR = os.path.expanduser("~/.config/testa-ljudet")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")


def get_sinks():
    sinks = []
    try:
        out = subprocess.check_output(["pactl", "list", "sinks"], timeout=5).decode()
    except Exception:
        return sinks
    cur = None
    for line in out.splitlines():
        raw = line.strip()
        if raw.startswith("Sink #"):
            if cur:
                sinks.append(tuple(cur))
            cur = [raw.split("#")[1], "", ""]
        elif cur is not None:
            if raw.startswith("Name:"):
                cur[1] = raw.split(":", 1)[1].strip()
            elif raw.startswith("Description:"):
                cur[2] = raw.split(":", 1)[1].strip()
    if cur:
        sinks.append(tuple(cur))
    return sinks


def get_sink_volume(name):
    try:
        out = subprocess.check_output(["pactl", "list", "sinks"], timeout=5).decode()
        in_sink = False
        for line in out.splitlines():
            raw = line.strip()
            if raw.startswith("Sink #"):
                in_sink = False
            if f"Name: {name}" in raw:
                in_sink = True
            if in_sink and "Volume:" in raw and "front-left" in raw:
                parts = raw.split("/")
                if len(parts) >= 2:
                    pct = parts[1].strip().rstrip("%")
                    return int(pct)
    except Exception:
        pass
    return None


def set_sink_volume(name, pct):
    try:
        subprocess.run(["pactl", "set-sink-volume", name, f"{pct}%"], timeout=5)
    except Exception:
        pass


def set_sink_mute(name, muted):
    try:
        cmd = ["pactl", "set-sink-mute", name, "1" if muted else "0"]
        subprocess.run(cmd, timeout=5)
    except Exception:
        pass


def get_sink_mute(name):
    try:
        out = subprocess.check_output(["pactl", "list", "sinks"], timeout=5).decode()
        in_sink = False
        for line in out.splitlines():
            raw = line.strip()
            if raw.startswith("Sink #"):
                in_sink = False
            if f"Name: {name}" in raw:
                in_sink = True
            if in_sink and raw.startswith("Mute:"):
                return "yes" in raw.lower()
    except Exception:
        pass
    return False


def get_default_sink():
    try:
        out = subprocess.check_output(["pactl", "info"], timeout=5).decode()
        for line in out.splitlines():
            if "Default Sink:" in line:
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def get_sink_inputs():
    try:
        out = subprocess.check_output(
            ["pactl", "-f", "json", "list", "sink-inputs"], timeout=5
        ).decode()
        return json.loads(out)
    except Exception:
        return []


def get_si_volume_pct(si):
    vol = si.get("volume", {})
    vals = [v.get("value_percent", "0%") for v in vol.values()]
    if vals:
        return int(vals[0].rstrip("%"))
    return 0


def set_si_volume(idx, pct):
    try:
        subprocess.run(["pactl", "set-sink-input-volume", str(idx), f"{pct}%"], timeout=5)
    except Exception:
        pass


def set_si_mute(idx, muted):
    try:
        subprocess.run(
            ["pactl", "set-sink-input-mute", str(idx), "1" if muted else "0"],
            timeout=5,
        )
    except Exception:
        pass


def health_check():
    issues = []
    try:
        subprocess.check_output(["pactl", "info"], timeout=5, stderr=subprocess.STDOUT)
    except Exception:
        issues.append("PulseAudio/PipeWire körs inte")
    sinks = get_sinks()
    if not sinks:
        issues.append("Inga ljudutgångar hittades")
    if not os.path.exists(SOUND_FILE):
        issues.append("Testljudfil saknas")
    try:
        subprocess.check_call(
            ["paplay", "--version"],
            timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        issues.append("paplay saknas")
    return issues


def load_favorites():
    try:
        with open(FAVORITES_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_favorites(favs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(FAVORITES_FILE, "w") as f:
        json.dump(sorted(favs), f)


class DotWidget(Gtk.DrawingArea):
    def __init__(self, color="#4CAF50"):
        super().__init__()
        self.color = color
        self.set_size_request(DOT_SIZE, DOT_SIZE)
        self.connect("draw", self.on_draw)

    def set_color(self, color):
        self.color = color
        self.queue_draw()

    def on_draw(self, widget, cr):
        alloc = self.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2
        r = min(cx, cy) - 2
        cr.set_source_rgba(0, 0, 0, 0.15)
        cr.arc(cx + 1, cy + 1, r, 0, 6.2832)
        cr.fill()
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.arc(cx, cy, r, 0, 6.2832)
        cr.fill()


SINK_COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
               "#f97316", "#eab308", "#22c55e", "#14b8a6",
               "#06b6d4", "#3b82f6"]


def app_color(name):
    h = hash(name)
    return SINK_COLORS[abs(h) % len(SINK_COLORS)]


class SinkRow(Gtk.ListBoxRow):
    def __init__(self, sid, name, desc, is_fav, on_star_toggle, on_select):
        super().__init__()
        self.sid = sid
        self.name = name
        self.desc = desc
        self.is_fav = is_fav
        self.on_star_toggle = on_star_toggle

        box = Gtk.Box(spacing=6, margin=4)
        self.star_btn = Gtk.ToggleButton()
        self.star_btn.set_active(is_fav)
        self.star_btn.set_size_request(32, 28)
        self.star_lbl = Gtk.Label()
        self._update_star_label()
        self.star_btn.add(self.star_lbl)
        self.star_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.star_btn.connect("toggled", self._on_star)
        lbl = Gtk.Label(label=desc)
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(self.star_btn, False, False, 0)
        box.pack_start(lbl, True, True, 0)
        self.add(box)
        self.connect("activate", lambda _: on_select(self))

    def _update_star_label(self):
        self.star_lbl.set_markup(
            '<span foreground="#f59e0b" size="large">\u2605</span>'
            if self.is_fav else
            '<span foreground="#9ca3af" size="large">\u2606</span>'
        )

    def _on_star(self, btn):
        self.is_fav = btn.get_active()
        self._update_star_label()
        self.on_star_toggle(self)


class AppStreamRow(Gtk.ListBoxRow):
    def __init__(self, idx, name, icon_name, vol_pct, muted, sink_idx, on_debounce):
        super().__init__()
        self.idx = idx
        self.sink_idx = sink_idx
        self._updating = False

        box = Gtk.Box(spacing=6, margin=4)
        color = app_color(name)

        icon_box = Gtk.Box(spacing=4)
        dot = Gtk.DrawingArea()
        dot.set_size_request(8, 8)
        dot.connect("draw", lambda w, cr: self._draw_dot(cr, w, color))
        icon_box.pack_start(dot, False, False, 0)

        self.app_lbl = Gtk.Label(label=name)
        self.app_lbl.set_xalign(0)
        self.app_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.app_lbl.set_size_request(90, -1)
        icon_box.pack_start(self.app_lbl, False, False, 0)
        box.pack_start(icon_box, False, False, 0)

        self.scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.scale.set_range(0, 150)
        self.scale.set_value(vol_pct)
        self.scale.set_digits(0)
        self.scale.set_hexpand(True)
        self.scale.set_size_request(100, -1)
        self.scale.connect("value-changed", self._on_scale)
        box.pack_start(self.scale, True, True, 0)

        self.mute_btn = Gtk.ToggleButton()
        self.mute_btn.set_active(muted)
        mrk = "\u25b7" if muted else "\u25bd"
        self.mute_btn.set_label(mrk)
        self.mute_btn.set_size_request(32, 28)
        self.mute_btn.connect("toggled", self._on_mute)
        box.pack_start(self.mute_btn, False, False, 0)

        self.add(box)
        self.on_debounce = on_debounce
        self._debounce_timer = None

    def _draw_dot(self, cr, widget, color):
        alloc = widget.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2
        rgba = Gdk.RGBA()
        rgba.parse(color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.arc(cx, cy, 3, 0, 6.2832)
        cr.fill()

    def _on_scale(self, scale):
        if self._updating:
            return
        pct = int(scale.get_value())
        if self._debounce_timer:
            GLib.source_remove(self._debounce_timer)
        self._debounce_timer = GLib.timeout_add(150, self._apply_vol, pct)

    def _apply_vol(self, pct):
        self._debounce_timer = None
        self.on_debounce(self.idx, pct, None)
        return False

    def _on_mute(self, btn):
        self.on_debounce(self.idx, None, btn.get_active())

    def update_values(self, vol_pct, muted):
        self._updating = True
        if vol_pct is not None:
            self.scale.set_value(vol_pct)
        if muted is not None:
            self.mute_btn.set_active(muted)
        self._updating = False


class AudioTester(Gtk.Window):
    def __init__(self):
        super().__init__(title="Testa ljudet")
        self.set_border_width(12)
        self.set_default_size(680, 480)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_type_hint(Gdk.WindowTypeHint.DROPDOWN_MENU)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.connect("focus-out-event", lambda w, e: w.destroy())
        self.connect("key-press-event", self._on_key)

        self.favorites = load_favorites()
        self.sinks = []
        self.current_sink = None
        self._updating_vol = False
        self._vol_debounce = None
        self._si_debounce = {}
        self._updating_apps = False

        css_sel = b"""
        #dev-list row {
            padding: 0;
        }
        #dev-list row:selected {
            background: transparent;
        }
        .selected-sink {
            background: rgba(34, 197, 94, 0.08);
            border-left: 5px solid #22c55e;
            padding-left: 2px;
        }
        .default-sink {
            border-left: 5px solid #16a34a;
            font-weight: bold;
        }
        .default-sink.selected-sink {
            border-left: 5px solid #15803d;
        }
        """
        sp_sel = Gtk.CssProvider()
        sp_sel.load_from_data(css_sel)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), sp_sel,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )

        hb = Gtk.HeaderBar(title="Testa ljudet")
        hb.set_show_close_button(True)
        hb.set_subtitle("Ljudutgångar och program")
        self.set_titlebar(hb)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=4)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=4)

        paned.pack1(left, resize=True, shrink=False)
        paned.pack2(right, resize=True, shrink=True)
        paned.set_position(340)

        health_row = Gtk.Box(spacing=8)
        self.health_dot = DotWidget("#9E9E9E")
        health_row.pack_start(self.health_dot, False, False, 0)
        self.health_label = Gtk.Label()
        self.health_label.set_markup("<b>Ljudsystem:</b> Kontrollerar...")
        self.health_label.set_xalign(0)
        health_row.pack_start(self.health_label, True, True, 0)
        left.pack_start(health_row, False, False, 0)

        left.pack_start(Gtk.Label(label="<b>Ljudutgångar</b>", use_markup=True, xalign=0), False, False, 0)

        sc_dev = Gtk.ScrolledWindow()
        sc_dev.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_dev.set_min_content_height(140)
        self.dev_listbox = Gtk.ListBox()
        self.dev_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.dev_listbox.set_name("dev-list")
        self.dev_listbox.connect("row-selected", self._on_dev_selected)
        sc_dev.add(self.dev_listbox)
        left.pack_start(sc_dev, True, True, 0)

        vol_box = Gtk.Box(spacing=6)
        vol_lbl = Gtk.Label(label="Volym:")
        vol_lbl.set_size_request(45, -1)
        self.vol_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.vol_scale.set_range(0, 150)
        self.vol_scale.set_value(100)
        self.vol_scale.set_digits(0)
        self.vol_scale.set_hexpand(True)
        self.vol_scale.connect("value-changed", self._on_vol_changed)
        self.mute_btn = Gtk.ToggleButton(label="\u25bd")
        self.mute_btn.set_size_request(32, 28)
        self.mute_btn.connect("toggled", self._on_mute_toggled)
        vol_box.pack_start(vol_lbl, False, False, 0)
        vol_box.pack_start(self.vol_scale, True, True, 0)
        vol_box.pack_start(self.mute_btn, False, False, 0)
        left.pack_start(vol_box, False, False, 0)

        act_row = Gtk.Box(spacing=6)
        btn_def = Gtk.Button(label="Standard")
        btn_def.connect("clicked", self.on_set_default)
        act_row.pack_start(btn_def, False, False, 0)
        act_row.pack_start(Gtk.Label(), True, True, 0)
        test_btn = Gtk.Button(label="\u25b6 Testa ljudet")
        test_btn.set_size_request(-1, 36)
        test_btn.connect("clicked", self.on_test)
        act_row.pack_end(test_btn, False, False, 0)
        left.pack_start(act_row, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        left.pack_start(self.status_label, False, False, 0)

        right.pack_start(Gtk.Label(label="<b>Aktiva program</b>", use_markup=True, xalign=0), False, False, 0)

        sc_app = Gtk.ScrolledWindow()
        sc_app.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_app.set_min_content_height(140)
        self.app_listbox = Gtk.ListBox()
        self.app_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        sc_app.add(self.app_listbox)
        right.pack_start(sc_app, True, True, 0)

        self.refresh_sinks()
        self.refresh_apps()
        self.run_health_check()
        GLib.idle_add(self._select_default_sink)

        self._refresh_apps_timer = None
        GLib.timeout_add_seconds(2, self._auto_refresh)

    def _auto_refresh(self):
        self.refresh_apps()
        return True

    def _build_dev_list(self):
        self.dev_listbox.forall(lambda w, *a: self.dev_listbox.remove(w))
        default = get_default_sink()
        starred = [(s, n, d) for s, n, d in self.sinks if n in self.favorites]
        unstarred = [(s, n, d) for s, n, d in self.sinks if n not in self.favorites]

        def add_row(sid, name, desc):
            row = SinkRow(sid, name, desc, name in self.favorites,
                          self._on_star_toggle, self._on_dev_select)
            row.set_name(name)
            if name == default:
                row.get_style_context().add_class("default-sink")
            if name == self.current_sink:
                row.get_style_context().add_class("selected-sink")
            self.dev_listbox.add(row)

        for s, n, d in starred:
            add_row(s, n, d)

        if starred and unstarred:
            sep = Gtk.ListBoxRow()
            sep.set_sensitive(False)
            lbl = Gtk.Label(label="<span foreground='#888'><b>Andra enheter</b></span>")
            lbl.set_use_markup(True)
            lbl.set_xalign(0)
            lbl.set_margin_start(8)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            sep.add(lbl)
            self.dev_listbox.add(sep)

        for s, n, d in unstarred:
            add_row(s, n, d)

        if not self.sinks:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label="Inga ljudutgångar", margin=8))
            row.set_sensitive(False)
            self.dev_listbox.add(row)

        self.dev_listbox.show_all()
        self._update_vol_ui()

    def _select_default_sink(self):
        default = get_default_sink()
        if default:
            for row in self.dev_listbox.get_children():
                if hasattr(row, 'name') and row.name == default:
                    self.dev_listbox.select_row(row)
                    self._select_dev(default)
                    return
        elif self.sinks:
            sid, name, desc = self.sinks[0]
            for row in self.dev_listbox.get_children():
                if hasattr(row, 'name') and row.name == name:
                    self.dev_listbox.select_row(row)
                    self._select_dev(name)
                    return

    def refresh_sinks(self):
        self.sinks = get_sinks()
        self._build_dev_list()

    def refresh_apps(self):
        if self._updating_apps:
            return
        self._updating_apps = True
        inputs = get_sink_inputs()
        existing = {}
        for row in self.app_listbox.get_children():
            if hasattr(row, 'idx'):
                existing[row.idx] = row

        if not inputs:
            if not existing:
                row = Gtk.ListBoxRow()
                row.set_sensitive(False)
                row.add(Gtk.Label(label="Inga aktiva program", margin=8))
                self.app_listbox.add(row)
            self.app_listbox.show_all()
            return

        def on_debounce(idx, vol, muted):
            if vol is not None:
                if idx in self._si_debounce:
                    GLib.source_remove(self._si_debounce[idx])
                tid = GLib.timeout_add(150, self._apply_si_vol, idx, vol)
                self._si_debounce[idx] = tid
            if muted is not None:
                set_si_mute(idx, muted)

        seen = set()
        for si in inputs:
            idx = si.get("index", 0)
            seen.add(idx)
            props = si.get("properties", {})
            name = self._app_name(si, idx)
            icon = props.get("application.icon_name", "")
            vol = get_si_volume_pct(si)
            muted = si.get("mute", False)
            sink = si.get("sink", 0)

            if idx in existing:
                existing[idx].update_values(vol, muted)
                row = existing.pop(idx)
                self.app_listbox.set_sort_func(lambda a, b: 0)
            else:
                row = AppStreamRow(idx, name, icon, vol, muted, sink, on_debounce)
                self.app_listbox.add(row)

        for leftover in existing.values():
            self.app_listbox.remove(leftover)

        self.app_listbox.show_all()
        self._updating_apps = False

    def _on_key(self, win, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q, Gdk.KEY_Q):
            self.destroy()
        return False

    def refresh_apps_soon(self):
        if hasattr(self, '_refresh_apps_timer') and self._refresh_apps_timer:
            GLib.source_remove(self._refresh_apps_timer)
        self._refresh_apps_timer = GLib.timeout_add(2000, self._do_refresh_apps)

    def _do_refresh_apps(self):
        self._refresh_apps_timer = None
        self.refresh_apps()
        return False

    def _apply_si_vol(self, idx, pct):
        self._si_debounce.pop(idx, None)
        set_si_volume(idx, pct)
        return False

    def _app_name(self, si, idx):
        props = si.get("properties", {})
        return (props.get("application.process.binary")
                or props.get("application.name")
                or props.get("media.name")
                or f"Stream #{idx}")

    def _on_star_toggle(self, row):
        if row.name in self.favorites:
            self.favorites.discard(row.name)
        else:
            self.favorites.add(row.name)
        save_favorites(self.favorites)
        self._build_dev_list()

    def _on_dev_selected(self, _box, row):
        if row is not None and hasattr(row, 'name'):
            self._select_dev(row.name)

    def _on_dev_select(self, row):
        if row.name != self.current_sink:
            self._select_dev(row.name)

    def _select_dev(self, name):
        self.current_sink = name
        for row in self.dev_listbox.get_children():
            ctx = row.get_style_context()
            if hasattr(row, 'name') and row.name == name:
                ctx.add_class("selected-sink")
            else:
                ctx.remove_class("selected-sink")
        self._update_vol_ui()

    def _update_vol_ui(self):
        name = self.current_sink
        self._updating_vol = True
        if name:
            vol = get_sink_volume(name)
            muted = get_sink_mute(name)
            if vol is not None:
                self.vol_scale.set_value(vol)
            self.mute_btn.set_active(muted)
            self.vol_scale.set_sensitive(True)
            self.mute_btn.set_sensitive(True)
        else:
            self.vol_scale.set_sensitive(False)
            self.mute_btn.set_sensitive(False)
        self._updating_vol = False

    def _on_vol_changed(self, scale):
        if self._updating_vol:
            return
        name = self.current_sink
        if not name:
            return
        pct = int(scale.get_value())
        if self._vol_debounce:
            GLib.source_remove(self._vol_debounce)
        self._vol_debounce = GLib.timeout_add(150, self._apply_vol, name, pct)

    def _apply_vol(self, name, pct):
        self._vol_debounce = None
        set_sink_volume(name, pct)
        return False

    def _on_mute_toggled(self, btn):
        name = self.current_sink
        if name:
            set_sink_mute(name, btn.get_active())

    def run_health_check(self):
        def check():
            issues = health_check()
            GLib.idle_add(self._update_health, issues)
        threading.Thread(target=check, daemon=True).start()

    def _update_health(self, issues):
        if not issues:
            self.health_dot.set_color("#4CAF50")
            self.health_label.set_markup("<b>Ljudsystem:</b> OK")
            self.status_label.set_markup('<span foreground="green">Allt fungerar</span>')
        else:
            self.health_dot.set_color("#F44336")
            self.health_label.set_markup("<b>Ljudsystem:</b> Problem")
            text = "\n".join(f"  \u2022 {i}" for i in issues)
            self.status_label.set_markup(f'<span foreground="red">Problem:\n{text}</span>')

    def on_set_default(self, _btn=None):
        name = self.current_sink
        if not name:
            return
        try:
            subprocess.run(["pactl", "set-default-sink", name], timeout=5)
            self.status_label.set_markup('<span foreground="green">Standard ljudutgång ändrad</span>')
        except Exception as e:
            self.status_label.set_markup(f'<span foreground="red">Misslyckades: {e}</span>')

    def on_test(self, _btn=None):
        name = self.current_sink
        self.status_label.set_markup('<span foreground="blue">Spelar upp testljud...</span>')
        def play():
            try:
                cmd = ["paplay", SOUND_FILE]
                if name:
                    cmd = ["paplay", "--device", name, SOUND_FILE]
                subprocess.run(cmd, timeout=10)
                GLib.idle_add(lambda: self.status_label.set_markup(
                    '<span foreground="green">Testljud spelades upp!</span>'
                ))
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                GLib.idle_add(lambda: self.status_label.set_markup(
                    f'<span foreground="red">Fel: {e}</span>'
                ))
        threading.Thread(target=play, daemon=True).start()


if __name__ == "__main__":
    win = AudioTester()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
