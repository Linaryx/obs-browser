# Validation record

Hardware: NVIDIA GeForce RTX 5060, driver 615.78.08. CachyOS/Arch, Hyprland.
Installed SDK: OBS 33.0.0; compiler GCC 16.2.1. CEF 156.0.14 / Chromium 156.0.8078.48.

## Initial implementation smoke tests

- Standalone plugin/helper/CEF wrapper/test host compiled and staged without rebuilding OBS.
- Native Wayland: first successful `OnAcceleratedPaint` DMA-BUF frame, NVIDIA modifier
  `0x0300000000606014`, 1280x720. Fixture rendered with animation, WebGL and routed audio.
- XWayland/default flags: no accelerated callbacks in the first smoke run; 15-second watchdog
  recreated the browser on CPU. Output and audio were present after fallback.
- The host deliberately has no frontend callback provider: the `obs_frontend_add_event_callback`
  warning in its log is expected, and frontend-only JS calls cannot be validated by this host.

## Benchmark matrix (22 seconds per case)

The second complete run (`*-r2/result.json`) passed rendering/audio and exited cleanly in every
case. XWayland acceleration itself still failed and correctly triggered CPU fallback. Early host
shutdown crashes were traced to the host not draining OBS's asynchronous destroy queue; the host
now removes sources/scenes and drains that queue before unloading CEF. No renderer workaround was
used to hide those teardown failures.

| Mode | Sources | Browser paint FPS* | OBS render ms (mean) | CPU tree %** | Whole-GPU utilization %*** | Result |
|---|---:|---:|---:|---:|---:|---|
| Native Wayland GPU | 1 | 60.02 | 0.443 | 38.8 | 10.3 | GPU, no CPU fallback |
| Native Wayland CPU paint | 1 | 59.75 | 0.449 | 30.4 | 13.3 | CPU paint, WebGL retained |
| Native Wayland GPU | 4 | ~59.99 each | 0.560 | 110.2 | 12.9 | All 4 GPU, no CPU fallback |
| Native Wayland injected import failure | 1 | ~59.98 CPU | 0.457 | 47.1 | 16.2 | Reloaded once on CPU |
| Native Wayland injected missing callback | 1 | ~60 after timeout | 0.661 | 40.1 | 11.7 | 15s watchdog, CPU output |
| XWayland GPU/default | 1 | ~60 after timeout | 0.402 | 39.0 | 14.5 | GPU unsupported here, CPU fallback |
| XWayland `--use-gl=angle --use-angle=gl` | 1 | ~60 after timeout | — | 38.2 | — | Same limitation |

\* Paint FPS is derived from per-source paint counters between first and last capture, not canvas FPS.
OBS canvas remained 60 FPS. The timeout cases have no output before fallback, so their full-run
average is lower, approximately 18 FPS; ~60 applies only after recovery.

\** Host plus CEF descendants, includes startup/teardown, one core = 100%. Sampling misses CPU of
processes that exit between samples; these short runs are indicative, not a controlled performance study.

\*** Global `nvidia-smi` samples include the user's already-running desktop/OBS. VRAM ranged roughly
1.9–2.3 GiB globally; it is not an isolated plugin allocation measurement.

**No speedup claim:** on this simple fixture GPU paint actually used more CPU than CPU paint.
The conservative per-frame GPU completion barrier has a cost. Hardware rendering is confirmed, but
optimizing cross-process fences and comparing heavier real overlays is still required before claiming
lower CPU use or better performance. The build optimization (plugin-only incremental compilation) is proven.

All successful GPU fixtures verified exact sample values: opaque red `(255,0,0,255)`, half-alpha
green `(0,128,0,128)`, WebGL blue `(0,0,255,255)`, clear `(0,0,0,0)`; changing animation screenshots
and non-zero routed audio frames. No production patch guesses failure from transparent pixels.

Raw results remain in ignored `test-results/`; no real overlay URLs or stream credentials are used.

## Expanded PR-audit tests

- All five supported native Wayland benchmark cases were rerun after the policy/fallback changes
  (`*-audited`): GPU 1/4, CPU paint, injected import failure and injected first-frame timeout all
  passed pixel/animation/WebGL/audio checks and exited cleanly. CPU tree means were about 39.4%
  for GPU 1, 31.4% for CPU 1 and 109.1% for GPU 4. These are indicative, not a claimed speedup.
- Exact `--use-angle=gl-egl` on XWayland crashed CEF GPU children (139/133), unlike the successful
  native default. CPU output eventually resumed but WebGL did not. The override remains explicit
  diagnostic opt-in; it is not forced by the launcher or promoted as a driver fix.
