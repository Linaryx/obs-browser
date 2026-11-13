#!/usr/bin/env python3
"""Regress overlapping fallback/recreation, hide/show and resizing without NVIDIA.

Build with OBS_BROWSER_BUILD_TESTS=ON and stage the private CEF runtime first.
Run with xvfb-run -a python3 tests/fallback_audit.py --output-dir test-results/fallback-race.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--executable', type=Path, default=ROOT / 'build/browser-test-host')
parser.add_argument('--module', type=Path, default=ROOT / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so')
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
args.output_dir.mkdir(parents=True, exist_ok=False)
results = []
for shutdown in [False, True]:
    folder = args.output_dir.resolve() / ('shutdown' if shutdown else 'visible')
    folder.mkdir()
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='xcb', QT_NO_GLIB='1', OBS_BROWSER_GPU='software',
               LIBGL_ALWAYS_SOFTWARE='1', OBS_BROWSER_TEST_FALLBACK_RACE='1',
               OBS_BROWSER_TEST_LIFECYCLE='1')
    for key in ['OBS_BROWSER_TEST_GPU_FAILURE', 'OBS_BROWSER_PROXY', 'OBS_BROWSER_TEST_LEGACY_COPY',
                'OBS_BROWSER_TEST_SHUTDOWN']:
        env.pop(key, None)
    if shutdown:
        env['OBS_BROWSER_TEST_SHUTDOWN'] = '1'
    log_path = folder / 'host.log'
    with log_path.open('w') as log:
        result = subprocess.run([str(args.executable.resolve()), str(args.module.resolve()),
                                 str(ROOT / 'data'), str(ROOT / 'tests/fixture.html'),
                                 str(folder), '1', '16', '--password-store=basic'],
                                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=45)
    text = log_path.read_text(errors='replace')
    states = [tuple(map(int, values)) for values in re.findall(
        r'BROWSERS source=test-0 creations=(\d+) attached=(\d+) peak=(\d+)', text)]
    paints = [int(value) for value in re.findall(r'PAINT source=test-0 gpu=\d+ cpu=(\d+)', text)]
    expected_creations = 3 if shutdown else 2
    passed = (result.returncode == 0 and 'FALLBACK_RACE requested=1' in text and
              'injected overlapping recreation' in text and bool(states) and
              states[-1] == (expected_creations, 1, 1) and max(state[2] for state in states) == 1 and
              bool(paints) and paints[-1] > 0)
    record = {'shutdown': shutdown, 'passed': passed, 'exit_code': result.returncode,
              'states': states, 'cpu_frames': paints, 'log': str(log_path)}
    results.append(record)
    print(json.dumps(record), flush=True)
(args.output_dir / 'result.json').write_text(json.dumps(results, indent=2))
raise SystemExit(0 if all(result['passed'] for result in results) else 1)
