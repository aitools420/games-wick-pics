#!/usr/bin/env python3
"""Everything we change about upstream's game, in one idempotent place.

The sync workflow rsyncs mtwhv5ktjr-bot/pepe-wick over game1/play/ and then runs
this. Run it twice and the second run is a no-op. If any patch target has moved
upstream this EXITS NON-ZERO so the workflow fails loudly instead of shipping a
half-patched game.

  1. deeplink  -> point the mobile-wallet link at this host
  2. icons     -> upstream ships 512x512 115KB copies for icon-192/apple-touch

Sprites need no patch: upstream ships pre-keyed WebP with a real alpha channel
and keeps keyWhite() as its own fallback for .png sheets. Don't touch that.
"""
import os, sys, io
from PIL import Image

PLAY = "game1/play"
HTML = os.path.join(PLAY, "index.html")
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


def main():
    if not os.path.exists(HTML):
        fail(f"{HTML} missing")
    s = open(HTML, encoding="utf-8").read()
    s = patch_deeplink(s)
    open(HTML, "w", encoding="utf-8").write(s)
    patch_icons()

    print("changes: " + (", ".join(changed) if changed else "none (already current)"))


if __name__ == "__main__":
    main()