- `tests/tearing_audit.py`: **176** non-blank uniform-frame samples, **0** nonuniform samples,
  five colors observed, four bounded CPU stress workers, actual accelerated callback and no fallback.
  This tests sampled consistency only, not an exhaustive absence of tearing under every workload.
- `tests/alpha_audit.py`: CPU/GPU samples were identical over black and white. The inherited
  premultiplied-sRGB compositing defect is real: half-green over white `(187,220,187)` instead of
  correct nonlinear `(128,255,128)` or linear `(188,255,188)`; 75%-white over white measured 227
  rather than 255. Neither #533 nor its absent libobs prerequisite is falsely reported as fixed.
- `tests/console_audit.py`: default error stays at OBS warning level; explicit quiet mode moves it
  to debug and emits exactly one summary with `warnings=1 errors=1 fatal=0`. Both cases passed.
- `tests/devtools_audit.py`, feature enabled: two Inspect requests created **one** actual DevTools
  window and one close callback, with continuing GPU frame/audio counts, correct fixture pixels
  and no fallback; process exited cleanly. The default-off build is separately compiled in packaging.
- `frontend-xcb-dock-cpu`: full fresh-config OBS, synthetic custom dock loaded at its real tiled
  viewport **78x877**, source fixture pixels/animation/WebGL and `obsstudio.getStatus` passed,
  no output started, clean exit with zero reported OBS leaks. The prior test's `width > 100`
  assertion was a harness error: a right dock can legitimately shrink to its ~80px minimum.
  This is not a manual keyboard/focus, login, or repeated resize stress test.
- Pure `gpu-policy` CTest passed. `clang-format --dry-run --Werror` on changed C++ files,
  Python compilation, shell syntax checks and `git diff --check` passed locally.

## Full OBS frontend and packaging

- A fresh-config OBS 33 frontend successfully loaded the private CEF 156 runtime and displayed the
  GPU fixture through the opt-in mount overlay. GPU import, pixel/alpha checks, WebGL, animation
  the `obsstudio.getStatus` JavaScript callback, and non-streaming/non-recording state were confirmed
  in `frontend-wayland-verified`.
- Default Qt GLib dispatch caused a real GTK/Wayland initialization crash in CEF's manager thread.
  The experimental launcher now sets `QT_NO_GLIB=1`, selecting Qt's Unix event dispatcher. The
  subsequent frontend run produced correct accelerated output and exited with zero reported OBS
  memory leaks. This launcher-specific integration workaround must be included when testing.
- `makepkg --noextract --nodeps --nocheck --force` built the private runtime package locally from
  this working tree (not a remote clone or a clean chroot). CEF's default Fortify=2 conflicted with
  CachyOS Fortify=3; the standalone finder now retains distro hardening instead of redefining it.
  Package: `obs-browser-nvidia-git-2.27.5.r749.gd4db73e-1-x86_64.pkg.tar.zst` (~294 MiB).
  The package was built, not installed. Its version names the upstream base; uncommitted fork
  patches were included from the local test source tree. Newer commits/packages supersede this initial artifact.
- The fork and AUR package have not been published. GitHub Actions has not run remotely.

## Live-stream load (local RTMP, not Twitch)

Test system as above. Scene `01 · Начало`: 10 browser overlays (9 visible, 1 hidden), capture sources
disabled. 1920×1080 60 FPS, x264 `veryfast`, 6000 kbps. `tests/stream_audit.py`, 60 seconds per stream.

Single stream: fork GPU render 2.68 ms, fork CPU 3.51 ms, stock (NVIDIA blocked) 2.99 ms; all accepted,
zero output drops, render drops 85–90 of ~4475.

Five parallel streams per preset (`test-results/p-*`):

| Preset | Tree CPU | Output dropped per stream | Render dropped per stream |
|---|---|---|---|
| Fork GPU | ~314% | 0–45 | ~170–190 |
| Fork CPU | ~560% | 1108–1510 | 291–583 |
| Stock | ~568% | 435–1700 | 318–432 |

Interpretation: fork CPU and stock load the CPU similarly. The GPU path removes most CPU load and
dropped output frames. One run per preset: not a statistical comparison.

## Not proven by compilation or this fixture

- Custom XWayland docks, Twitch/Twir/third-party overlays and the complete OBS JS binding surface.
- Native Wayland docks (upstream unsupported, not implemented here).
- Long-duration streaming/recording under load; 1080p/4K/HiDPI, resize/hide/show, hundreds of reloads.
- Other GPUs/drivers, multi-GPU/PRIME, suspend/resume and device resets.
- A GPU hang after a successful first frame that produces no further callbacks.
- Reproducible bit-identical output (CEF is pinned; rolling Arch toolchain/dependencies are not).
- Remote GitHub Actions execution, clean-chroot package build or AUR acceptance.
