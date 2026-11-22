"""Make the app's logo files from the Rizviz Scraping Hub logo (installer/rizviz-logo-source.webp).

    py installer\\make_logo.py        (any Python with Pillow)

Writes, from the "RV" mark at the top of the logo (the words below it are left out):
    installer/scraping-hub.ico       window, shortcuts, setup wizard (16-256 px)
    desktop/rizviz-mark.png          sign-in and start-up screens
    client/public/rizviz-mark.png    the console's logo
    admin/public/rizviz-mark.png     the account panel's logo
    admin/src/app/icon.png           the account panel's browser-tab icon
The white background becomes transparent, so the mark sits on any colour.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "installer" / "rizviz-logo-source.webp"
ICO = ROOT / "installer" / "scraping-hub.ico"
PNGS = [
    ROOT / "desktop" / "rizviz-mark.png",
    ROOT / "client" / "public" / "rizviz-mark.png",
    ROOT / "admin" / "public" / "rizviz-mark.png",
    ROOT / "admin" / "src" / "app" / "icon.png",
]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def mark_box(img: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the mark: the first block of non-white rows (the words come after a gap)."""
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()
    inked = [any(px[x, y] < 200 for x in range(0, w, 2)) for y in range(h)]
    top = inked.index(True)
    bottom = top
    while bottom < h and inked[bottom]:
        bottom += 1
    cols = [x for x in range(w) if any(px[x, y] < 200 for y in range(top, bottom, 2))]
    return cols[0], top, cols[-1] + 1, bottom


def white_to_alpha(img: Image.Image) -> Image.Image:
    """White -> transparent, keeping the anti-aliased edges smooth (GIMP's colour-to-alpha, for white)."""
    out = []
    for r, g, b, _ in img.getdata():
        a = 255 - min(r, g, b)
        if a >= 235:
            out.append((r, g, b, 255))
        elif a <= 8:
            out.append((255, 255, 255, 0))
        else:
            f = 255 / a  # undo the blend with white
            out.append((
                max(0, min(255, round(255 - (255 - r) * f))),
                max(0, min(255, round(255 - (255 - g) * f))),
                max(0, min(255, round(255 - (255 - b) * f))),
                a,
            ))
    res = Image.new("RGBA", img.size)
    res.putdata(out)
    return res


def square(img: Image.Image, pad: float = 0.04) -> Image.Image:
    side = round(max(img.size) * (1 + 2 * pad))
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def main() -> None:
    src = Image.open(SOURCE).convert("RGBA")
    mark = square(white_to_alpha(src.crop(mark_box(src))))
    for png in PNGS:
        png.parent.mkdir(parents=True, exist_ok=True)
        mark.resize((256, 256), Image.LANCZOS).save(png, optimize=True)
        print(f"wrote {png.relative_to(ROOT)}")
    mark.resize((256, 256), Image.LANCZOS).save(ICO, sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {ICO.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
