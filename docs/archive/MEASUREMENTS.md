# Historical measurements

These records were produced on the test system below and are kept for context.
They are **not** evidence for the current revision or for another GPU/driver.
Current checks are summarized in [../VALIDATION.md](../VALIDATION.md).

## Test system at the time of measurement

| | |
|---|---|
| OS | CachyOS (Arch-based), kernel 7.3.0-4-cachyos |
| Session | Hyprland, native Wayland |
| CPU | Intel Xeon E5-2697A v4, 32 threads |
| RAM | 31 GiB |
| GPU | NVIDIA GeForce RTX 5060, driver 615.78.08 |
| OBS | 33.0.0 |
| CEF | 156.0.14 (plugin, private runtime); 154 (stock package) |

## Historical streaming test

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

In this historical run, the GPU path used about 45% less CPU and dropped far fewer output frames
under five parallel 1080p60 streams. CPU paint and stock behaved about the same. These measurements
are not a current performance guarantee or evidence that producer synchronization is correct.
Single runs are noisy; treat the single-stream render times as indicative only.
Five parallel 1080p60 CPU streams already saturate this machine; do not expect live use at that load.

## x86-64-v4 archive

The first delivered archive,
`obs-browser-nvidia-arch-x86_64-eba2d30-dirty-de43e3a638a5.tar.zst`, is not a valid
Xeon test build. Its `obs-browser-page` helper declared x86-64-v4 because the build
host's glibc startup object required it. Passing `-march` alone does not replace that
startup object. The archive is preserved only as an invalid-build record.

The user reports that the successful NVIDIA numbers came from the installed r755
(x86-64-v3) build, not from that archive. Its log is absent from this checkout, so the
attribution is user-provided evidence. New packages enforce a declared ISA ceiling of
x86-64-v3 for every bundled ELF; that is a metadata guard, not an opcode audit.
