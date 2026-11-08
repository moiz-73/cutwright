#!/usr/bin/env bash
# cutwright bootstrap: static ffmpeg, GL libs for Skia, fonts, python package.
# No root required. Debian/Ubuntu x86_64.
set -euo pipefail

BIN="${HOME}/.local/bin"
SRC="${HOME}/.local/src/cutwright"
mkdir -p "$BIN" "$SRC"

if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -x "$BIN/ffmpeg" ]; then
  echo "==> static ffmpeg"
  curl -sL -o "$SRC/ffmpeg.tar.xz" \
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
  tar -xJf "$SRC/ffmpeg.tar.xz" -C "$SRC"
  cp "$SRC"/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg "$BIN/"
  cp "$SRC"/ffmpeg-master-latest-linux64-gpl/bin/ffprobe "$BIN/"
  chmod +x "$BIN/ffmpeg" "$BIN/ffprobe"
fi

# Skia needs libEGL/libGL. If the base image lacks them and we are not root,
# pull the bookworm runtime debs into a private prefix.
if ! ldconfig -p 2>/dev/null | grep -q 'libEGL.so.1'; then
  echo "==> local GL runtime (no root)"
  mkdir -p "$SRC/libs"
  python3 - "$SRC" <<'PY'
import gzip, sys, urllib.request
from pathlib import Path
src = Path(sys.argv[1]); lib = src / "libs"
want = {"libegl1","libgl1","libglvnd0","libglx0","libx11-6","libxau6","libxdmcp6",
        "libbsd0","libmd0","libxcb1","libxext6"}
idx = src / "Packages.gz"
if not idx.exists():
    urllib.request.urlretrieve(
        "https://deb.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.gz", idx)
cur, found = {}, {}
for line in gzip.open(idx, "rt", errors="replace"):
    line = line.rstrip("\n")
    if not line:
        if cur.get("Package") in want and cur["Package"] not in found:
            found[cur["Package"]] = cur["Filename"]
        cur = {}
    elif ": " in line:
        k, v = line.split(": ", 1); cur[k] = v
for pkg, fn in found.items():
    deb = src / Path(fn).name
    if not deb.exists():
        urllib.request.urlretrieve("https://deb.debian.org/debian/" + fn, deb)
    import subprocess
    subprocess.run(["dpkg-deb", "-x", str(deb), str(lib)], check=True)
print("gl libs in", lib / "usr/lib/x86_64-linux-gnu")
PY
  echo "export LD_LIBRARY_PATH=$SRC/libs/usr/lib/x86_64-linux-gnu:\${LD_LIBRARY_PATH:-}" >> "$HOME/.bashrc"
  export LD_LIBRARY_PATH="$SRC/libs/usr/lib/x86_64-linux-gnu"
fi

echo "==> python deps"
pip install -e . >/dev/null

echo "==> fonts"
python3 scripts/fetch_fonts.py

export PATH="$BIN:$PATH"
cw doctor
echo
echo "Ready. Try:  cw launch --spec examples/lumen.json --out out/lumen.mp4"
