#!/usr/bin/env python3
"""Checks for bin/cheatsheet.py and its output: python3 bin/test_cheatsheet.py
(needs uvx, PyYAML, pdftotext, and for one scratch render rsvg-convert and pdfunite
or qpdf). Run after bin/cheatsheet.py: the last checks hold the committed
keymap-custom/ files to the keymap and config as they are now"""
import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # never a __pycache__ in the tree
import cheatsheet  # noqa: E402

FAKE = """
layers:
  Base: [a, '&tm_zoom', {t: '&nv_save', h: x}, {t: Zoom, h: tmux}, '&&', '&']
  Num: [b]
  Nav: [c]
"""

# a raw &name is caught as a bare key and as a legend; a labelled key is not
assert cheatsheet.unlabeled(FAKE) == [("Base", "&tm_zoom"), ("Base", "&nv_save")], cheatsheet.unlabeled(FAKE)
# pages follow the layer order, an odd last layer gets a page of its own
assert cheatsheet.pages(FAKE) == [("Base", "Num"), ("Nav",)], cheatsheet.pages(FAKE)

# Base keys take their layer's color, a toggle too; both keys that hold a layer are
# shaded in it on that layer's drawing, and a transparent toggle there shows itself
HELD = """
layers:
  Base: [Nav, Nav, {t: Nav, h: toggle}, x, Sym]
  Nav: [{t: ▽, type: trans}, {type: held}, {t: ▽, type: trans}, y, z]
  Sym: [a, b, c, d, {type: held}]
"""
marked = cheatsheet.yaml.safe_load(cheatsheet.mark_layer_keys(HELD))["layers"]
types = {n: [k.get("type") if isinstance(k, dict) else None for k in keys] for n, keys in marked.items()}
assert types["Base"] == ["layer1", "layer1", "layer1", None, "layer2"], types
assert types["Nav"] == ["held layer1", "held layer1", "layer1", None, None], types  # toggle: its way out
assert types["Sym"] == [None, None, None, None, "held layer2"], types
assert marked["Base"][2] == {"t": "Nav", "h": "toggle", "type": "layer1"}, marked["Base"][2]

# a layer-tap (tap over the layer's name) takes its layer's color and is shaded held
# there; a conditional layer shades the keys that hold each of its if-layers
TAPS = """
layers:
  Base: [{t: ⌫, h: Nav}, {t: ␣, h: Sym}, {t: A, h: ⌃ Ctrl}, x]
  Nav: [{type: held}, {t: ▽, type: trans}, a, b]
  Sym: [{t: ▽, type: trans}, {type: held}, c, d]
  Mod: ['', '', e, f]
"""
marked = cheatsheet.yaml.safe_load(cheatsheet.mark_layer_keys(TAPS, [((1, 2), 3)]))["layers"]
assert marked["Base"][:3] == [{"t": "⌫", "h": "Nav", "type": "layer1"}, {"t": "␣", "h": "Sym", "type": "layer2"},
                              {"t": "A", "h": "⌃ Ctrl"}], marked["Base"]  # a home-row mod is no layer key
assert marked["Nav"][0] == {"type": "held layer1"} and marked["Sym"][1] == {"type": "held layer2"}, marked
assert marked["Mod"][:2] == [{"type": "held layer1"}, {"type": "held layer2"}], marked["Mod"]
assert cheatsheet.conditional_layers("x { if-layers = <3 5>;\n then-layer = <4>; };") == [((3, 5), 4)]
assert cheatsheet.conditional_layers("no conditional layers") == []

# ligatures broken between symbols only, & and arrows in words untouched
assert cheatsheet.unligate("->") == "-\u200a>" and cheatsheet.unligate("===") == "=\u200a=\u200a="
assert cheatsheet.unligate("Split→") == "Split→" and cheatsheet.unligate("a-b") == "a-b"

