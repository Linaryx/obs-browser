# Build and package

This fork builds against the installed OBS 33 SDK. OBS and Chromium are not rebuilt.

## Requirements

- Arch Linux or derivative, x86-64-v3 CPU or newer, OBS Studio 33, Qt 6, Wayland session
- NVIDIA driver with GBM/EGL DMA-BUF support (for the GPU path)
- `bubblewrap` (temporary mount overlay, not a security sandbox)

```sh
sudo pacman -S --needed base-devel git cmake ninja obs-studio qt6-base nlohmann-json simde \
  libdrm libglvnd libx11 wayland curl python bubblewrap zstd
```

## Fetch CEF and build

`scripts/fetch-cef.sh` downloads the pinned CEF **156.0.30** minimal distribution,
verifies its SHA256 and prints the extracted path.

```sh
cef=$(bash scripts/fetch-cef.sh)
cmake -S . -B build -G Ninja -DCEF_ROOT_DIR="$cef" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build -j "$(nproc)"
DESTDIR="$PWD/stage" cmake --install build
```

`DESTDIR` stages everything under `stage/usr/lib/obs-browser-nvidia`; system directories
and the OBS package are untouched. The staged launcher is
`stage/usr/bin/obs-nvidia-browser`, together with its desktop entry.

## Arch package

The `PKGBUILD` in `packaging/aur` builds `obs-browser-nvidia-git` from this repository.
It requires `obs-studio<34` because the standalone build targets the OBS 33 SDK ABI, and
depends on `qt6-wayland` for the native Wayland launcher.

```sh
cd packaging/aur
makepkg -si
```

To use an existing checkout as the source:

```sh
OBS_BROWSER_FORK_URL=file:///absolute/path/to/obs-browser makepkg -si
```

Regenerate the metadata after editing `PKGBUILD`:

```sh
makepkg --printsrcinfo > .SRCINFO
```

## Test bundle

Build against generic Arch startup objects in Docker, independent of an optimized host glibc:

```sh
bash scripts/build-arch-v3-bundle.sh
```

This downloads the prebuilt CEF runtime, builds with
`-march=x86-64-v3 -mtune=generic`, runs the startup/fallback checks and a QEMU Haswell
helper-entry check, then packages Release binaries with test hooks and DevTools disabled.
It does not rebuild CEF/Chromium. Output is in `build-v3/`; archives in `build-v3/dist/`.
Docker must be available to the current user. To reuse an extracted CEF, add
`--cef-root /absolute/path`.

Packaging rejects bundled ELF files declaring requirements above x86-64-v3 before writing
an archive, and records compiler flags plus per-file ISA metadata and hashes. Passing
compiler flags alone cannot make a v4 glibc startup object compatible.

For an already built compatible runtime:

```sh
bash scripts/package-test-build.sh /absolute/path/to/build /absolute/path/to/dist
```

Share the `.tar.zst` and `.sha256` from `build-v3/dist/`. The archive contains the plugin,
helper, complete private CEF runtime, data, licenses, corresponding plugin source and build
provenance. It requires Arch/CachyOS x86_64 with OBS 33, Qt 6, `qt6-wayland` and
`bubblewrap`; it does not target Flatpak OBS or arbitrary Linux ABIs.

The recipient extracts it and runs `./obs-nvidia-browser` inside the extracted folder. That
launcher keeps settings and the CEF cache in the bundle's `config/` directory. Create a test
scene or import a copy of the scene collection, enable **Browser Hardware Acceleration**, and
restart the test OBS. `OBS_BROWSER_TEST_CONFIG_HOME=/absolute/path` selects another isolated
config. The installed system launcher continues to use normal OBS settings.

## Tests

```sh
cef=$(bash scripts/fetch-cef.sh)
cmake -S . -B build -DOBS_BROWSER_BUILD_TESTS=ON -DCEF_ROOT_DIR="$cef" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build -j "$(nproc)"
ctest --test-dir build --output-on-failure
DESTDIR="$PWD/stage" cmake --install build
```

Additional host tests are documented in [VALIDATION.md](VALIDATION.md). Results go to the
git-ignored `test-results/` directory.
