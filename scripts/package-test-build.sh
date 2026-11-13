#!/usr/bin/env bash
# Package an existing standalone build without installing into the host system.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build=$(realpath -- "${1:-$root/build}")
output=${2:-$root/dist}
[[ -f $build/CMakeCache.txt ]] || {
  echo "Missing CMakeCache.txt in $build" >&2
  exit 1
}
mkdir -p -- "$output"
output=$(realpath -- "$output")
revision=$(git -C "$root" rev-parse --short HEAD)
state=
[[ -z $(git -C "$root" status --porcelain) ]] || state=-dirty
name="obs-browser-nvidia-arch-x86_64-v3-$revision$state"
work=$(mktemp -d "$output/.package-test.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
stage=$work/stage
bundle=$work/$name
mkdir -p -- "$bundle"
DESTDIR="$stage" cmake --install "$build" --prefix /usr
runtime=$stage/usr/lib/obs-browser-nvidia
[[ -f $runtime/obs-browser.so && -f $runtime/libcef.so && -x $runtime/obs-browser-page ]] || {
  echo 'Expected complete standalone runtime under usr/lib/obs-browser-nvidia; use CMAKE_INSTALL_LIBDIR=lib.' >&2
  exit 1
}
python3 "$root/scripts/check-bundle-isa.py" "$runtime" >"$work/runtime-isa.json"
mv -- "$runtime" "$bundle/runtime"
mv -- "$stage/usr/share/obs/obs-plugins/obs-browser" "$bundle/data"
cp -a -- "$stage/usr/share/licenses/obs-browser-nvidia" "$bundle/licenses"
mkdir -- "$bundle/fixtures" "$bundle/docs"
cp -- "$root/tests/fixture.html" "$root/tests/heavy-fixture.html" "$bundle/fixtures/"
cp -- "$root/docs/VALIDATION.md" "$bundle/docs/"
install -m755 -- "$root/scripts/obs-nvidia-browser" "$bundle/launcher"
cat >"$bundle/obs-nvidia-browser" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export OBS_BROWSER_RUNTIME_ROOT="$bundle/runtime"
export OBS_BROWSER_DATA_ROOT="$bundle/data"
export XDG_CONFIG_HOME=${OBS_BROWSER_TEST_CONFIG_HOME:-$bundle/config}
export XDG_CACHE_HOME="$XDG_CONFIG_HOME/cache"
export XDG_DATA_HOME="$XDG_CONFIG_HOME/data"
mkdir -p -- "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
exec "$bundle/launcher" "$@"
LAUNCHER
chmod 755 "$bundle/obs-nvidia-browser"
cat >"$bundle/README.txt" <<'README'
Experimental OBS browser NVIDIA test bundle / Тестовая сборка

Requirements: Arch Linux x86_64-v3 CPU (or newer; ABI-compatible derivative), installed OBS 33,
Qt 6, qt6-wayland, bubblewrap, and an NVIDIA driver with GBM/EGL DMA-BUF support.
This includes the browser plugin and private CEF runtime, NOT OBS or system libraries.
It is not a portable OBS build for arbitrary distributions or Flatpak OBS.
Packaging rejects bundled ELF files declaring ISA requirements above x86-64-v3.
Missing ELF ISA notes do not prove CPU compatibility; system libraries are not checked.
GPU rendering requires a native Wayland session. X11 defaults to CPU paint.

Запуск / Run (from an extracted writable folder):
  ./obs-nvidia-browser

Settings and CEF cache are isolated in ./config; existing OBS settings are not used.
Изолированные настройки находятся в ./config. Импортируйте копию нужной коллекции
сцен либо создайте Browser Source с анимированным оверлеем. В Settings → Advanced
включите Browser Hardware Acceleration и перезапустите тестовый OBS.
Для простого теста добавьте Browser Source → Local file → fixtures/fixture.html,
1280×720, 60 FPS; включите Control audio via OBS. Для нагрузки используйте
fixtures/heavy-fixture.html. Укажите полный путь к файлу из распакованной папки.
Do not run two instances using the same test config simultaneously.
OBS_BROWSER_TEST_CONFIG_HOME=/absolute/path selects a different test config.

Compare the same scene, resolution and FPS with GPU and CPU paint:
  OBS_BROWSER_GPU=nvidia OBS_BROWSER_DIAGNOSTICS=1 ./obs-nvidia-browser >gpu.log 2>&1
  OBS_BROWSER_GPU=cpu OBS_BROWSER_DIAGNOSTICS=1 ./obs-nvidia-browser >cpu.log 2>&1
These commands preserve OBS's exit status and save the logs without a pipeline.
OBS_BROWSER_GPU=software disables Chromium GPU entirely for additional diagnostics.

GPU confirmation in gpu.log: "accelerated DMA-BUF frame" for each visible source.
"CPU paint fallback" means that source reloaded on CPU: it is not a GPU test pass.
"NVIDIA shared textures: experimental" alone does not confirm GPU frames.
Compare OBS and all obs-browser-page child process CPU usage, not OBS alone.
Check moving/transparent overlays, sound, scene switches, resize, hide/show, and exit.
Не используйте тест для важной трансляции до проверки на своей видеокарте.
Native Wayland browser docks are unavailable in this CEF version. For docks:
  QT_QPA_PLATFORM=xcb OBS_BROWSER_GPU=cpu ./obs-nvidia-browser

NVIDIA rendering has NOT been verified on the recipient's hardware. Successful
compilation or startup does not establish acceleration, correctness or a speedup.
The pinned CEF 156.0.30 includes the upstream producer-synchronization fix for
#4313. Older 156.0.14 bundles do not. Frames may still tear if the target driver
or workload exposes another issue; this remains a test candidate:
https://github.com/chromiumembedded/cef/issues/4313
See BUILD-INFO.json for exact build versions and source state; source.tar.gz contains
the corresponding plugin source, and SOURCE-CHANGES.patch records tracked edits.
docs/VALIDATION.md distinguishes historical NVIDIA measurements from current checks.
CEF license is in licenses/CEF-LICENSE.txt; upstream CEF source:
https://github.com/chromiumembedded/cef (revision recorded in the CEF version).
README

git -C "$root" diff HEAD --binary >"$bundle/SOURCE-CHANGES.patch"
python3 - "$root" "$build" "$output" <<'PY' |
import os
from pathlib import Path
import subprocess
import sys

root, build, output = map(Path, sys.argv[1:])
files = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached', '--others',
                                 '--exclude-standard', '-z']).split(b'\0')
