#!/usr/bin/env python3
"""Renders keymap-custom/ from config/adv360.keymap with keymap_drawer.config.yaml:

- my_keymap.yaml / .svg / .png: the dark drawing, PNG on the theme's background
- cheatsheet.pdf: print-ready, the dark theme swapped for an ink-friendly light
  one, two layers per landscape page in the keymap's layer order; a footer stamps
  the commit so a printout can be matched to a build, and the author

Every key needs a label: a behavior keymap_drawer.config.yaml does not map is
drawn as its raw &name, so the render stops and names it instead.

Usage: bin/cheatsheet.py [letter|a4]   (make cheatsheet [PAPER=a4]; CI runs it too)
Needs uvx (runs keymap-drawer), rsvg-convert (librsvg), pdfunite or qpdf, PyYAML.
"""
import datetime
import html
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "keymap-custom"
CONFIG = ROOT / "keymap_drawer.config.yaml"
KEYMAP = ROOT / "config" / "adv360.keymap"
PAPER = {"letter": (11.0, 8.5), "a4": (297 / 25.4, 210 / 25.4)}  # landscape, inches
MARGIN = 0.4  # inches
DRAWER = "keymap-drawer==0.23.0"  # pinned; CI runs this script, so this is the only pin
BACKGROUND = "#1a1a2e"  # the dark theme's, for the PNG
AUTHOR = "euxener"
# keymap-drawer's light theme, keys a shade darker so they hold up on paper
PRINT_STYLE = """
text { font-family: "JetBrains Mono", "JetBrainsMono Nerd Font", "JetBrainsMono NF", monospace; }
svg.keymap { fill: #1f2328; }
rect.key { fill: #e1e5ea; }
rect.key, rect.combo { stroke: #8c959f; }
rect.combo, rect.combo-separate { fill: #b9cbe6; }
rect.key.held { fill: #a9b0b8; }
text.hold { fill: #a0001c; }
text.label { font-size: 18px; }
text.layer-activator { text-decoration: none; }
/* one color per layer: its keys on Base and its held thumbs on its own drawing
   (after .held, same specificity). Dark theme: keymap_drawer.config.yaml */
rect.key.layer1 { fill: #f0c96e; }
rect.key.layer2 { fill: #c3a8ea; }
rect.key.layer3 { fill: #ee9fac; }
rect.key.layer4 { fill: #92d1a3; }
rect.key.layer5 { fill: #8fd0da; }
"""


