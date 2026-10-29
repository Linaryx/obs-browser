#!/usr/bin/env python3
"""Exercise source hide/show, shutdown/recreation and resize on native Wayland."""
import json
import argparse
import os
from pathlib import Path
import re
import subprocess
from benchmark import inspect_frames

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--suffix', default='')
args = parser.parse_args()
results = []
for shutdown in [False, True]:
    folder = root / 'test-results' / (('lifecycle-shutdown' if shutdown else 'lifecycle-visible') + args.suffix)
    folder.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='wayland', OBS_BROWSER_GPU='nvidia', OBS_BROWSER_TEST_LIFECYCLE='1',
               OBS_BROWSER_TEST_WIDTH='1920', OBS_BROWSER_TEST_HEIGHT='1080')
    env.pop('OBS_BROWSER_TEST_LEGACY_COPY', None)
    if shutdown:
        env['OBS_BROWSER_TEST_SHUTDOWN'] = '1'
    else:
        env.pop('OBS_BROWSER_TEST_SHUTDOWN', None)
    with (folder / 'host.log').open('w') as log:
        subprocess.run([str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
                        str(root / 'data'), str(root / 'tests/fixture.html'), str(folder), '1', '22'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True)
    text = (folder / 'host.log').read_text()
    pixels = inspect_frames(folder, 1920, 1080)
    result = {'shutdown': shutdown, 'pixels': pixels, 'fallback': 'CPU paint fallback' in text,
              'gpu_frames': [int(n) for n in re.findall(r'PAINT source=test-0 gpu=(\d+)', text)]}
    result['passed'] = pixels['passed'] and not result['fallback'] and result['gpu_frames'][-1] > 100
    (folder / 'result.json').write_text(json.dumps(result, indent=2))
    results.append(result)
print(json.dumps(results, indent=2))
raise SystemExit(0 if all(result['passed'] for result in results) else 1)
