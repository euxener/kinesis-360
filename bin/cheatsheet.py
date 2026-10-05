#!/usr/bin/env python3
"""Print-ready cheatsheet of config/adv360.keymap: the keymap-drawer config with
its dark theme swapped for an ink-friendly light one, two layers per landscape
page, one PDF. A footer stamps the commit so a printout can be matched to a build.

Usage: bin/cheatsheet.py [letter|a4]   ->  keymap-custom/cheatsheet.pdf
Needs uvx (runs keymap-drawer), rsvg-convert (librsvg) and PyYAML.
"""
import datetime
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAPER = {"letter": (11.0, 8.5), "a4": (297 / 25.4, 210 / 25.4)}  # landscape, inches
MARGIN = 0.4  # inches
# Most used first; the combo diagram is drawn with the Base layer
PAGES = [("Base (Colemak-DH)", "Sym"), ("Num+Fn", "Nav"), ("Excel", "Mod")]
PRINT_STYLE = """
rect.key.held { fill: #c8c8c8; }
text.hold { fill: #a0001c; }
text.label { font-size: 18px; }
"""


def drawer(config, *args):
    cmd = ["uvx", "-q", "--from", "keymap-drawer", "keymap", "-c", str(config), *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def svg_size(svg):
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', svg)
    if not m:
        sys.exit("keymap-drawer output has no svg width/height")
    return float(m.group(1)), float(m.group(2))


def main():
    paper = sys.argv[1] if len(sys.argv) > 1 else "letter"
    if paper not in PAPER:
        sys.exit(f"usage: {sys.argv[0]} [letter|a4]")
    page_w, page_h = PAPER[paper]
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "uncommitted"
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "config"],
                           capture_output=True, text=True).stdout.strip()
    stamp = f"Advantage 360 · {sha}{'+dirty' if dirty else ''} · {datetime.date.today()}"

    cfg = yaml.safe_load((ROOT / "keymap_drawer.config.yaml").read_text())
    cfg["draw_config"]["svg_extra_style"] = PRINT_STYLE
    cfg["draw_config"]["footer_text"] = stamp
    # the combo inline on its keys, not a separate diagram that halves the page
    cfg["draw_config"]["separate_combo_diagrams"] = False

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        config = tmp / "print.yaml"
        config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
        keymap = tmp / "keymap.yaml"
        keymap.write_text(drawer(config, "parse", "-z", str(ROOT / "config/adv360.keymap")))

        pdf_pages = []
        for i, layers in enumerate(PAGES):
            svg = drawer(config, "draw", str(keymap), "-s", *layers)
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

        target = ROOT / "keymap-custom" / "cheatsheet.pdf"
        merge(pdf_pages, target)
        print(f"{target.relative_to(ROOT)}: {len(PAGES)} pages, {paper} landscape, {stamp}")


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


if __name__ == "__main__":
    main()