for name in files:
    if not name:
        continue
    path = root / os.fsdecode(name)
    if path.is_relative_to(build) or path.is_relative_to(output) or not path.exists():
        continue
    sys.stdout.buffer.write(name + b'\0')
PY
  tar -C "$root" --null -T - -czf "$bundle/source.tar.gz"
source_hash=$(sha256sum "$bundle/source.tar.gz")
name="$name-${source_hash:0:12}"
mv -- "$bundle" "$work/$name"
bundle=$work/$name
python3 - "$root" "$build" "$bundle" "$work/runtime-isa.json" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root, build, bundle, isa_report = map(Path, sys.argv[1:])
cache = {}
for line in (build / 'CMakeCache.txt').read_text().splitlines():
    if line and not line.startswith(('#', '//')) and '=' in line:
        key, value = line.split('=', 1)
        cache[key.split(':', 1)[0]] = value

def command(*args):
    result = subprocess.run(args, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else None

def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()

cef = Path(cache.get('CEF_ROOT_DIR', ''))
header = cef / 'include/cef_version.h'
cef_defines = [line for line in header.read_text().splitlines()
               if line.startswith(('#define CEF_VERSION ', '#define CHROME_VERSION_'))] if header.is_file() else []
manifest = {
    'format': 1,
    'platform': 'Arch Linux x86_64-v3; installed OBS 33 required',
    'cpu_isa_check': json.loads(isa_report.read_text()),
    'compiler_flags': {key: value for key, value in cache.items()
                       if key.startswith(('CMAKE_C_FLAGS', 'CMAKE_CXX_FLAGS', 'CMAKE_EXE_LINKER_FLAGS', 'CMAKE_MODULE_LINKER_FLAGS'))},
    'source_revision': command('git', '-C', str(root), 'rev-parse', 'HEAD'),
    'source_status': command('git', '-C', str(root), 'status', '--short'),
    'source_archive_sha256': digest(bundle / 'source.tar.gz'),
    'tracked_changes_sha256': digest(bundle / 'SOURCE-CHANGES.patch'),
    'cef_defines': cef_defines,
    'libcef_sha256': digest(bundle / 'runtime/libcef.so'),
    'obs_sdk_version': command('pkg-config', '--modversion', 'libobs'),
    'qt_version': command('pkg-config', '--modversion', 'Qt6Core'),
    'cmake_version': command('cmake', '--version'),
    'compiler_version': command(cache.get('CMAKE_CXX_COMPILER', 'c++'), '--version'),
    'build_type': cache.get('CMAKE_BUILD_TYPE'),
    'test_hooks': cache.get('OBS_BROWSER_BUILD_TESTS', 'OFF'),
    'devtools': cache.get('OBS_BROWSER_ENABLE_DEVTOOLS', 'OFF'),
    'nvidia_hardware_verified_by_packaging': False,
}
(bundle / 'BUILD-INFO.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
tar -C "$work" --zstd -cf "$work/$name.tar.zst" "$name"
mv -- "$work/$name.tar.zst" "$output/$name.tar.zst"
(cd -- "$output" && sha256sum "$name.tar.zst" >"$name.tar.zst.sha256")
printf '%s\n' "$output/$name.tar.zst"
