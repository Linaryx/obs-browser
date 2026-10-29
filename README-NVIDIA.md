# Experimental NVIDIA browser sources on Linux

Small patches on top of obsproject/obs-browser 2.27.5 (`d4db73e`).
No OBS core rebuild and no replacement of the system CEF package are required.
This is **experimental**, not an official OBS build or a claim of universal NVIDIA support.
See [measured results and remaining verification](docs/VALIDATION.md).
The [upstream implementation matrix](docs/IMPLEMENTATION-MATRIX.md) covers all 15 requested PRs,
including merged fixes deliberately not duplicated and incompatible changes deliberately deferred.

## What changed

- Pinned Linux x86-64 CEF **156.0.14+g4fa4ab5 / Chromium 156.0.8078.48**.
  The 8078 branch contains [CEF #4238](https://github.com/chromiumembedded/cef/pull/4238),
  backported as [`3adefb8`](https://github.com/chromiumembedded/cef/commit/3adefb829c1ad4910247ddc461c9078d1d6a9f33).
  It requests native-handle SharedImages instead of forcing CPU-mappable linear GBM buffers.
  Chromium 156 also contains the corresponding native-handle GPU blit change.
- Safe default retains NVIDIA CPU paint. `OBS_BROWSER_GPU=nvidia` opts into shared textures;
  `OBS_BROWSER_GPU=cpu` disables shared textures (CPU paint output, WebGL retained).
  `OBS_BROWSER_GPU=software` also disables Chromium GPU rendering; WebGL may then be unavailable.
  Unset/`auto` preserves upstream detection. OBS's Browser Hardware Acceleration setting must be enabled for GPU mode.
- Fixed an upstream plane-array overrun: iterate `plane_count`, not `kAcceleratedPaintMaxPlanes`.
- Validate plane count, fds, stride, dimensions, color format and visible rectangle.
  Pass real per-frame DRM modifiers to libobs's EGL importer; do not label unknown modifiers LINEAR.
- Import the native buffer only during `OnAcceleratedPaint`, copy the visible region to an OBS-owned
  GPU texture, then release the import before returning to CEF. Never cache CEF's fds or close them.
  A conservative `glFinish` completes the GPU copy before CEF reuses its buffer. This is not zero-copy:
  it is a GPU-to-GPU copy with no CPU pixel readback. Fence-based optimization is future work.
- Preserve upstream premultiplied-alpha blending, sRGB handling, source ID/settings, interaction,
  audio routing and JavaScript bindings. No custom renderer or scene migration.
- Keep `OBS_BROWSER_PROXY` (optional Chromium proxy, independent of OBS's RTMP connection).
- `OBS_BROWSER_ANGLE=gl-egl` optionally adapts CEF #3954's EGL backend selection without forcing
  X11 on native Wayland. The default is `auto`: forcing `gl-egl` crashed CEF's GPU process on the
  tested XWayland/615 driver and lost WebGL even after CPU fallback. This is a diagnostic override,
  not a recommended default or a claimed fix for XWayland acceleration. Existing CLI flags win.
- Expose `browser_render_stats` on the source proc handler: cumulative GPU/CPU paint counts and fallback status.

## Automatic fallback and limits

Each source independently switches once to CEF's `OnPaint` CPU-buffer output after import/allocation
failure, invalid DMA-BUF metadata, renderer-process termination, or no first accelerated paint within **15 visible seconds**.
The browser is recreated, so page state reloads and audio may briefly pause. URL, source settings,
audio routing and the source identity are retained. A failed source stays on CPU until it is recreated
or OBS restarts. Other sources and the OBS stream remain running.

CPU-buffer fallback is not a process-global GPU shutdown: CEF may still use the shared GPU process
to composite other browsers. For completely software rendering restart with `OBS_BROWSER_GPU=software`.
After the first successful paint the watchdog deliberately does not time out static/transparent pages.
An undetected GPU hang after that frame is therefore **not** guaranteed to recover automatically.
Fully transparent pixels are legitimate and are never treated as proof of GPU failure.

### Known alpha/color limitation

The GPU path preserves the existing premultiplied pixels and matches CPU output, but the inherited
OBS browser renderer is **not fully correct for semi-transparent sRGB compositing over white**.
For example, 50%-green over white measured `(187,220,187)` in both paths, rather than either correct
nonlinear `(128,255,128)` or linear `(188,255,188)` blending. The black/white reference audit documents
this clearly. Applying browser #533 alone is unsafe: the installed libobs lacks #13797's shaders,
state propagation and migration flag. No scene migration or global blend-method change is performed.

## Arch build (against the installed OBS SDK)

Use a normal user, not root:

```sh
sudo pacman -S --needed base-devel git cmake ninja obs-studio qt6-base nlohmann-json \
  libdrm libglvnd libx11 wayland curl bubblewrap ffmpeg
cef=$(bash scripts/fetch-cef.sh)
cmake -S . -B build -G Ninja -DCEF_ROOT_DIR="$cef" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build -j "$(nproc)"
DESTDIR="$PWD/stage" cmake --install build
```

CEF is ~332 MB compressed. Keep several GB of disk space outside small `/tmp` tmpfs mounts.
Only the CEF C++ wrapper and the browser plugin/helper compile; Chromium and OBS do not rebuild.
Repeated `cmake --build build` is incremental. `ccache` can be enabled with
`-DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_C_COMPILER_LAUNCHER=ccache`.
Vendor headers, wrapper and `libcef.so` **must be the exact same distribution**.
Rebuild the plugin after an OBS major-version upgrade; binary compatibility with another major is not promised.
Do not mix system CEF 154 with this plugin's CEF 156 wrapper/API hash.
CEF 156's existing experimental paint/client APIs compiled without changing the public source interfaces.
The standalone CMake entry point is Linux-only; when included by OBS, existing parent build helpers remain in use.

The install tree keeps the entire runtime in `/usr/lib/obs-browser-nvidia`, including `libcef.so`,
helper, locales, ICU/V8 data and PAK files. It does not overwrite `/usr/lib/cef` or an OBS package file.
CEF's `LICENSE.txt` must accompany redistributed binaries; see also upstream `COPYING`.

## Opt-in launcher without overwriting the working OBS

OBS 33 loads its built-in browser as a core module; simply adding a second plugin can produce
duplicate source IDs or still load the original. `scripts/obs-nvidia-browser` uses **bubblewrap only
for a temporary mount overlay** to select the private browser/helper/runtime at the original core
module path. All other core modules are passed through. No root, pacman overwrite or symlink changes
to `/usr/lib` are needed. **This is not a security sandbox:** files, display, devices and network remain accessible.

The launcher defaults `QT_NO_GLIB=1`: full OBS otherwise hit a GTK/Wayland initialization race
between CEF's manager thread and Qt's GLib dispatcher on this machine. Qt uses its Unix event
dispatcher instead. The isolated host did not expose this startup race. This workaround is scoped
to the experimental launcher, not the user's normal OBS session; test GTK-native dialogs/plugins
on your desktop. Do not remove it on this tested setup without repeating the frontend smoke test.

Close OBS before selecting a different runtime. Do not replace a loaded `.so` on disk.
To try the staged build with a fresh config (recommended):

```sh
mkdir -p "$PWD/test-results/obs-config"
XDG_CONFIG_HOME="$PWD/test-results/obs-config" \
OBS_BROWSER_RUNTIME_ROOT="$PWD/stage/usr/lib/obs-browser-nvidia" \
OBS_BROWSER_DATA_ROOT="$PWD/data" \
OBS_BROWSER_GPU=nvidia QT_QPA_PLATFORM=wayland bash scripts/obs-nvidia-browser
```

Native Wayland does **not** gain custom browser docks from this patch. The launcher defaults to
`QT_QPA_PLATFORM=xcb` for dock compatibility, but the GPU path must also pass XWayland validation;
consult the results. Keep native Wayland and XWayland results separate.

To roll back, quit this OBS and run ordinary `obs`: no installed core modules have changed.
For software mode use `OBS_BROWSER_GPU=cpu`. For logs add `OBS_BROWSER_DIAGNOSTICS=1`.
Upstream CEF runs with `no_sandbox=true`; this experiment does not improve that security limitation.

## Real-hardware tests

The test host uses the real installed libobs/OpenGL backend, Qt, CEF and your NVIDIA driver,
but **does not open the user's OBS config**, load streaming keys or start outputs.
It renders a 1280x720 scene at 60 FPS with 1/4 independent browser sources.

```sh
cmake -S . -B build -DOBS_BROWSER_BUILD_TESTS=ON
cmake --build build -j "$(nproc)"
DESTDIR="$PWD/stage" cmake --install build
python3 tests/benchmark.py
# Only supported native Wayland paths (GPU, CPU paint and both injected fallbacks):
python3 tests/benchmark.py --native-only --suffix=-repeat
```

Requires an active Hyprland/Wayland session, working XWayland, `nvidia-smi`, `ffmpeg`, Python 3 and
`wayland-client`. Test results/logs/screenshots stay in ignored `test-results/`. Runs refuse to
overwrite an existing case directory: rename/remove only your previous results before repeating.
Optional: `--case wayland-gpu-1-final --seconds 30`.

The fixture verifies opaque red, half-alpha green, transparent pixels, a WebGL blue rectangle,
CSS animation and a 440 Hz Web Audio tone routed through OBS. Source paint counters distinguish
browser FPS from OBS canvas FPS. CPU samples include the host's child processes and use one core
as 100%; `nvidia-smi` GPU utilization/VRAM are **whole GPU** measurements and can include other apps.
Import-failure and missing-callback injection are available only in builds made with
`OBS_BROWSER_BUILD_TESTS=ON`, via `OBS_BROWSER_TEST_GPU_FAILURE=import|timeout`.
Production/AUR builds disable these hooks. CI compiles tests but cannot validate NVIDIA rendering.

Additional hardware/reference audits (run after the ordinary build/staging commands):

```sh
python3 tests/alpha_audit.py      # prints observed vs linear/nonlinear math; known legacy mismatch
python3 tests/tearing_audit.py    # uniform-frame samples under four bounded CPU stress workers
python3 tests/console_audit.py   # default log visibility vs explicit quiet-mode summary
ctest --test-dir build --output-on-failure   # pure GPU-policy unit tests, no display/GPU required
```

The tearing test checks sampled frames, not every frame or every possible GPU scheduling pattern.
The alpha audit deliberately does not report the known premultiplied-sRGB defect as fixed.

### Optional developer features

- **Source Inspect / DevTools (#528 adaptation):** enable `-DOBS_BROWSER_ENABLE_DEVTOOLS=ON`, rebuild
  and restage. Default is **OFF**, including the AUR package. The source properties get an Inspect
  button; DevTools uses a separate minimal client so source CSS/menu callbacks cannot corrupt its UI.
  It closes before its source. No remote-debugging port is opened. Local smoke test:

  ```sh
  python3 tests/devtools_audit.py  # verifies one actual window for two requests, GPU/audio and teardown
  # Or run the host directly:
  OBS_BROWSER_TEST_DEVTOOLS=1 QT_QPA_PLATFORM=wayland OBS_BROWSER_GPU=nvidia \
    build/browser-test-host "$PWD/stage/usr/lib/obs-browser-nvidia/obs-browser.so" \
    "$PWD/data" "$PWD/tests/fixture.html" "$PWD/test-results/devtools-local" 1 10
  ```

- **Quiet console (#440 adaptation):** `OBS_BROWSER_QUIET_CONSOLE=1` lowers page error/fatal log
  levels and emits a warning/error/fatal-count summary per browser client on reload/close. Default
  log levels stay unchanged. This is not equivalent to suppressing CEF's own diagnostic stderr.
- **Camera/microphone (#530):** no silent grant has been added. The stale PR duplicates existing
  permission handlers and grants every navigated origin; it needs an explicit origin/revocation
  policy and real device/portal tests before adoption. No camera/mic was accessed by these tests.

For a fresh-config **full OBS frontend** smoke test of the mount overlay, screenshots and `obsstudio.getStatus`:

```sh
python3 tests/frontend_smoke.py --platform wayland
# Optional separate XWayland run (currently may fall back to CPU):
python3 tests/frontend_smoke.py --platform xcb --dock --name frontend-xcb
```

This starts a separate `obs --multi` with a random authenticated test-only websocket on port 4456.
The client uses loopback; OBS may listen on all interfaces, so retain your firewall policy.
It never starts streaming/recording, and closes only that test OBS process group.
Do not run concurrently with CPU/GPU benchmarks, as its GPU load would contaminate the measurements.

## AUR packaging and publication

`packaging/aur/PKGBUILD` builds **obs-browser-nvidia-git**, installing a private runtime plus
`obs-nvidia-browser`. It can coexist with the official `obs-studio` package. No `--overwrite`,
`provides=obs-studio`, or false conflicts with the main OBS package are used.

Before publication replace `_repo` with the actual GitHub fork URL, update `url`, then run:

```sh
cd packaging/aur
OBS_BROWSER_FORK_URL=https://github.com/YOUR-ACCOUNT/obs-browser.git makepkg -si
makepkg --printsrcinfo > .SRCINFO
```

Before remote publication, a committed local clone can also be packaged with
`OBS_BROWSER_FORK_URL=file:///absolute/path/to/obs-browser-nvidia makepkg -s`.
This tests VCS source retrieval without GitHub credentials. A local test is not a clean-chroot or
remote CI validation. Set the real permanent URL and regenerate `.SRCINFO` before AUR submission.

Publish the source branch as `experimental/nvidia-cef156` (or update the PKGBUILD branch).
The current placeholder intentionally cannot fetch an unrelated upstream repository as if it had
these patches. `.SRCINFO` is generated only after setting the real URL. AUR submission and creating
a remote GitHub fork require the owner's credentials and are not performed by a local build.

`.github/workflows/linux-nvidia.yml` compiles on Arch, stages the private CEF runtime and uploads
the plugin/helper/test-host binaries. Downloaded artifacts alone lack the large CEF runtime;
use the pinned fetch script plus install instructions. Keep GitHub Actions tokens read-only.

## Remaining checks before streaming

See `docs/VALIDATION.md`. In particular: full OBS frontend with real docks, user overlays and OBS JS
bindings, sustained multi-source 1080p/4K load, scene hide/show/shutdown/resize, driver variants,
and GPU reset behavior. A successful synthetic fixture is not a guarantee for every website.
Do not enable experimental acceleration for an important live stream without a rehearsal.
