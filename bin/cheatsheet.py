#!/usr/bin/env python3
"""Renders keymap-custom/ from config/adv360.keymap with keymap_drawer.config.yaml:

- my_keymap.yaml / .svg / .png: the dark drawing, PNG on the theme's background
- cheatsheet.pdf: print-ready, the dark theme swapped for an ink-friendly light
  one, two layers per landscape page; a footer stamps the commit so a printout
  can be matched to a build

Usage: bin/cheatsheet.py [letter|a4]   (make cheatsheet [PAPER=a4]; CI runs it too)
Needs uvx (runs keymap-drawer), rsvg-convert (librsvg), pdfunite or qpdf, PyYAML.
"""
import datetime
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
DRAWER = "keymap-drawer==0.23.0"  # same version as .github/workflows/draw-keymap.yml
BACKGROUND = "#1a1a2e"  # the dark theme's, for the PNG
# Most used first; the combo is drawn inline on the Base layer
PAGES = [("Base (Colemak-DH)", "Sym"), ("Num+Fn", "Nav"), ("Excel", "Mod")]
PRINT_STYLE = """
text { font-family: "JetBrains Mono", "JetBrainsMono Nerd Font", "JetBrainsMono NF", monospace; }
rect.key.held { fill: #c8c8c8; }
text.hold { fill: #a0001c; }
text.label { font-size: 18px; }
"""


def drawer(config, *args):
    cmd = ["uvx", "-q", "--from", DRAWER, "keymap", "-c", str(config), *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def draw(config, keymap, *args):
    # keymap-drawer wraps each $$mdi:...$$ icon in an <svg id="mdi:..."> with no
    # viewBox; browsers cope, librsvg draws nothing. MDI icons are on a 24 grid.
    svg = drawer(config, "draw", str(keymap), *args)
    return re.sub(r'<svg id="(mdi:[^"]+)">', r'<svg id="\1" viewBox="0 0 24 24">', svg)


def svg_size(svg):
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', svg)
    if not m:
        sys.exit("keymap-drawer output has no svg width/height")
    return float(m.group(1)), float(m.group(2))


def render_drawing():
    yaml_out, svg_out = OUT / "my_keymap.yaml", OUT / "my_keymap.svg"
    yaml_out.write_text(drawer(CONFIG, "parse", "-z", str(KEYMAP)))
    svg_out.write_text(draw(CONFIG, yaml_out))
    subprocess.run(["rsvg-convert", "-b", BACKGROUND, str(svg_out), "-o", str(OUT / "my_keymap.png")], check=True)
    print("keymap-custom/my_keymap.{yaml,svg,png}")


def render_cheatsheet(paper):
    page_w, page_h = PAPER[paper]
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "uncommitted"
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "config"],
                           capture_output=True, text=True).stdout.strip()
    stamp = f"Advantage 360 · {sha}{'+dirty' if dirty else ''} · {datetime.date.today()}"

    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["draw_config"]["svg_extra_style"] = PRINT_STYLE
    cfg["draw_config"]["footer_text"] = stamp
    # the combo inline on its keys, not a separate diagram that halves the page
    cfg["draw_config"]["separate_combo_diagrams"] = False

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        config = tmp / "print.yaml"
        config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
        keymap = tmp / "keymap.yaml"
        keymap.write_text(drawer(config, "parse", "-z", str(KEYMAP)))

        pdf_pages = []
        for i, layers in enumerate(PAGES):
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
    print(f"keymap-custom/cheatsheet.pdf: {len(PAGES)} pages, {paper} landscape, {stamp}")


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
