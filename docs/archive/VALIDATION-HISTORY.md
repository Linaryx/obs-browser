# Historical validation record

Records from before the CEF 156.0.30 refresh (2026-11-13). Kept for traceability;
they describe older revisions and are not current claims. Current checks:
[../VALIDATION.md](../VALIDATION.md).

## CPU compatibility correction — 2026-11-01

The first delivered archive,
`obs-browser-nvidia-arch-x86_64-eba2d30-dirty-de43e3a638a5.tar.zst`, is **not a valid Xeon test build**.
Its `obs-browser-page` ELF `GNU_PROPERTY_X86_ISA_1_NEEDED` value is `0xf`, including x86-64-v4;
the Xeon E5-2680 v4 supports x86-64-v3. Local inspection also finds that requirement in the
build host's glibc `Scrt1.o`, while the helper compile command has no `-march` override and GCC's
default is baseline x86-64. Changing only compiler flags would not replace that startup object.
The archive is preserved as evidence and must not be used for target measurements.

The user reports that the successful NVIDIA numbers and real DMA-BUF callbacks came from the
installed **r755 (x86-64-v3)** build, not this archive. The supplied log path
`test-results/bundle-eba2d30-wayland/obs.log` is absent from the current checkout. This identifies
the evidence as user-reported; no target-machine log or NVIDIA rerun is claimed here. All
historical NVIDIA tables below belong to that reported installed-build context, not a validation
of the newly packaged binaries. The current AMD checks below remain local AMD checks only.

The packaging regression now checks every bundled ELF, including nested runtime libraries,
and rejects declared required ISA bits outside baseline/v2/v3. Synthetic ELF fixtures verify
baseline/v3 acceptance, unknown treatment of absent notes, rejection of v4/unknown bits in a
nested library, and failure before archive/checksum creation when the helper requires v4.
Per-file hashes, required ISA notes and compiler flags are saved in `BUILD-INFO.json`.
This is a metadata guard, not proof that unmarked binaries or recipient system libraries meet
the target CPU's instruction set. Clean generic/v3 build inputs and target execution are still needed.

## Corrected v3 build verification — 2026-11-01

The corrected binaries were built in clean generic Arch, using image digest
`sha256:624bdc7fc6615155d67bc34cf7146c0c9fd0e3c92943977da63a630e4ca49c30`, glibc
`2.44+r50+g1848099f063e-1`, GCC `16.2.1+r23+gd564253eb6c8-1`, OBS SDK 33.0.1 and Qt 6.12.0.
The generic `Scrt1.o` declares baseline x86-64 (Linux ABI 4.4); both C and C++ builds explicitly
use `-march=x86-64-v3 -mtune=generic`. CEF remains the pinned stock prebuilt 156.0.14.

- All five CTest checks passed. The staged startup audit passed two iterations each of all four
  modes, including initialization failure and clean shutdown.
- The two fallback/lifecycle cases passed: two browser creations with shutdown-on-hide disabled,
  three with it enabled, and a peak of one attached browser in both. CPU paint counts were 809
  and 629 respectively. These are new runs, distinct from the earlier host-build counts below.
- Release binaries were staged with `OBS_BROWSER_BUILD_TESTS=OFF` and
  `OBS_BROWSER_ENABLE_DEVTOOLS=OFF`.
- The ISA metadata guard passed all five bundled ELF files. The helper declares required baseline
  x86-64 and used v3; the other four files lack an ISA-needed note and remain metadata-unknown.
- Under QEMU's Haswell CPU model the old helper failed in the loader with
  `CPU ISA level is lower than required` (exit 127). The corrected helper reached
  `CefExecuteProcess`, returning -1 (exit 255), as expected without a subprocess type. This is
  an entry-point check, not a complete CEF rendering or NVIDIA test under emulation.
- Installed OBS 33.0.0 loaded the corrected Release plugin/private CEF through the launcher on
  native Wayland in **CPU mode** on the AMD host. Exact screenshot colors/alpha, WebGL, animation
  and the OBS JavaScript callback passed. Streaming/recording stayed inactive; shutdown was clean.

Reproduce with `bash scripts/build-arch-v3-bundle.sh`. Outputs, toolchain/ELF notes and check logs
are under `build-v3/`, and the default complete test archive is written to `build-v3/dist/`.
The workflow uses prebuilt CEF and does not resume the cancelled Chromium source rebuild.
No current target NVIDIA result is claimed; installed r755 evidence remains separately attributed above.

## Earlier local host verification — 2026-11-01

The current build host has AMD graphics, not NVIDIA. It runs Arch Linux with the OBS 33.0.0
SDK, Qt 6.12.0 and GCC 16.2.1; the private runtime remains CEF 156.0.14 / Chromium 156.0.8078.48.

- All five CTest checks passed: GPU policy, benchmark pixel validation, launcher defaults,
  relocatable test-bundle packaging and safe rejection of CEF work before initialization.
- The staged CEF startup audit passed two iterations each of pre-initialization, immediate
  initialization/shutdown, immediate source creation/destruction, and locked-profile initialization
  failure with clean shutdown.
