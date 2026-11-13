# Validation record

## CEF refresh — 2026-11-13

- Dependency: CEF `156.0.30+g6028375`, Chromium `156.0.8078.96`, latest Linux64 stable
  in the Spotify distribution index at the time of the update.
- Minimal archive SHA1 matches the upstream index:
  `0b4c2189e3b93033bbef13add1a86f66849c1e62`.
- Pinned SHA256: `356db99d653698aa9ba78b22965032b4fa5b23ba079ffdbaa5d28a8530f04011`.
- Contains M156 backport `57389f04a61a` for the NVIDIA producer synchronization issue #4313.
- Local test environment: OBS `33.0.1-1.1`, Qt `6.12.0`, RTX 5060, NVIDIA `620.70.06`.
- Release test build against the new SDK succeeded. All five CTest checks passed.
- Startup audit passed two iterations each of preinit, initialize, source and locked-profile
  initialization failure/clean shutdown, with `--disable-gpu`.
- Corrected the launcher regression's stale expectation of default `QT_NO_GLIB=1`;
  default-unset and explicit `OBS_BROWSER_QT_NO_GLIB=1` cases now pass.
- Native Wayland fixture passed in NVIDIA and CPU modes (18 seconds each):
  colors, premultiplied alpha, transparency, WebGL and animation. NVIDIA delivered
  accelerated DMA-BUF frames with no CPU fallback; both processes exited cleanly.
- Fallback/lifecycle regression passed both shutdown-on-hide variants: two and three
  browser creations respectively, maximum one attached browser, clean exit.
- Production Release build has tests and DevTools disabled. Its separate 15-second
  native Wayland NVIDIA fixture passed the same pixel checks, delivered DMA-BUF frames
  without fallback and exited cleanly.
- Bundled ELF ISA metadata guard passed all five files; the helper declares at most
  x86-64-v3. This is not an opcode audit.
- These are short fixture/lifecycle checks, not exhaustive synchronization, resize,
  screencast or real streaming tests. No new performance comparison is claimed.

Builds for this refresh were made outside the repository; selected logs, screenshots and
JSON results are preserved in ignored `test-results/cef156-20261113/`. The package was built
but not installed during that session.

Older records are preserved in
[archive/VALIDATION-HISTORY.md](archive/VALIDATION-HISTORY.md).
