# obs-browser-nvidia

Experimental NVIDIA GPU acceleration for OBS browser sources on Linux (Wayland), built on
[obsproject/obs-browser](https://github.com/obsproject/obs-browser) 2.27.5.

Not an official OBS build. Upstream documentation: [docs/UPSTREAM-README.md](docs/UPSTREAM-README.md).

## Status

| Feature | State |
|---|---|
| NVIDIA DMA-BUF browser sources, native Wayland | Works, tested |
| Automatic CPU fallback per source | Works, tested |
| Live streaming with overlays (local RTMP) | Works, tested |
| Native Wayland browser docks | Not supported (needs unmerged CEF #4233) |
| Premultiplied sRGB over white | Inherited upstream defect, not fixed |
| Hardware other than RTX 5060 / driver 615 | Not tested |

## Test system

| | |
|---|---|
| OS | CachyOS (Arch-based), kernel 7.3.0-4-cachyos |
| Session | Hyprland, native Wayland |
| CPU | Intel Xeon E5-2697A v4, 32 threads |
| RAM | 31 GiB |
| GPU | NVIDIA GeForce RTX 5060, driver 615.78.08 |
| OBS | 33.0.0 |
| CEF | 156.0.14 (plugin, private runtime); 154 (stock package) |

## Streaming test

Scene: `01 · Начало` from a real collection. It contains **10 browser overlays**: 9 visible,
1 hidden. Capture sources (screen, windows, microphone, PipeWire audio) were disabled in the
test copy. Stream: 1920×1080 60 FPS, x264 `veryfast`, 6000 kbps, AAC.
Output went to a **local RTMP receiver**, never to a live service.

Single stream, 60 seconds:

| Browser path | Accepted | Output dropped | Render dropped | Avg render |
|---|---|---|---|---|
| Fork, NVIDIA GPU | yes | 0 | 90 / 4475 | 2.68 ms |
| Fork, CPU paint | yes | 0 | 89 / 4472 | 3.51 ms |
| Stock obs-browser, NVIDIA blocked | yes | 0 | 85 / 4473 | 2.99 ms |

Five parallel streams per preset, 60 seconds each (tree CPU = OBS, CEF renderers and launcher):

| Preset | Tree CPU | Output dropped per stream | Render dropped per stream | DMA-BUF |
|---|---|---|---|---|
| Fork, NVIDIA GPU | ~314% | 0–45 (avg 11) | ~177 / ~4600 | yes |
| Fork, CPU paint | ~560% | 1108–1510 (avg 1311) | ~407 / ~4700 | no |
| Stock, NVIDIA blocked | ~568% | 435–1700 (avg 996) | ~369 / ~4700 | no |

Takeaway: the GPU path cuts CPU use by about 45% and removes almost all dropped output frames
under five parallel 1080p60 streams. CPU paint and stock behave about the same.
Single runs are noisy; treat the single-stream render times as indicative only.
Five parallel 1080p60 CPU streams already saturate this machine; do not expect live use at that load.

## Requirements

- Arch Linux or derivative, OBS Studio 33, Qt 6, Wayland session
- NVIDIA driver with GBM/EGL DMA-BUF support
- `bubblewrap` (used for a temporary mount overlay, not as a security sandbox)

## Install

### AUR

```sh
yay -S obs-browser-nvidia-git
```

The AUR package is not published yet. Once it is, this is the supported path.

### Build from a local clone

```sh
git clone -b experimental/nvidia-cef156 https://github.com/Linaryx/obs-browser.git
cd obs-browser/packaging/aur
makepkg -si
```

Without a GitHub fork, use a local clone instead:

```sh
OBS_BROWSER_FORK_URL=file:///absolute/path/to/obs-browser makepkg -si
```

### Build and stage manually

```sh
sudo pacman -S --needed base-devel git cmake ninja obs-studio qt6-base nlohmann-json \
  libdrm libglvnd libx11 wayland curl bubblewrap ffmpeg
cef=$(bash scripts/fetch-cef.sh)
cmake -S . -B build -G Ninja -DCEF_ROOT_DIR="$cef" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build -j "$(nproc)"
DESTDIR="$PWD/stage" cmake --install build
```

`DESTDIR` stages the files under `stage/usr/lib/obs-browser-nvidia`. Nothing in the system
directories or the OBS package files is overwritten.

## Run

```sh
obs-nvidia-browser
```

Or pick **OBS Studio (NVIDIA)** from the menu. Native Wayland uses NVIDIA by default;
on X11 it uses CPU paint.

| Variable | Values | Meaning |
|---|---|---|
| `OBS_BROWSER_GPU` | `nvidia`, `cpu`, `software`, unset | NVIDIA shared textures / CPU paint / no Chromium GPU / upstream auto |
| `QT_QPA_PLATFORM` | `wayland`, `xcb` | Qt platform; explicit values are kept |
| `OBS_BROWSER_PROXY` | URL | Chromium proxy for browser sources only |
| `OBS_BROWSER_DIAGNOSTICS` | `1` | Extra logs |

The GPU path needs **Browser Hardware Acceleration** enabled in OBS settings.
The launcher sets `QT_NO_GLIB=1` to avoid a GTK/Wayland startup race seen on this machine.

## Fallback

Each source switches once to CPU paint after an import failure, invalid DMA-BUF data,
renderer termination, or no first frame within 15 seconds. The page reloads and audio may pause
briefly. Other sources and the stream keep running.

## Known limits

- Native Wayland docks are unavailable; use `QT_QPA_PLATFORM=xcb OBS_BROWSER_GPU=cpu` for docks.
- Semi-transparent sRGB over white is still incorrect (inherited from upstream). Example: 50% green
  over white renders as `(187,220,187)` instead of `(128,255,128)`.
- Chromium runs with `no_sandbox`, as upstream does.
- A GPU hang after a successful first frame may not recover automatically.
- Only RTX 5060 / driver 615.78 was tested.

## Tests

```sh
cmake -S . -B build -DOBS_BROWSER_BUILD_TESTS=ON && cmake --build build -j "$(nproc)"
ctest --test-dir build --output-on-failure
DESTDIR="$PWD/stage" cmake --install build
python3 tests/benchmark.py                 # GPU/CPU pixels, FPS, CPU tree (native Wayland)
python3 tests/stream_audit.py --gpu-mode nvidia --name my-gpu   # local RTMP stream
python3 tests/stream_audit.py --stock --name my-stock           # stock obs-browser with NVIDIA blocked
```

Results go to `test-results/`, which is git-ignored. Stream tests use isolated OBS profiles and a local
RTMP receiver. They never use your stream key or start a live output.

More detail: [docs/VALIDATION.md](docs/VALIDATION.md) · [docs/FORKS.md](docs/FORKS.md) ·
[docs/IMPLEMENTATION-MATRIX.md](docs/IMPLEMENTATION-MATRIX.md)

## License

GPL-2.0-or-later (upstream obs-browser). CEF is BSD-3-Clause; see `COPYING` and the CEF license file
in the package. Upstream copyright notices are unchanged.
