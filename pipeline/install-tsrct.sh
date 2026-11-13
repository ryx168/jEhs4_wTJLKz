#!/usr/bin/env bash
# Installs the Tesseract CLI + a software Vulkan driver + ffmpeg on an Ubuntu runner.
# Exports TS (absolute tsrct path) and FFMPEG into $GITHUB_ENV when present.
set -euo pipefail
VER="${TSRCT_VERSION:-0.6.0}"

sudo apt-get update -qq
sudo apt-get install -y -qq unzip python3 python3-pip ffmpeg libvulkan1 mesa-vulkan-drivers vulkan-tools zlib1g fonts-noto-cjk time >/dev/null
sudo apt-get install -y -qq libasound2t64 >/dev/null 2>&1 || sudo apt-get install -y -qq libasound2 >/dev/null

base="https://github.com/mirage-hq/tesseract/releases/download/v${VER}"
z="tesseract-${VER}-linux-x86_64.zip"
cd /tmp
curl -fsSL -o "$z" "$base/$z"
curl -fsSL -o "$z.sha256" "$base/$z.sha256"
sha256sum -c "$z.sha256"
rm -rf tsrct-cli && unzip -q "$z" -d tsrct-cli
d=$(find tsrct-cli -name install.sh -printf '%h\n' | head -1)
bash "$d/install.sh" >/dev/null
TS="${XDG_DATA_HOME:-$HOME/.local/share}/Tesseract/bin/tsrct"
"$TS" --version
FFMPEG="$(command -v ffmpeg)"
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "TS=$TS" >> "$GITHUB_ENV"
  echo "FFMPEG=$FFMPEG" >> "$GITHUB_ENV"
fi
echo "tsrct=$TS ffmpeg=$FFMPEG"
