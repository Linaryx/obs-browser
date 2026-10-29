#!/usr/bin/env bash
set -euo pipefail
cache=${1:-${XDG_CACHE_HOME:-$HOME/.cache}/obs-browser-nvidia}
name='cef_binary_156.0.14+g4fa4ab5+chromium-156.0.8078.48_linux64_minimal'
mkdir -p "$cache"
archive="$cache/$name.tar.bz2"
if [[ ! -f $archive ]]; then
  curl -fL --retry 3 "https://cef-builds.spotifycdn.com/${name//+/%2B}.tar.bz2" -o "$archive.part"
  mv "$archive.part" "$archive"
fi
echo "4191ac920a91a052eba04afb6ed830d47aed46a3e246c434a2f062c23588dc8a  $archive" | sha256sum -c - >&2
if [[ ! -d $cache/$name ]]; then
  tar -xjf "$archive" -C "$cache"
fi
printf '%s\n' "$cache/$name"
