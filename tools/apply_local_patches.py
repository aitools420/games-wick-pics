#!/usr/bin/env python3
"""Everything we change about upstream's game, in one idempotent place.

The sync workflow rsyncs mtwhv5ktjr-bot/pepe-wick over game1/play/ and then runs
this. Run it twice and the second run is a no-op. If any patch target has moved
upstream this EXITS NON-ZERO so the workflow fails loudly instead of shipping a
half-patched game.

  1. deeplink  -> point the mobile-wallet link at this host
  2. icons     -> upstream ships 512x512 115KB copies for icon-192/apple-touch
  3. sprites   -> bake the runtime transparency into WebP and stop keying at boot
"""
import os, sys, glob, io
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bake_alpha import key_white

PLAY = "game1/play"
HTML = os.path.join(PLAY, "index.html")
WEBP_QUALITY = 80          # sheets render ~47px tall on screen from a 548px source
changed = []


def fail(msg):
    sys.exit(f"PATCH FAILED: {msg}\nUpstream changed shape — fix tools/apply_local_patches.py")


# ---------------------------------------------------------------- 1. deeplink
def patch_deeplink(s):
    old = "metamask.app.link/dapp/pepe-zero.vercel.app"
    new = "metamask.app.link/dapp/games.wick.pics/game1"
    if old in s:
        changed.append("deeplink")
        return s.replace(old, new)
    if new in s:
        return s
    fail("deeplink string not found")


# ------------------------------------------------------------------- 2. icons
def patch_icons():
    for f, size in [(f"{PLAY}/icon-192.png", 192),
                    (f"{PLAY}/icon-512.png", 512),
                    (f"{PLAY}/apple-touch-icon.png", 180)]:
        if not os.path.exists(f):
            continue
        before = os.path.getsize(f)
        im = Image.open(f).convert("RGBA")
        if im.size != (size, size):
            im = im.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True, compress_level=9)
        if buf.getvalue() != open(f, "rb").read():
            open(f, "wb").write(buf.getvalue())
            changed.append(f"icon {os.path.basename(f)} {before//1024}K->{len(buf.getvalue())//1024}K")


# ----------------------------------------------------------------- 3. sprites
KEYWHITE_PATCHED = "/* transparency baked at build time by tools/bake_alpha.py */"

NEW_KEYWHITE = ('function keyWhite(im){ ' + KEYWHITE_PATCHED + '\n'
                '  try{ const c=document.createElement("canvas"); c.width=im.width; c.height=im.height;\n'
                '    c.getContext("2d",{willReadFrequently:true}).drawImage(im,0,0); return c;\n'
                '  }catch(e){ return im; }\n'
                '}\n')


def bake_sheets():
    """JPEG sheets -> WebP with a real alpha channel; drop the originals."""
    srcs = sorted(glob.glob(f"{PLAY}/hero_*.png"))
    if not srcs:
        return  # already baked and .png removed by a previous run
    total_before = total_after = 0
    for f in srcs:
        arr = np.array(Image.open(f).convert("RGBA"))
        arr[:, :, 3] = key_white(arr)
        dst = f.replace(".png", ".webp")
        Image.fromarray(arr, "RGBA").save(
            dst, "WEBP", quality=WEBP_QUALITY, alpha_quality=100, method=6, exact=True)
        total_before += os.path.getsize(f)
        total_after += os.path.getsize(dst)
        os.remove(f)
    changed.append(f"baked {len(srcs)} sheets {total_before//1024}K->{total_after//1024}K")


def patch_sheet_refs(s):
    """Point HERO_SHEETS at the .webp files and stop keying at runtime."""
    import re
    png_refs = re.findall(r'file:"hero_[a-z_]+\.png"', s)
    if png_refs:
        s = re.sub(r'(file:"hero_[a-z_]+)\.png"', r'\1.webp"', s)
        changed.append(f"repointed {len(png_refs)} sheet refs to .webp")
    elif not re.search(r'file:"hero_[a-z_]+\.webp"', s):
        fail("HERO_SHEETS entries not found")

    if KEYWHITE_PATCHED in s:
        return s
    start = s.find("function keyWhite(im){")
    if start == -1:
        fail("keyWhite() not found")
    end = s.find("\nfunction handAnchors(", start)
    if end == -1:
        fail("could not find the end of keyWhite() (handAnchors moved)")
    s = s[:start] + NEW_KEYWHITE + s[end + 1:]
    changed.append("keyWhite -> passthrough")
    return s


def main():
    if not os.path.exists(HTML):
        fail(f"{HTML} missing")
    s = open(HTML, encoding="utf-8").read()
    s = patch_deeplink(s)
    bake_sheets()
    s = patch_sheet_refs(s)
    open(HTML, "w", encoding="utf-8").write(s)
    patch_icons()

    # guard: no lingering .png sheet references
    final = open(HTML, encoding="utf-8").read()
    if 'file:"hero_' in final and '.png"' in final.split('HERO_SHEETS')[1][:900]:
        fail("a hero_*.png reference survived")

    print("changes: " + (", ".join(changed) if changed else "none (already current)"))


if __name__ == "__main__":
    main()
