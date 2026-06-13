#!/usr/bin/env python3
"""
matrix-rain.py — GPU-accelerated Matrix digital rain via GTK GLArea + GLSL.
Requires: python-gobject, gtk-layer-shell  (both in Arch extra)
OpenGL is driven through libGL ctypes — no PyOpenGL needed.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GLib, Gdk
from gi.repository import GtkLayerShell

import argparse, ctypes, ctypes.util, sys, signal, time as _time

# ── load raw GL symbols ───────────────────────────────────────────────────────
_gl = ctypes.CDLL(ctypes.util.find_library("GL"))

def _glfn(name, restype, *argtypes):
    fn = getattr(_gl, name, None)
    if fn is None:
        raise RuntimeError(f"GL symbol not found: {name}")
    fn.restype  = restype
    fn.argtypes = list(argtypes)
    return fn

GLuint    = ctypes.c_uint
GLint     = ctypes.c_int
GLfloat   = ctypes.c_float
GLenum    = ctypes.c_uint
GLsizei   = ctypes.c_int
GLchar    = ctypes.c_char
GLboolean = ctypes.c_ubyte

glCreateShader      = _glfn("glCreateShader",      GLuint,  GLenum)
glShaderSource      = _glfn("glShaderSource",      None,    GLuint, GLsizei,
                             ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(GLint))
glCompileShader     = _glfn("glCompileShader",     None,    GLuint)
glGetShaderiv       = _glfn("glGetShaderiv",       None,    GLuint, GLenum, ctypes.POINTER(GLint))
glGetShaderInfoLog  = _glfn("glGetShaderInfoLog",  None,    GLuint, GLsizei,
                             ctypes.POINTER(GLsizei), ctypes.POINTER(GLchar))
glCreateProgram     = _glfn("glCreateProgram",     GLuint)
glAttachShader      = _glfn("glAttachShader",      None,    GLuint, GLuint)
glLinkProgram       = _glfn("glLinkProgram",       None,    GLuint)
glGetProgramiv      = _glfn("glGetProgramiv",      None,    GLuint, GLenum, ctypes.POINTER(GLint))
glGetProgramInfoLog = _glfn("glGetProgramInfoLog", None,    GLuint, GLsizei,
                             ctypes.POINTER(GLsizei), ctypes.POINTER(GLchar))
glUseProgram        = _glfn("glUseProgram",        None,    GLuint)
glGetUniformLocation= _glfn("glGetUniformLocation",GLint,   GLuint, ctypes.c_char_p)
glUniform1f         = _glfn("glUniform1f",         None,    GLint, GLfloat)
glUniform1i         = _glfn("glUniform1i",         None,    GLint, GLint)
glUniform2f         = _glfn("glUniform2f",         None,    GLint, GLfloat, GLfloat)
glUniform3f         = _glfn("glUniform3f",         None,    GLint, GLfloat, GLfloat, GLfloat)
glGenVertexArrays   = _glfn("glGenVertexArrays",   None,    GLsizei, ctypes.POINTER(GLuint))
glBindVertexArray   = _glfn("glBindVertexArray",   None,    GLuint)
glDrawArrays        = _glfn("glDrawArrays",        None,    GLenum, GLint, GLsizei)
glViewport          = _glfn("glViewport",          None,    GLint, GLint, GLsizei, GLsizei)
glClearColor        = _glfn("glClearColor",        None,    GLfloat, GLfloat, GLfloat, GLfloat)
glClear             = _glfn("glClear",             None,    GLenum)

GL_VERTEX_SHADER   = 0x8B31
GL_FRAGMENT_SHADER = 0x8B30
GL_COMPILE_STATUS  = 0x8B81
GL_LINK_STATUS     = 0x8B82
GL_TRIANGLES       = 0x0004
GL_COLOR_BUFFER_BIT= 0x4000
GL_TRUE            = 1

# ── GLSL shaders ──────────────────────────────────────────────────────────────
VERT_SRC = b"""
#version 330 core
void main() {
    // Full-screen triangle (no VBO needed)
    vec2 pos[3] = vec2[](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    gl_Position = vec4(pos[gl_VertexID], 0.0, 1.0);
}
"""

FRAG_SRC = b"""
#version 330 core

uniform float u_time;
uniform vec2  u_res;

uniform float u_cols;
uniform float u_rows;
uniform float u_trail;
uniform int   u_max_streams;
uniform float u_speed_min;
uniform float u_speed_range;
uniform float u_flicker;
uniform vec3  u_head_color;
uniform vec3  u_trail_color;

out vec4 fragColor;

float h1(float n) { return fract(sin(n * 127.1) * 43758.5453); }
float h2(float a, float b) { return h1(a + b * 57.0); }

#define NUM_CHARS   20
#define MAX_STREAMS_CAP 16

// 5x5 Katakana-inspired glyphs.
// Bit index = row*5 + col  (row 0 = top, col 0 = left).
const uint CHARS[20] = uint[20](
    18415150u,  // .###. / #...# / ##### / #...# / #...#
    14815373u,  // #.##. / ..#.. / ..#.. / ..#.. / .###.
    15255089u,  // #...# / #...# / #...# / #...# / .###.
    32651423u,  // ##### / ..#.. / .###. / ..#.. / #####
    15390382u,  // .###. / #.#.# / #.#.# / #.#.# / .###.
    22449589u,  // #.#.# / #.##. / ##... / #.##. / #.#.#
     4357279u,  // ##### / ..#.. / ##### / ..#.. / ..#..
    15895727u,  // ####. / #.#.. / ##... / #.#.. / ####.
    16293423u,  // ####. / #...# / ###.. / #...# / ####.
    32543807u,  // ##### / #.... / #.#.. / #.... / #####
     2239466u,  // .#.#. / ##### / .#.#. / ..#.. / .#...
    19544660u,  // ..#.# / .#..# / .###. / ..#.# / .#..#
     3494478u,  // .###. / .#..# / ..#.# / .#.#. / ##...
    32571071u,  // ##### / #.#.# / ##### / #.... / #####
     3420251u,  // ##.## / .#... / ..##. / ...#. / ##...
    18295790u,  // .###. / ##### / .#.#. / .###. / #...#
    10631327u,  // ##### / ..#.. / .###. / ..#.. / .#.#.
     2276021u,  // #.#.# / #.#.# / .###. / #.#.. / .#...
    14815391u,  // ##### / ..#.. / ..#.. / ..#.. / .###.
     2173124u   // ..#.. / .##.. / .#.#. / .#... / .#...
);

void main() {
    vec2 uv = gl_FragCoord.xy / u_res;
    uv.y    = 1.0 - uv.y;

    float col = floor(uv.x * u_cols);
    float row = floor(uv.y * u_rows);
    float cx  = fract(uv.x * u_cols);
    float cy  = fract(uv.y * u_rows);

    float total_bright = 0.0;
    bool  is_head      = false;

    int streams = clamp(u_max_streams, 1, MAX_STREAMS_CAP);
    for (int s = 0; s < streams; s++) {
        float fs     = float(s);
        float seed   = h2(col, fs * 13.0);
        float speed  = u_speed_min + seed * u_speed_range;
        float period = u_rows + u_trail + 10.0;
        float phase  = h2(col + 1.0, fs * 7.0) * period;
        float t      = mod(u_time * speed + phase, period);
        float head   = t - u_trail;
        float dist   = head - row;

        if (dist >= 0.0 && dist < u_trail) {
            float decay = exp(-dist / u_trail * 3.5);
            if (dist < 1.0) {
                total_bright = max(total_bright, 1.0);
                is_head = true;
            } else {
                total_bright = max(total_bright, decay);
            }
        }
    }

    if (total_bright < 0.005) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    float flicker = 0.88 + 0.12 * sin(u_time * 8.3 + col * 2.7 + row * 1.9);
    total_bright *= flicker;

    float char_t   = floor(u_time * u_flicker + h2(col, row) * 20.0);
    float cseed    = h2(col * 13.7 + row * 37.3, char_t);
    int   charIdx  = clamp(int(cseed * 20.0), 0, 19);
    uint  charData = CHARS[charIdx];

    // Sample 5x5 bitmap
    int px = clamp(int(cx * 5.0), 0, 4);
    int py = clamp(int(cy * 5.0), 0, 4);
    uint bit = (charData >> uint(py * 5 + px)) & 1u;
    float glyph_mask = float(bit) * 0.9 + 0.1;

    total_bright *= glyph_mask;

    if (total_bright < 0.005) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    vec3 col_rgb = is_head ? u_head_color : u_trail_color;
    fragColor = vec4(col_rgb * total_bright, 1.0);
}
"""


def _compile_shader(kind, src):
    shader = glCreateShader(kind)
    src_p  = ctypes.c_char_p(src)
    glShaderSource(shader, 1, ctypes.byref(src_p), None)
    glCompileShader(shader)
    status = GLint(0)
    glGetShaderiv(shader, GL_COMPILE_STATUS, ctypes.byref(status))
    if not status.value:
        buf = ctypes.create_string_buffer(2048)
        glGetShaderInfoLog(shader, 2048, None, buf)
        raise RuntimeError(f"Shader compile error:\n{buf.value.decode()}")
    return shader


def _build_program():
    vs  = _compile_shader(GL_VERTEX_SHADER,   VERT_SRC)
    fs  = _compile_shader(GL_FRAGMENT_SHADER, FRAG_SRC)
    prg = glCreateProgram()
    glAttachShader(prg, vs)
    glAttachShader(prg, fs)
    glLinkProgram(prg)
    status = GLint(0)
    glGetProgramiv(prg, GL_LINK_STATUS, ctypes.byref(status))
    if not status.value:
        buf = ctypes.create_string_buffer(2048)
        glGetProgramInfoLog(prg, 2048, None, buf)
        raise RuntimeError(f"Program link error:\n{buf.value.decode()}")
    return prg


class MatrixWindow(Gtk.Window):
    def __init__(self, cfg, monitor=None):
        super().__init__()
        self._cfg = cfg

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BACKGROUND)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP,    True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT,   True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT,  True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        if monitor:
            GtkLayerShell.set_monitor(self, monitor)

        self.set_decorated(False)

        self._gl_area = Gtk.GLArea()
        self._gl_area.set_required_version(3, 3)
        self._gl_area.set_auto_render(False)
        self._gl_area.connect("realize",  self._on_realize)
        self._gl_area.connect("render",   self._on_render)
        self._gl_area.connect("resize",   self._on_resize)
        self.add(self._gl_area)

        self._prog    = None
        self._vao     = None
        self._uniforms = {}
        self._width   = 1
        self._height  = 1
        self._t0      = _time.monotonic()

        self.show_all()
        interval_ms = max(1, int(1000 / cfg.fps))
        GLib.timeout_add(interval_ms, self._tick)

    def _tick(self):
        self._gl_area.queue_render()
        return True

    def _on_realize(self, area):
        area.make_current()
        if area.get_error():
            print("GLArea error on realize", file=sys.stderr)
            return
        try:
            self._prog = _build_program()
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return

        vao = GLuint(0)
        glGenVertexArrays(1, ctypes.byref(vao))
        self._vao = vao

        for name in ("u_time", "u_res", "u_cols", "u_rows", "u_trail",
                     "u_max_streams", "u_speed_min", "u_speed_range",
                     "u_flicker", "u_head_color", "u_trail_color"):
            self._uniforms[name] = glGetUniformLocation(self._prog, name.encode())

    def _on_resize(self, area, w, h):
        self._width  = max(w, 1)
        self._height = max(h, 1)

    def _on_render(self, area, ctx):
        if self._prog is None:
            return True

        cfg = self._cfg
        t   = _time.monotonic() - self._t0
        u   = self._uniforms

        glViewport(0, 0, GLsizei(self._width), GLsizei(self._height))
        glClearColor(GLfloat(0), GLfloat(0), GLfloat(0), GLfloat(1))
        glClear(GL_COLOR_BUFFER_BIT)

        glUseProgram(self._prog)
        glUniform1f(u["u_time"],        GLfloat(t))
        glUniform2f(u["u_res"],         GLfloat(self._width), GLfloat(self._height))
        glUniform1f(u["u_cols"],        GLfloat(cfg.cols))
        glUniform1f(u["u_rows"],        GLfloat(cfg.rows))
        glUniform1f(u["u_trail"],       GLfloat(cfg.trail))
        glUniform1i(u["u_max_streams"], GLint(cfg.streams))
        glUniform1f(u["u_speed_min"],   GLfloat(cfg.speed_min))
        glUniform1f(u["u_speed_range"], GLfloat(cfg.speed_range))
        glUniform1f(u["u_flicker"],     GLfloat(cfg.flicker))
        glUniform3f(u["u_head_color"],  GLfloat(cfg.head_color[0]),
                                        GLfloat(cfg.head_color[1]),
                                        GLfloat(cfg.head_color[2]))
        glUniform3f(u["u_trail_color"], GLfloat(cfg.trail_color[0]),
                                        GLfloat(cfg.trail_color[1]),
                                        GLfloat(cfg.trail_color[2]))

        glBindVertexArray(self._vao.value)
        glDrawArrays(GL_TRIANGLES, 0, 3)

        return True   # prevent GTK from clearing the buffer


def _color(s):
    try:
        parts = [float(x) for x in s.split(",")]
        if len(parts) != 3:
            raise ValueError
        return tuple(parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected 'r,g,b' floats, got: {s!r}")


def parse_args():
    p = argparse.ArgumentParser(description="Matrix digital rain wallpaper")
    p.add_argument("--cols",        type=float, default=120.0,
                   help="Grid columns — more = smaller glyphs (default: 120)")
    p.add_argument("--rows",        type=float, default=68.0,
                   help="Grid rows (default: 68)")
    p.add_argument("--trail",       type=float, default=20.0,
                   help="Trail length in rows (default: 20)")
    p.add_argument("--streams",     type=int,   default=3,
                   help="Streams per column, controls density (default: 3)")
    p.add_argument("--speed-min",   type=float, default=6.0,
                   help="Minimum fall speed (default: 6.0)")
    p.add_argument("--speed-range", type=float, default=12.0,
                   help="Fall speed variance added on top of min (default: 12.0)")
    p.add_argument("--flicker",     type=float, default=0.5,
                   help="Character swap rate in Hz (default: 0.5)")
    p.add_argument("--head-color",  type=_color, default=(0.4, 1.0, 0.5),
                   metavar="R,G,B",
                   help="Head glyph colour (default: 0.4,1.0,0.5 — bright green)")
    p.add_argument("--trail-color", type=_color, default=(0.0, 0.82, 0.25),
                   metavar="R,G,B",
                   help="Trail colour (default: 0.0,0.82,0.25)")
    p.add_argument("--fps",         type=int,   default=30,
                   help="Target frame rate (default: 30)")
    return p.parse_args()


def main():
    cfg = parse_args()

    signal.signal(signal.SIGINT,  lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

    display = Gdk.Display.get_default()
    if display is None:
        print("No Wayland display.", file=sys.stderr)
        sys.exit(1)

    n = display.get_n_monitors()
    windows = [MatrixWindow(cfg, monitor=display.get_monitor(i)) for i in range(n)]

    Gtk.main()


if __name__ == "__main__":
    main()
