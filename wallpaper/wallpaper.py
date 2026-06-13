#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, WebKit2, GtkLayerShell, Gdk
import os, signal

HTML = "file://" + os.path.expanduser("~/.config/hypr/wallpaper/matrix.html")

class WallpaperWindow(Gtk.Window):
    def __init__(self, uri, monitor=None):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BACKGROUND)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        if monitor:
            GtkLayerShell.set_monitor(self, monitor)
        self.set_decorated(False)

        wv = WebKit2.WebView()
        wv.set_background_color(Gdk.RGBA(0, 0, 0, 1))
        wv.load_uri(uri)
        self.add(wv)
        self.show_all()

def main():
    signal.signal(signal.SIGINT,  lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    display = Gdk.Display.get_default()
    windows = [WallpaperWindow(HTML, monitor=display.get_monitor(i))
               for i in range(display.get_n_monitors())]
    Gtk.main()

if __name__ == "__main__":
    main()
