"""Generate the app icon: a front-facing bull elk, cream on forest green.

Writes a multi-resolution favicon.ico (16/24/32/48/64/128/256) plus a 256px
PNG. The .ico serves double duty -- Setup.bat points the desktop shortcut at
it, and Dash picks it up automatically as the browser tab icon because it
lives in app/assets/.

    python tools/make_icon.py                 # draw the elk
    python tools/make_icon.py --from art.png  # use real artwork instead

Artwork is drawn side-on at 1024px and downsampled, so the curves stay clean.
The elk is scaled to sit fully INSIDE the disc: cream antlers poking outside
it would vanish against a light desktop background.
"""
from PIL import Image, ImageDraw
from pathlib import Path
import argparse

S = 1024                          # supersampled working canvas
K = S / 256.0                     # design coords are in a 256 box
CX = 128.0                        # horizontal centre, for mirroring

BG = (47, 74, 61, 255)            # deep forest green
FG = (244, 239, 228, 255)         # cream
EYE = (201, 42, 38, 255)          # deep red -- holds its colour down to 32px

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "Colorado_Migration_Mapping" / "Colorado Migration Mapping" / "app" / "assets"


# --- drawing helpers -------------------------------------------------------

def sc(pts):
    return [(x * K, y * K) for x, y in pts]


def poly(d, pts, col=FG):
    d.polygon(sc(pts), fill=col)


def ell(d, box, col=FG):
    d.ellipse(sc(box), fill=col)


def stroke(d, pts, w, col=FG):
    """Round-capped, round-jointed stroke."""
    d.line(sc(pts), fill=col, width=int(w * K), joint="curve")
    r = w * K / 2
    for x, y in sc(pts):
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)


# --- the elk ---------------------------------------------------------------

def _half(d, s):
    """Draw the right side when s=+1, the mirrored left side when s=-1."""
    mx = lambda x: CX + s * (x - CX)
    P = lambda pts: [(mx(x), y) for x, y in pts]

    # ear: leaf-shaped, angled down-and-out
    poly(d, P([(144, 118), (162, 110), (182, 110), (198, 118),
               (196, 130), (178, 138), (158, 140), (144, 134)]))
    tip = sorted([mx(186), mx(202)])
    ell(d, [(tip[0], 108), (tip[1], 132)])

    # antler: one bold beam with three chunky tines. Strokes are deliberately
    # heavy -- anything finer than ~8 units disappears at the 48px desktop size.
    stroke(d, P([(142, 100), (152, 76), (166, 56), (184, 42), (202, 36)]), 11)
    for base, t in [((152, 76), (140, 50)),
                    ((168, 55), (166, 26)),
                    ((188, 41), (196, 14))]:
        stroke(d, P([base, t]), 9)
    stroke(d, P([(202, 36), (222, 26)]), 9)      # terminal fork


def draw_elk(d):
    # head: crown, widest at the eyes, curving in to the muzzle
    poly(d, [
        (104, 102), (152, 102),
        (162, 118), (165, 136),
        (159, 156), (149, 174),
        (143, 190), (138, 202),
        (128, 207), (118, 202),
        (113, 190), (107, 174),
        (97, 156), (91, 136),
        (94, 118),
    ])
    ell(d, [(104, 182), (152, 214)])             # muzzle pad
    ell(d, [(96, 100), (160, 146)])              # rounded skull

    for s in (1, -1):
        _half(d, s)

    ell(d, [(106, 138), (118, 150)], EYE)
    ell(d, [(138, 138), (150, 150)], EYE)
    ell(d, [(118, 192), (126, 199)], BG)         # nostrils
    ell(d, [(130, 192), (138, 199)], BG)


# --- composition -----------------------------------------------------------

def render(source_png=None, fit=0.78):
    """Return a 256px RGBA icon. If source_png is given it replaces the elk."""
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(base).ellipse([0, 0, S - 1, S - 1], fill=BG)

    if source_png:
        art = Image.open(source_png).convert("RGBA")
    else:
        art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw_elk(ImageDraw.Draw(art))

    box = art.getbbox()
    if box:
        art = art.crop(box)
    w, h = art.size
    k = (S * fit) / max(w, h)
    art = art.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    base.alpha_composite(art, ((S - art.width) // 2, (S - art.height) // 2))

    return base.resize((256, 256), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", metavar="PNG",
                    help="use this image instead of the drawn elk")
    ap.add_argument("--out", default=str(ASSETS),
                    help="output directory (default: app/assets/)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    icon = render(args.src)

    png = out / "elk_icon.png"
    ico = out / "favicon.ico"
    icon.save(png)
    # Pillow builds every listed size into the one .ico; Windows then picks
    # the right one per context (16 taskbar, 48 desktop, 256 tiles).
    icon.save(ico, format="ICO", sizes=[(n, n) for n in ICO_SIZES])

    print(f"wrote {png}  ({png.stat().st_size:,} B)")
    print(f"wrote {ico}  ({ico.stat().st_size:,} B, sizes: "
          f"{', '.join(str(n) for n in ICO_SIZES)})")


if __name__ == "__main__":
    main()
