#!/usr/bin/env bash
set -euo pipefail
cache=${1:-${XDG_CACHE_HOME:-$HOME/.cache}/obs-browser-nvidia}
name='cef_binary_156.0.30+g6028375+chromium-156.0.8078.96_linux64_minimal'
mkdir -p "$cache"
archive="$cache/$name.tar.bz2"
if [[ ! -f $archive ]]; then
  curl -fL --retry 3 "https://cef-builds.spotifycdn.com/${name//+/%2B}.tar.bz2" -o "$archive.part"
  mv "$archive.part" "$archive"
fi
echo "356db99d653698aa9ba78b22965032b4fa5b23ba079ffdbaa5d28a8530f04011  $archive" | sha256sum -c - >&2
if [[ ! -d $cache/$name ]]; then
  tar -xjf "$archive" -C "$cache"
fi
printf '%s\n' "$cache/$name"
