#!/usr/bin/env bash
# Use generic Arch startup objects instead of the build host's optimized glibc.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output=$root/build-v3
cef=
jobs=8
package=1
keep=0
while (($#)); do
  case "$1" in
  --cef-root)
    cef=$2
    shift 2
    ;;
  --output-dir)
    output=$2
    shift 2
    ;;
  --jobs)
    jobs=$2
    shift 2
    ;;
  --no-package)
    package=0
    shift
    ;;
  --keep-container)
    keep=1
    shift
    ;;
  *)
    echo "Usage: $0 [--cef-root DIR] [--output-dir DIR] [--jobs N] [--no-package] [--keep-container]" >&2
    exit 2
    ;;
  esac
done
[[ $jobs =~ ^[1-9][0-9]*$ ]] || {
  echo 'Invalid job count' >&2
  exit 2
}
if [[ -z $cef ]]; then cef=$(bash "$root/scripts/fetch-cef.sh"); fi
cef=$(realpath -- "$cef")
[[ -f $cef/Release/libcef.so ]] || {
  echo 'Missing pinned CEF runtime' >&2
  exit 1
}
mkdir -p -- "$output"
output=$(realpath -- "$output")
container=${OBS_BROWSER_BUILD_CONTAINER:-obs-browser-arch-v3-build}
image=${OBS_BROWSER_BUILD_IMAGE:-archlinux:base-devel}
if docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container $container already exists; choose OBS_BROWSER_BUILD_CONTAINER or remove your earlier build container." >&2
  exit 1
fi
cleanup() {
  if ((! keep)); then docker rm -f "$container" >/dev/null; fi
}
docker run --name "$container" --init -d \
  --mount "type=bind,src=$root,dst=$root,readonly" \
  --mount "type=bind,src=$cef,dst=$cef,readonly" \
  --mount "type=bind,src=$output,dst=$output" \
  "$image" sleep infinity >/dev/null
trap cleanup EXIT
docker image inspect "$image" --format '{{json .RepoDigests}}' >"$output/container-image.json"
docker exec -i "$container" bash -s -- "$(id -u)" "$(id -g)" <<'SETUP'
set -euo pipefail
pacman -Syu --needed --noconfirm git cmake ninja obs-studio qt6-base nlohmann-json simde \
  libdrm libglvnd libx11 wayland python zstd binutils xorg-server-xvfb xorg-xauth qemu-user
groupadd -g "$2" builder
useradd -m -u "$1" -g "$2" builder
SETUP
docker exec -i --user "$(id -u):$(id -g)" "$container" bash -s -- "$root" "$cef" "$output" "$jobs" "$package" <<'BUILD'
set -euo pipefail
root=$1
cef=$2
output=$3
jobs=$4
package=$5
export XDG_CACHE_HOME="$output/cache"
# Do not set QT_NO_GLIB: it breaks xdg-desktop-portal ScreenCast callbacks.
unset QT_NO_GLIB
checks="$output/checks/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$XDG_CACHE_HOME" "$checks"
cd "$root"
pacman -Q glibc gcc cmake obs-studio qt6-base > "$output/toolchain.txt"
readelf -n /usr/lib/Scrt1.o > "$output/crt-notes.txt"
cmake -S "$root" -B "$output/cmake" -G Ninja \
  -DCEF_ROOT_DIR="$cef" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
  '-DCMAKE_C_FLAGS=-march=x86-64-v3 -mtune=generic' \
  '-DCMAKE_CXX_FLAGS=-march=x86-64-v3 -mtune=generic' \
  -DOBS_BROWSER_BUILD_TESTS=ON -DOBS_BROWSER_ENABLE_DEVTOOLS=OFF
cmake --build "$output/cmake" -j "$jobs"
xvfb-run -a ctest --test-dir "$output/cmake" --output-on-failure
DESTDIR="$output/stage-tests" cmake --install "$output/cmake"
LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a python3 tests/startup_audit.py \
  --executable "$output/cmake/cef-startup-test" \
  --module "$output/stage-tests/usr/lib/obs-browser-nvidia/obs-browser.so" \
  --output-dir "$checks/startup" --cef-arg=--disable-gpu
xvfb-run -a python3 tests/fallback_audit.py \
  --executable "$output/cmake/browser-test-host" \
  --module "$output/stage-tests/usr/lib/obs-browser-nvidia/obs-browser.so" \
  --output-dir "$checks/fallback"
cmake -S "$root" -B "$output/cmake" -DOBS_BROWSER_BUILD_TESTS=OFF
cmake --build "$output/cmake" -j "$jobs"
DESTDIR="$output/stage" cmake --install "$output/cmake"
readelf -n "$output/stage/usr/lib/obs-browser-nvidia/obs-browser-page" > "$output/helper-notes.txt"
readelf -n "$output/stage/usr/lib/obs-browser-nvidia/obs-browser.so" > "$output/plugin-notes.txt"
set +e
timeout 30 qemu-x86_64 -cpu Haswell "$output/stage/usr/lib/obs-browser-nvidia/obs-browser-page" --no-sandbox \
  > "$output/qemu-helper.log" 2>&1
helper_status=$?
set -e
# CefExecuteProcess returns -1 when no subprocess type is supplied.
[[ $helper_status == 255 ]] || { cat "$output/qemu-helper.log" >&2; exit 1; }
printf 'Haswell helper entry check passed (CefExecuteProcess returned -1).\n'
printf 'Integration check logs: %s\n' "$checks"
if (( package )); then bash scripts/package-test-build.sh "$output/cmake" "$output/dist"; fi
BUILD
printf 'Build output: %s\n' "$output"
if ((keep)); then printf 'Build container retained: %s\n' "$container"; fi