# the color legend goes next to the heading of a layer with macro keys, and only there
SVG = ('<text x="0" y="10" class="label" id="A">A:</text><rect class="key macro tmux"/>'
       '<text x="0" y="10" class="label" id="B">B:</text><rect class="key"/>')
out = cheatsheet.legend(SVG)
assert out.count('class="legend tmux"') == 1, out
assert out.index('class="legend tmux"') < out.index('id="B"'), out

# a key's bottom line moves up, a two-line label above it a little; keys without one stay
ONE = '<g transform="translate(1, 1)" class="key k"><text x="0" y="0" class="key tap">A</text><text x="0" y="26" class="key hold">b</text></g>'
TWO = '<g transform="translate(1, 1)" class="key k"><text x="0" y="0" class="key tap">\n<tspan x="0" dy="-0.6em">A</tspan></text><text x="0" y="26" class="key hold">b</text></g>'
BARE = '<g transform="translate(1, 1)" class="key k"><text x="0" y="0" class="key tap">\n<tspan x="0">A</tspan></text></g>'
assert 'y="21" class="key hold"' in cheatsheet.tighten(ONE) and 'y="0" class="key tap"' in cheatsheet.tighten(ONE)
assert 'y="21" class="key hold"' in cheatsheet.tighten(TWO) and 'y="-2" class="key tap"' in cheatsheet.tighten(TWO)
assert cheatsheet.tighten(BARE) == BARE
SHRUNK = '<g transform="translate(1, 1)" class="key k"><text x="0" y="0" class="key tap"><tspan style="font-size: 75%">Function</tspan></text><text x="0" y="26" class="key hold">b</text></g>'
assert 'y="18" class="key hold"' in cheatsheet.tighten(SHRUNK) and 'y="0" class="key tap"' in cheatsheet.tighten(SHRUNK)
# modifier icons get a larger tspan, the name stays as is
assert cheatsheet.enlarge_icons('<text x="0" y="0" class="key hold">⌃ Ctrl</text>') == '<text x="0" y="0" class="key hold"><tspan class="modicon ctrl">⌃</tspan> Ctrl</text>'
assert cheatsheet.enlarge_icons('<text x="0" y="0" class="key hold">⌥ Alt</text>') == '<text x="0" y="0" class="key hold"><tspan class="modicon">⌥</tspan> Alt</text>'

# a render swaps files in: a reader holding the old one (git diff, mmapped) still sees
# all of it, not a truncated file that SIGBUSes it; a tool that dies halfway leaves
# no trace, and the temp keeps the suffix the tool picks its format by
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp) / "my_keymap.png"
    path.write_text("old drawing, longer than the new one")
    with open(path) as held:
        with cheatsheet.replacing(path) as new:
            assert new.suffix == ".png" and new.parent == path.parent, new
            new.write_text("new")
        assert held.read() == "old drawing, longer than the new one", "rewritten in place"
    assert path.read_text() == "new"
    try:
        with cheatsheet.replacing(path) as new:
            subprocess.run([sys.executable, "-c", "import sys; open(sys.argv[1], 'w').write('half'); sys.exit(1)",
                            str(new)], check=True)
        assert False, "a failed tool went unnoticed"
    except subprocess.CalledProcessError:
        pass
    assert path.read_text() == "new" and os.listdir(tmp) == ["my_keymap.png"], os.listdir(tmp)

