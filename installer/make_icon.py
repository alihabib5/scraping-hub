"""Draw installer/scraping-hub.ico — the console's logo mark (client/src/components/Logo.tsx).

    server\\.venv\\Scripts\\python.exe installer\\make_icon.py

Used for the app window, Start Menu / desktop shortcuts and the setup wizard.
Renders with PyMuPDF (already a server dependency); PNG-in-ICO, Vista+.
"""

import struct
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent / "scraping-hub.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]

# The Logo component: a rounded ink-900 tile, the mark at 55% of it.
SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{s}" height="{s}">
  <rect width="24" height="24" rx="5" fill="#0b1f3a"/>
  <g transform="translate(5.4 5.4) scale(0.55)" fill="none" stroke-width="1.8" stroke-linejoin="round">
    <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z" stroke="#ffffff"/>
    <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" stroke="#ffffff" stroke-opacity="0.7"/>
    <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" stroke="#d2a55c"/>
  </g>
</svg>"""


def png(size: int) -> bytes:
    doc = pymupdf.open(stream=SVG.format(s=size).encode(), filetype="svg")
    return doc[0].get_pixmap(alpha=True).tobytes("png")


def main() -> None:
    images = [png(s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(SIZES, images):
        dim = 0 if size == 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    OUT.write_bytes(header + entries + b"".join(images))
    (OUT.parent / "build").mkdir(exist_ok=True)
    (OUT.parent / "build" / "icon-preview.png").write_bytes(images[-1])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
