#!/usr/bin/env python3
"""Checks for bin/cheatsheet.py and its output: python3 bin/test_cheatsheet.py
(needs uvx, PyYAML, pdftotext). Run after bin/cheatsheet.py: the last checks hold
the committed keymap-custom/ files to the keymap and config as they are now"""
import pathlib
import re
import subprocess
import sys

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
assert (out / "my_keymap.png").stat().st_mtime >= (out / "my_keymap.svg").stat().st_mtime - 5, "my_keymap.png older than its svg"
text = subprocess.run(["pdftotext", "-layout", str(out / "cheatsheet.pdf"), "-"],
                      capture_output=True, text=True, check=True).stdout
pdf_pages = [p for p in text.split("\f") if p.strip()]
assert len(pdf_pages) == len(cheatsheet.pages(real)), len(pdf_pages)
for page, names in zip(pdf_pages, cheatsheet.pages(real)):
    heads = [n for n in layers if f"{n}:" in page]
    assert heads == list(names), (heads, names)
    assert cheatsheet.AUTHOR in page.strip().splitlines()[-1], "no author in the footer"
print("ok")