# the real keymap: every key labelled, pages in layer order
real = cheatsheet.drawer(cheatsheet.CONFIG, "parse", "-z", str(cheatsheet.KEYMAP))
assert cheatsheet.unlabeled(real) == [], cheatsheet.unlabeled(real)
assert cheatsheet.pages(real) == [("Base (Colemak-DH)", "Excel"), ("Num+Fn", "Nav"), ("Sym", "Mod")], cheatsheet.pages(real)
# the layer keys found on Base are the keymap's: the thumb layer-taps by their hold
# label, and Mod is shaded with them, Nav + Sym held (a reformatted conditional block
# the regex no longer reads would drop that shading with every other check still green)
assert cheatsheet.conditional_layers(cheatsheet.KEYMAP.read_text()) == [((3, 4), 5)]
marked = cheatsheet.yaml.safe_load(cheatsheet.parse(cheatsheet.CONFIG))["layers"]
base = marked["Base (Colemak-DH)"]
taps = {i: k["h"] for i, k in enumerate(base) if isinstance(k, dict) and str(k.get("type", "")).startswith("layer") and k.get("h") not in (None, "toggle")}
assert taps == {65: "Nav", 66: "Num+Fn", 70: "Sym"}, taps
assert marked["Mod"][65] == {"type": "held layer3"} and marked["Mod"][70] == {"type": "held layer4"}, (marked["Mod"][65], marked["Mod"][70])
# layer order holds whatever the numbers become: a conditional layer sits above the
# layers that turn it on (below Sym, Mod's keys never fired), and a toggled layer
# leaves the other layers' thumb holds alone (but the KEPT overlaps below)
assert all(then > max(ifs) for ifs, then in cheatsheet.conditional_layers(cheatsheet.KEYMAP.read_text()))
toggled = {k["t"] for k in base if isinstance(k, dict) and k.get("h") == "toggle"}
assert toggled == {"Excel", "Num+Fn", "Nav"}, toggled  # Nav: the lock
# ...the other layers' Base layer keys too: their holds (36/37 Excel) and toggles (6/7)
layer_keys = {**taps, **{pos: k if isinstance(k, str) else k["t"] for pos, k in enumerate(base)
                         if (k if isinstance(k, str) else k.get("t")) in toggled | {"Excel"} and pos not in taps}}
# chosen on purpose: the numpad's 0 on Space (Num toggled types 0 there, Sym waits), and
# Space a plain Space on Nav (Bspc then Space never lands in Mod; Mod is Space then Bspc)
KEPT = {("Num+Fn", 70), ("Nav", 70)}
for name in toggled:
    shadowed = [pos for pos, hold in layer_keys.items()
                if hold != name and (name, pos) not in KEPT and marked[name][pos] != {"t": "▽", "type": "trans"}]
    assert not shadowed, f"{name}, toggled on, hides the thumb holds at {shadowed}"
# ...and binds its own hold keys: falling through to the &mo, a hold there turns the
# toggle off on release. Read from the keymap source: keymap-drawer draws a layer's
# own hold key as held whatever is bound under it
names = list(marked)
source = {name: re.findall(r"&\w+(?:\s+(?!&)[^\s&]+)*", body) for name, body in re.findall(
    r'display-name = "([^"]+)";\s*bindings = <(.*?)>;', cheatsheet.KEYMAP.read_text(), re.S)}
assert list(source) == names and all(len(b) == len(source[names[0]]) for b in source.values()), list(source)
for name in toggled:
    own = [pos for pos, b in enumerate(source[names[0]]) if re.fullmatch(rf"&(mo|lt_th|lt_sp) {names.index(name)}\b.*", b)]
    assert own and all(source[name][pos] != "&trans" for pos in own), (name, own, [source[name][p] for p in own])
# every toggle has its way out: on its own layer the toggle key falls through to itself
for pos, k in enumerate(source[names[0]]):
    if (m := re.fullmatch(r"&tog (\d+)", k)):
        assert source[names[int(m.group(1))]][pos] == "&trans", (names[int(m.group(1))], pos, "no way out of the toggle")