- A 12-second native Wayland **CPU-paint** fixture run produced exact red `(255,0,0,255)`,
  half-green `(0,128,0,128)`, WebGL blue `(0,0,255,255)` and clear `(0,0,0,0)` samples, changing
  animation frames and routed audio. This verifies the fallback rendering baseline, not NVIDIA
  DMA-BUF import or performance.
- The bundle/launcher smoke tests use disposable fake runtimes to check archive completeness,
  private module overlays, relocation and config isolation. They do not prove hardware rendering.
- The software-rendering overlapping-recreation regression passed both visibility modes after
  the fallback fix. With shutdown-on-hide disabled it recorded two browser creations; with it
  enabled it recorded three. Each finished with one attached browser and a peak of one, with
  755 and 626 CPU paint callbacks respectively. This checks duplicate-creation prevention,
  hide/show and resizing without requiring NVIDIA.
- The initial host distribution build compiled in `Release` with `OBS_BROWSER_BUILD_TESTS=OFF` and
  `OBS_BROWSER_ENABLE_DEVTOOLS=OFF`. Its runtime excludes test-only failure injection hooks.
- A 24-second AMD watchdog run received no accelerated callbacks and switched once to CPU
  paint after 15 seconds. It exited cleanly after 484 CPU paint callbacks and 1,091,584 routed
  audio samples; post-fallback screenshots passed exact color/alpha and animation checks. This
  validates missing-first-frame recovery, not NVIDIA rendering.
- Full OBS 33 loaded the initial host Release plugin and private CEF through the `bubblewrap` launcher
  in native Wayland **CPU** mode. Screenshot colors/alpha, WebGL, animation and the OBS JavaScript
  status callback passed. Streaming and recording stayed inactive; shutdown was clean with zero
  reported OBS leaks.
- A separate Xvfb/software full-frontend run passed 2D colors/alpha/animation, the OBS JavaScript
  callback, startup and shutdown, but its WebGL-blue sample was transparent. That environment
  did **not** pass the complete rendering fixture and supplies no GPU-rendering evidence.

NVIDIA acceleration was **not rerun locally** for this revision. The measurements below are
historical records inherited from earlier work on an RTX 5060/615.78.08 system; their ignored raw
artifacts are not included in the source checkout and they do not validate the current changes.

CEF [#4313](https://github.com/chromiumembedded/cef/issues/4313) and
[#4314](https://github.com/chromiumembedded/cef/pull/4314) identify missing **producer** GPU
synchronization in the pinned CEF 156 path. The plugin's `glFinish` only completes the consumer
copy before callback return; it does not wait for a missing producer dependency. Historical
nonuniform-frame sampling cannot establish freedom from tearing or partially rendered frames.
This remains an experimental test build pending an upstream CEF/Chromium fix and NVIDIA retest.

## Historical NVIDIA validation — reported installed r755 (v3)

Historical hardware: NVIDIA GeForce RTX 5060, driver 615.78.08. CachyOS/Arch, Hyprland.
Historical SDK: OBS 33.0.0; compiler GCC 16.2.1. CEF 156.0.14 / Chromium 156.0.8078.48.

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

## Dirty-region copy audit (2026-11-02)

The accelerated Linux path now copies only CEF's `capture_update_rect` instead of the whole visible
frame, and keeps the previous texture contents for unchanged pixels. This is safe because CEF
describes that rectangle as the updated/dirty area; a full copy is forced on first use, resize,
format change, `extra_texture` sources, or when CEF supplies dirty rectangles without a usable
update rectangle. `OBS_BROWSER_FULL_COPY=1` restores the old full-frame behavior for comparison.

Measured in the real OBS frontend on the RTX 5060, 1920x1080, 10 browser overlays, 5-second
statistics intervals:

| Copy mode | Browser frames | Import ns/frame | Copy ns/frame | Full / partial |
|---|---:|---:|---:|---:|
| Full frame | 499 | 0.270 ms | 0.260 ms | 499 / 0 |
| Dirty region | 1111 | 0.277 ms | 0.258 ms | 7 / 1104 |
| Dirty region + GL fence (`OBS_BROWSER_GPU_FENCE=1`) | 1111 | 0.277 ms | 0.258 ms | 7 / 1104 |

The per-frame CPU cost is dominated by EGL/DMA-BUF import and the completion wait, not by the
copied area, so this change does not by itself lower measured CPU time. It does reduce the amount of
GPU bandwidth consumed by mostly static overlays. A GL fence did not beat `glFinish()` on this
driver and remains a diagnostic opt-in. The pinned CEF 156.0.30 includes the upstream
producer-synchronization fix for #4313 (`57389f04a61a`, shipped from 156.0.28). Consumer
`glFinish` remains necessary for this fork's own copy lifetime but is not a substitute for
the producer fix. These measurements predate the new CEF pin.

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
  Setting `QT_NO_GLIB=1` worked around that crash, but later testing showed it also disables the
  dispatcher OBS needs for xdg-desktop-portal ScreenCast responses: screen/window capture then
  never receives `CreateSession`/`SelectSources` replies and stays black. The launcher therefore
  leaves `QT_NO_GLIB` unset by default and exposes the old workaround as
  `OBS_BROWSER_QT_NO_GLIB=1` for debugging only. With the default, the CEF 156 NVIDIA browser and
  XDPW screen capture both run simultaneously.
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
