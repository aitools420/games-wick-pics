#!/usr/bin/env python3
"""Bake the game's runtime transparency into the sprite sheets, offline.

The upstream sheets are JPEGs behind .png names. JPEG can't carry alpha, so the
game reconstructs it in the browser on every load via keyWhite(): a border
flood-fill of near-white pixels plus two defringe passes. That is ~80% of the
image-processing CPU at boot (1381 ms of 1694 ms on a 4x-throttled phone).

This does exactly the same work once, at build time, and writes WebP with a real
alpha channel. It is a line-by-line port of keyWhite() — same thresholds, same
4-connectivity, same two-pass defringe with batched application — so the
resulting alpha mask is identical and nothing changes visually.

Usage: bake_alpha.py <src_dir> <out_dir> [--quality N]
"""
import sys, os, glob, json
import numpy as np
from PIL import Image
from scipy import ndimage

BG_MIN = 148        # r,g,b must all exceed this to count as background
BG_SPREAD = 18      # and be this close to grey
FRINGE_MAX = 150    # defringe: brightest channel above this
FRINGE_SPREAD = 46  # and channel spread below this
ALPHA_CUT = 40      # "transparent" threshold used throughout keyWhite


def key_white(rgba: np.ndarray) -> np.ndarray:
    """Port of keyWhite(). Takes HxWx4 uint8, returns the alpha channel."""
    a = rgba[:, :, 3].copy()
    r = rgba[:, :, 0].astype(np.int16)
    g = rgba[:, :, 1].astype(np.int16)
    b = rgba[:, :, 2].astype(np.int16)

    # isBg: already transparent, OR bright and low-saturation
    is_bg = (a < ALPHA_CUT) | (
        (r > BG_MIN) & (g > BG_MIN) & (b > BG_MIN)
        & (np.abs(r - g) < BG_SPREAD) & (np.abs(g - b) < BG_SPREAD)
    )

    # border flood-fill, 4-connected: keep only bg regions touching an edge
    lbl, n = ndimage.label(is_bg, structure=ndimage.generate_binary_structure(2, 1))
    if n:
        edge = np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]])
        touching = np.unique(edge[edge > 0])
        a[np.isin(lbl, touching)] = 0

    # DEFRINGE, two passes, interior pixels only (JS loops 1..h-2 / 1..w-2)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    halo_colour = (mx > FRINGE_MAX) & ((mx - mn) < FRINGE_SPREAD)
    for _ in range(2):
        clear = a < ALPHA_CUT
        touches = np.zeros_like(clear)
        touches[:, 1:] |= clear[:, :-1]      # left neighbour
        touches[:, :-1] |= clear[:, 1:]      # right neighbour
        touches[1:, :] |= clear[:-1, :]      # up neighbour
        touches[:-1, :] |= clear[1:, :]      # down neighbour
        interior = np.zeros_like(touches)
        interior[1:-1, 1:-1] = True
        kill = (a >= ALPHA_CUT) & touches & halo_colour & interior
        if not kill.any():
            break
        a[kill] = 0
    return a


def main():
    src, out = sys.argv[1], sys.argv[2]
    quality = 90
    if "--quality" in sys.argv:
        quality = int(sys.argv[sys.argv.index("--quality") + 1])
    os.makedirs(out, exist_ok=True)

    report, before, after = {}, 0, 0
    for f in sorted(glob.glob(os.path.join(src, "hero_*.png"))):
        name = os.path.basename(f)
        im = Image.open(f).convert("RGBA")
        arr = np.array(im)
        arr[:, :, 3] = key_white(arr)
        dst = os.path.join(out, name.replace(".png", ".webp"))
        Image.fromarray(arr, "RGBA").save(dst, "WEBP", quality=quality, method=6, exact=True)
        b, a = os.path.getsize(f), os.path.getsize(dst)
        before += b
        after += a
        opaque = int((arr[:, :, 3] >= ALPHA_CUT).sum())
        report[name] = {"webp": os.path.basename(dst), "src_bytes": b, "out_bytes": a,
                        "opaque_px": opaque, "size": list(im.size)}
        print(f"{name:26} {b/1024:7.1f}K -> {a/1024:7.1f}K   opaque={opaque}")

    print(f"\nTOTAL {before/1024:.1f}K -> {after/1024:.1f}K  "
          f"({'-' if after < before else '+'}{abs(100*(1-after/before)):.1f}%)")
    with open(os.path.join(out, "bake-report.json"), "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