# Mod's only way in is Space (Sym) held, then Bspc: Sym passes Bspc through to the Nav hold,
# and binds nothing at the lock key, or a tap there adds Nav to Sym and opens Mod mid-symbols
assert source["Sym"][65] == "&trans" and source["Sym"][52] == "&none", (source["Sym"][65], source["Sym"][52])
# the two kept overlaps, as chosen: 0 on Space under Num, a plain Space under Nav
assert source["Num+Fn"][70] == "&kp KP_N0" and source["Nav"][70] == "&kp SPACE", (source["Num+Fn"][70], source["Nav"][70])
# Mod, on top, passes nothing through: no Sym key under a Mod gap, no thumb brushed mid-chord
assert "&trans" not in source["Mod"], [i for i, b in enumerate(source["Mod"]) if b == "&trans"]
# Space is the layer-tap without quick-tap: tap then hold reaches Sym, not repeated spaces
keymap_text = cheatsheet.KEYMAP.read_text()
assert source[names[0]][70] == "&lt_sp 4 SPACE", source[names[0]][70]
assert re.search(r"lt_sp: [^}]*quick-tap-ms = <0>;", keymap_text), "lt_sp lost quick-tap-ms = <0>"
# the extended NKRO report stays: turning it off changes the key report, every Bluetooth host re-pairs
defconfig = (cheatsheet.ROOT / "config/boards/arm/adv360/adv360_left_defconfig").read_text()
assert re.search(r"^CONFIG_ZMK_HID_KEYBOARD_EXTENDED_REPORT=y$", defconfig, re.M), "extended NKRO report turned off: every Bluetooth host must re-pair"

# keymap-custom/ is consistent: drawing yaml = a fresh parse, svg and pdf drawn from it
out = cheatsheet.OUT
fresh = cheatsheet.yaml.safe_load(cheatsheet.mark_layer_keys(real, cheatsheet.conditional_layers(cheatsheet.KEYMAP.read_text())))
drawn = cheatsheet.yaml.safe_load((out / "my_keymap.yaml").read_text())
assert drawn == fresh, "keymap-custom/my_keymap.yaml is stale: run bin/cheatsheet.py"
svg = (out / "my_keymap.svg").read_text()
layers = list(fresh["layers"])
assert all(f">{name}:<" in svg for name in layers), "my_keymap.svg is missing a layer"
assert not re.search(r">&amp;[a-z_]", svg, re.I), "my_keymap.svg draws a raw &name"
assert svg.count('class="legend tmux"') == 1 and "legend nvim" not in svg, "legend missing"
assert (out / "my_keymap.png").stat().st_mtime >= (out / "my_keymap.svg").stat().st_mtime - 5, "my_keymap.png older than its svg"
# index.html: a tab and two inlined drawings per layer (dark, light), in order, each the
# same keys as that layer of my_keymap.svg, and nothing fetched from anywhere
page = (out / "index.html").read_text()
tabs = re.findall(r'<button role="tab"[^>]*><kbd>(\d+)</kbd>([^<]*)</button>', page)
assert tabs == [(str(i + 1), cheatsheet.html.escape(n)) for i, n in enumerate(layers)], tabs
IMG = r'<img class="{}" alt="([^"]*) layer" src="data:image/svg\+xml;base64,([^"]+)">'
images = re.findall(r'<div id="layer\d+" role="tabpanel" aria-labelledby="tab\d+"(?: hidden)?>'
                    + IMG.format("dark") + IMG.format("light") + "</div>", page)
# before the script runs, only the first layer shows
assert re.findall(r'aria-labelledby="tab(\d+)"( hidden)?>', page) == [(str(i), " hidden" if i else "") for i in range(len(layers))]
assert [(d, l) for d, _, l, _ in images] == [(cheatsheet.html.escape(n),) * 2 for n in layers], [(d, l) for d, _, l, _ in images]
assert not re.search(r'(?:src|href)="(?!data:)', page) and "<link" not in page and "url(" not in page, "index.html fetches something"
sections = re.split(r'<text x="0" y="10" class="label"', svg)[1:]
light_key = re.search(r"rect\.key \{ fill: (#[0-9a-f]+); \}", cheatsheet.PRINT_STYLE).group(1)  # the light theme's key fill
def words(drawing):
    return sorted(w for w in re.findall(r">([^<>]+)<", drawing) if w.strip())
