# obs-browser-nvidia

Experimental NVIDIA GPU acceleration for OBS browser sources on Linux (Wayland), built on
[obsproject/obs-browser](https://github.com/obsproject/obs-browser) 2.27.5.

Not an official OBS build. Upstream browser-source API documentation:
[docs/UPSTREAM-README.md](docs/UPSTREAM-README.md).

**Current status: experimental test candidate.** The pinned CEF 156.0.30 includes the NVIDIA
producer-synchronization fix for [CEF #4313](https://github.com/chromiumembedded/cef/issues/4313)
(backported as CEF commit `57389f04a61a`, shipped from 156.0.28). A fixed dependency does not by
itself validate this fork on a given GPU/driver; see [validation](docs/VALIDATION.md) and the
[historical CEF note](docs/archive/CEF-156.0.14-source-build.md).

## Status

| Feature | State |
|---|---|
| NVIDIA DMA-BUF browser sources, native Wayland | Fixture passes on RTX 5060 with the pinned CEF; longer streaming runs not retested |
| Automatic CPU fallback per source | Implemented; current lifecycle regression checks use software rendering |
| Live streaming with overlays (local RTMP) | Historical measurements only; not rerun for current revision |
| Native Wayland browser docks | Not supported (needs unmerged CEF #4233) |
| Premultiplied sRGB over white | Inherited upstream defect, not fixed |
| Hardware other than RTX 5060 | Not tested (drivers 615.78 and 620.70 exercised) |

## Requirements

- Arch Linux or derivative, x86-64-v3 CPU or newer, OBS Studio 33, Qt 6, Wayland session
- NVIDIA driver with GBM/EGL DMA-BUF support for the GPU path
- `bubblewrap` (used for a temporary mount overlay, not as a security sandbox)

## Install

### Arch/CachyOS package

Build `obs-browser-nvidia-git` from this repository:

```sh
git clone -b experimental/nvidia-cef156 https://github.com/Linaryx/obs-browser.git
cd obs-browser/packaging/aur
makepkg -si
```

The package is not published to the AUR yet. To use an existing checkout as the package source:

```sh
OBS_BROWSER_FORK_URL=file:///absolute/path/to/obs-browser makepkg -si
```

### Manual build

See [docs/BUILD.md](docs/BUILD.md) for the CEF download, CMake build, staging and the
Docker-based test bundle. A staged build installs under `stage/usr/lib/obs-browser-nvidia`;
nothing in the system directories or the OBS package is overwritten.

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
| `OBS_BROWSER_QT_NO_GLIB` | `1` | Old GTK/Wayland startup workaround; breaks portal capture |
| `OBS_BROWSER_STATS_LOG` | `1` | Log per-source GPU copy statistics every 5 s |
| `OBS_BROWSER_FULL_COPY` | `1` | Diagnostic: copy the whole frame instead of `capture_update_rect` |
| `OBS_BROWSER_GPU_FENCE` | `1` | Diagnostic: wait on a GL fence instead of `glFinish` |

The accelerated Linux path copies only CEF's `capture_update_rect` by default. Set
`OBS_BROWSER_FULL_COPY=1` to reproduce the old full-frame behavior when comparing.
The GPU path needs **Browser Hardware Acceleration** enabled in OBS settings.
`QT_NO_GLIB` is deliberately left unset: it disables Qt's GLib dispatcher, which prevents OBS
from processing xdg-desktop-portal ScreenCast responses. Set `OBS_BROWSER_QT_NO_GLIB=1` only if
the GTK/Wayland startup race returns.

GPU confirmation in a diagnostics log is `accelerated DMA-BUF frame` per visible source.
`CPU paint fallback` means that source reloaded on CPU; `NVIDIA shared textures: experimental`
alone does not prove GPU rendering.

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
- Only RTX 5060 was tested (drivers 615.78 and 620.70); other GPUs are untested.

## Tests

```sh
cef=$(bash scripts/fetch-cef.sh)
cmake -S . -B build -DOBS_BROWSER_BUILD_TESTS=ON -DCEF_ROOT_DIR="$cef"
cmake --build build -j "$(nproc)"
ctest --test-dir build --output-on-failure
DESTDIR="$PWD/stage" cmake --install build
python3 tests/benchmark.py                 # GPU/CPU pixels, FPS, CPU tree (native Wayland)
python3 tests/stream_audit.py --gpu-mode nvidia --name my-gpu   # local RTMP stream
python3 tests/stream_audit.py --stock --name my-stock           # stock obs-browser with NVIDIA blocked
```

Results go to `test-results/`, which is git-ignored. Stream tests use isolated OBS profiles and a
local RTMP receiver. They never use your stream key or start a live output.

## Documentation

- [Build and package](docs/BUILD.md)
- [Validation record](docs/VALIDATION.md)
- [Upstream browser-source API](docs/UPSTREAM-README.md)
- [Archive](docs/archive/README.md) — historical measurements and research notes

## License

GPL-2.0-or-later (upstream obs-browser). CEF is BSD-3-Clause; see `COPYING` and the CEF license file
in the package. Upstream copyright notices are unchanged.
