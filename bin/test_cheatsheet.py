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

# ligatures broken between symbols only, & and arrows in words untouched
assert cheatsheet.unligate("->") == "-\u200a>" and cheatsheet.unligate("===") == "=\u200a=\u200a="
assert cheatsheet.unligate("Split→") == "Split→" and cheatsheet.unligate("a-b") == "a-b"

# the color legend goes next to the heading of a layer with macro keys, and only there
SVG = ('<text x="0" y="10" class="label" id="A">A:</text><rect class="key macro nvim"/>'
       '<text x="0" y="10" class="label" id="B">B:</text><rect class="key"/>')
out = cheatsheet.legend(SVG)
assert out.count('class="legend nvim"') == 1 and "tmux" not in out, out
assert out.index('class="legend nvim"') < out.index('id="B"'), out

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
assert cheatsheet.pages(real) == [("Base (Colemak-DH)", "Num+Fn"), ("Nav", "Mod"), ("Excel", "Sym")], cheatsheet.pages(real)

# keymap-custom/ is consistent: drawing yaml = a fresh parse, svg and pdf drawn from it
out = cheatsheet.OUT
fresh = cheatsheet.yaml.safe_load(cheatsheet.mark_layer_keys(real))
drawn = cheatsheet.yaml.safe_load((out / "my_keymap.yaml").read_text())
assert drawn == fresh, "keymap-custom/my_keymap.yaml is stale: run bin/cheatsheet.py"
svg = (out / "my_keymap.svg").read_text()
layers = list(fresh["layers"])
assert all(f">{name}:<" in svg for name in layers), "my_keymap.svg is missing a layer"
assert not re.search(r">&amp;[a-z_]", svg, re.I), "my_keymap.svg draws a raw &name"
assert svg.count('class="legend nvim"') == 1 and svg.count('class="legend tmux"') == 1, "legend missing"
assert (out / "my_keymap.png").stat().st_mtime >= (out / "my_keymap.svg").stat().st_mtime - 5, "my_keymap.png older than its svg"
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
names = ["my_keymap.yaml", "my_keymap.svg", "my_keymap.png", "cheatsheet.pdf"]
with tempfile.TemporaryDirectory() as tmp:
    scratch = pathlib.Path(tmp)
    for name in names:
        (scratch / name).write_text("old")
    held = [open(scratch / name, "rb") for name in names]
    try:
        cheatsheet.OUT = scratch  # out is still the real one, from the checks above
        with contextlib.redirect_stdout(io.StringIO()):
            cheatsheet.render_drawing()
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