for (_, dark, _, light), section in zip(images, sections):
    for data, background in ((dark, True), (light, False)):
        one = cheatsheet.base64.b64decode(data).decode()
        assert not re.search(r'(?:src|href)="(?!#|data:)|@import|url\((?!#)', one), "a drawing in index.html fetches something"
        assert words(re.split(r'<text x="0" y="10" class="label"', one)[1]) == words(section), "index.html is stale: run bin/cheatsheet.py"
        # the dark drawing carries the dark theme's background, the light one the print style
        assert (cheatsheet.BACKGROUND in one) == background and (light_key in one) != background, "a drawing has the other theme"
        assert (cheatsheet.PRINT_STYLE.strip() in one) != background, "a light drawing is stale or a dark one has the light style"
# the theme switch: a button and t, the system's theme until one is chosen, light vars for both cases
assert '<button id="theme" type="button">' in page
assert 'if (e.key.toLowerCase() === "t") { if (!e.repeat) switchTheme(); }' in page  # Caps Lock too, a held t once
# the light variables apply when chosen, or by the system only while nothing is chosen
L = cheatsheet.PAGE_LIGHT
assert f':root[data-theme="light"] {{ {L} }}' in page, "the chosen light theme's selector changed"
assert f'@media (prefers-color-scheme: light) {{ :root:not([data-theme]) {{ {L} }} }}' in page, "the system light rule overrides a choice"
assert page.count('"kinesis-360-theme"') == 2, "the head reads and the switch writes different keys"
# which drawing shows: dark by default, light under the light variables, nothing else
assert "--dark: block; --light: none;" in page and "--dark: none; --light: block;" in cheatsheet.PAGE_LIGHT
assert "img.dark { display: var(--dark); }" in page and "img.light { display: var(--light); }" in page
# a saved theme applies before the drawings are parsed, and only a real one
head = page.split("</head>")[0]
assert 'localStorage.getItem("kinesis-360-theme")' in head and 's === "light" || s === "dark"' in head
assert (out / "index.html").stat().st_mtime >= (out / "my_keymap.yaml").stat().st_mtime - 5, "index.html older than its drawing"

text = subprocess.run(["pdftotext", "-layout", str(out / "cheatsheet.pdf"), "-"],
                      capture_output=True, text=True, check=True).stdout
pdf_pages = [p for p in text.split("\f") if p.strip()]
assert len(pdf_pages) == len(cheatsheet.pages(real)), len(pdf_pages)
for page, names in zip(pdf_pages, cheatsheet.pages(real)):
    heads = [n for n in layers if f"{n}:" in page]
    assert heads == list(names), (heads, names)
    assert cheatsheet.AUTHOR in page.strip().splitlines()[-1], "no author in the footer"

# every output of a real render is swapped in, none rewritten: a file held open
# before the render still reads as it was. Renders into a scratch OUT, not the tree
names = ["my_keymap.yaml", "my_keymap.svg", "my_keymap.png", "index.html", "cheatsheet.pdf"]
with tempfile.TemporaryDirectory() as tmp:
    scratch = pathlib.Path(tmp)
    for name in names:
        (scratch / name).write_text("old")
    held = [open(scratch / name, "rb") for name in names]
    try:
        cheatsheet.OUT = scratch  # out is still the real one, from the checks above
        with contextlib.redirect_stdout(io.StringIO()):
            cheatsheet.render_drawing()
            cheatsheet.render_page(scratch / "my_keymap.yaml")
            cheatsheet.render_cheatsheet("letter")
        stale = [name for name, f in zip(names, held) if f.read() != b"old"]
    finally:
        for f in held:
            f.close()
        cheatsheet.OUT = out
    assert not stale, f"rewritten in place: {stale}"
    assert sorted(os.listdir(scratch)) == sorted(names), os.listdir(scratch)
    assert all((scratch / name).stat().st_size > 100 for name in names), "a render output is empty"
print("ok")
