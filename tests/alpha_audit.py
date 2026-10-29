#!/usr/bin/env python3
"""Compare captured colors against linear and nonlinear sRGB references."""
import json
import argparse
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--suffix', default='')
args = parser.parse_args()


def decode(c):
    return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4


def encode(c):
    return c * 12.92 if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055


patches = [('gray50', 50, (128 / 255,) * 3, .5), ('green50', 200, (0, 1, 0), .5),
           ('white75', 350, (1, 1, 1), .75), ('white25', 500, (1, 1, 1), .25)]
results = []
for mode in ['cpu', 'nvidia']:
    for background, bg in [('white', 1), ('black', 0)]:
        folder = root / 'test-results' / f'alpha-{mode}-{background}{args.suffix}'
        folder.mkdir(parents=True, exist_ok=False)
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM='wayland', OBS_BROWSER_GPU=mode, OBS_BROWSER_TEST_BACKGROUND=background)
        with (folder / 'host.log').open('w') as log:
            subprocess.run([str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
                            str(root / 'data'), str(root / 'tests/alpha-fixture.html'), str(folder), '1', '7'],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=True)
        frames = sorted(folder.glob('frame-*.png'))
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(frames[-1]), '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
        for name, x, color, alpha in patches:
            p = (50 * 1280 + x) * 4
            observed = list(data[p:p + 4])
            nonlinear = [round(255 * (c * alpha + bg * (1 - alpha))) for c in color]
            linear = [round(255 * encode(decode(c) * alpha + decode(bg) * (1 - alpha))) for c in color]
            results.append({'mode': mode, 'background': background, 'patch': name, 'observed_rgba': observed,
                            'reference_nonlinear_rgb': nonlinear, 'reference_linear_rgb': linear})
output = root / 'test-results' / f'alpha-audit{args.suffix}.json'
output.write_text(json.dumps(results, indent=2))
print(output.read_text())
print('Reference audit only: no claim that legacy source rendering implements either complete #533/#13797 path.')