def drawer(config, *args):
    cmd = ["uvx", "-q", "--from", DRAWER, "keymap", "-c", str(config), *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


HAIR_SPACE = "\u200a"
SYMBOLS = re.compile(r"(?<=[-=<>!|:/*&~.+_#$%^?\\])(?=[-=<>!|:/*&~.+_#$%^?\\])")


def unligate(text):
    """A hair space between symbol characters. JetBrains Mono's ligatures draw -> as
    an arrow key and === as a triple bar. librsvg ignores the CSS that turns them off,
    and HarfBuzz skips invisible joiners (U+200C) when it matches them; a hair space
    is a real glyph, so it breaks them, at the cost of a sliver of space"""
    return SYMBOLS.sub(HAIR_SPACE, text)


def draw(config, keymap, *args):
    # keymap-drawer wraps each $$mdi:...$$ icon in an <svg id="mdi:..."> with no
    # viewBox; browsers cope, librsvg draws nothing. MDI icons are on a 24 grid.
    svg = drawer(config, "draw", str(keymap), *args)
    svg = re.sub(r'<svg id="(mdi:[^"]+)">', r'<svg id="\1" viewBox="0 0 24 24">', svg)
    # legends only: text and tspan content, unescaped first so &amp; stays one character
    return re.sub(r"(<(?:text|tspan)\b[^>]*>)([^<]+)",
                  lambda m: m.group(1) + html.escape(unligate(html.unescape(m.group(2))), quote=False), svg)


def svg_size(svg):
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', svg)
    if not m:
        sys.exit("keymap-drawer output has no svg width/height")
    return float(m.group(1)), float(m.group(2))


def unlabeled(keymap_yaml):
    """(layer, raw name) for every key drawn as a raw &behavior: no label in the config.
    & or && alone are labels (AMPS, pm_and)"""
    layers = yaml.safe_load(keymap_yaml)["layers"]
    raw = []
    for layer, keys in layers.items():
        for key in keys:
            legends = key.values() if isinstance(key, dict) else [key]
            raw += [(layer, v) for v in legends if isinstance(v, str) and re.match(r"&[a-z_]", v, re.I)]
    return raw


def pages(keymap_yaml):
    """Two layers per page, in the keymap's order (layer 0 and 1, 2 and 3, ...)"""
    names = list(yaml.safe_load(keymap_yaml)["layers"])
    return [tuple(names[i:i + 2]) for i in range(0, len(names), 2)]


def mark_layer_keys(keymap_yaml):
    """Color every Base key that reaches a layer with that layer's color (class
    layer<N>, N its number), and shade the keys that hold it on its own drawing in
    the same color. keymap-drawer shades only the first of a pair; each thumb
    cluster has one. A Base key labelled with a layer's bare name is an &mo; an
    &tog carries a 'toggle' under the name: on its layer the same key, untouched
    there, toggles it off, so it is drawn as itself in the layer's color"""
    keymap = yaml.safe_load(keymap_yaml)
    layers = keymap["layers"]
    names = list(layers)
    base = layers[names[0]]
    for pos, key in enumerate(base):
        name = key.get("t") if isinstance(key, dict) else key
        if name not in names[1:]:
            continue
        color = f"layer{names.index(name)}"
        base[pos] = {**(key if isinstance(key, dict) else {"t": key}), "type": color}
        if isinstance(key, str):
            # drawn empty like keymap-drawer's own: the key is down, its binding here never fires
            layers[name][pos] = {"type": f"held {color}"}
        elif layers[name][pos] == {"t": "▽", "type": "trans"}:
            layers[name][pos] = base[pos]
    return yaml.safe_dump(keymap, allow_unicode=True, sort_keys=False)


def parse(config):
    keymap_yaml = drawer(config, "parse", "-z", str(KEYMAP))
    raw = unlabeled(keymap_yaml)
    if raw:
        sys.exit("no label in keymap_drawer.config.yaml for:\n"
                 + "\n".join(f"  {name} ({layer})" for layer, name in raw))
    return mark_layer_keys(keymap_yaml)


def render_drawing():
    yaml_out, svg_out = OUT / "my_keymap.yaml", OUT / "my_keymap.svg"
    yaml_out.write_text(parse(CONFIG))
    svg_out.write_text(draw(CONFIG, yaml_out))
    subprocess.run(["rsvg-convert", "-b", BACKGROUND, str(svg_out), "-o", str(OUT / "my_keymap.png")], check=True)
    print("keymap-custom/my_keymap.{yaml,svg,png}")


def render_cheatsheet(paper):
    page_w, page_h = PAPER[paper]
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "uncommitted"
    # everything the drawing comes from: a page drawn from uncommitted work says so
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "config",
                            "keymap_drawer.config.yaml", "bin/cheatsheet.py"],
                           capture_output=True, text=True).stdout.strip()
    stamp = f"Advantage 360 · {sha}{'+dirty' if dirty else ''} · {datetime.date.today()} · {AUTHOR}"

    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["draw_config"]["svg_extra_style"] = PRINT_STYLE
    cfg["draw_config"]["footer_text"] = stamp

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        config = tmp / "print.yaml"
        config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
        keymap = tmp / "keymap.yaml"
        keymap_yaml = parse(config)
        keymap.write_text(keymap_yaml)
        page_layers = pages(keymap_yaml)
        assert [n for page in page_layers for n in page] == list(yaml.safe_load(keymap_yaml)["layers"])

        pdf_pages = []
        for i, layers in enumerate(page_layers):
            svg = draw(config, keymap, "-s", *layers)
            w, h = svg_size(svg)
            # fit inside the margins, keep the aspect ratio, centre on the page
            scale = min((page_w - 2 * MARGIN) / w, (page_h - 2 * MARGIN) / h)
            left, top = (page_w - w * scale) / 2, (page_h - h * scale) / 2
            src, out = tmp / f"p{i}.svg", tmp / f"p{i}.pdf"
            src.write_text(svg)
            subprocess.run(["rsvg-convert", "-f", "pdf", "-a",
                            "--page-width", f"{page_w}in", "--page-height", f"{page_h}in",
                            "--left", f"{left:.3f}in", "--top", f"{top:.3f}in",
                            "-w", f"{w * scale:.3f}in", "-h", f"{h * scale:.3f}in",
                            "-o", str(out), str(src)], check=True)
            pdf_pages.append(out)

        merge(pdf_pages, OUT / "cheatsheet.pdf")
    print(f"keymap-custom/cheatsheet.pdf: {len(page_layers)} pages, {paper} landscape, {stamp}")


def merge(pages, target):
    """Join single-page PDFs. pdfunite (poppler) or qpdf, whichever is installed."""
    for cmd in (["pdfunite", *map(str, pages), str(target)],
                ["qpdf", "--empty", "--pages", *map(str, pages), "--", str(target)]):
        try:
            subprocess.run(cmd, check=True)
            return
        except FileNotFoundError:
            continue
    sys.exit("needs pdfunite (poppler) or qpdf to join the pages")


def main():
    paper = sys.argv[1] if len(sys.argv) > 1 else "letter"
    if paper not in PAPER:
        sys.exit(f"usage: {sys.argv[0]} [letter|a4]")
    render_drawing()
    render_cheatsheet(paper)


if __name__ == "__main__":
    main()
