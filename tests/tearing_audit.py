#!/usr/bin/env python3
"""Check uniform-frame captures under CPU load."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--suffix', default='')
args = parser.parse_args()
folder = root / 'test-results' / f'tearing-native-gpu{args.suffix}'
folder.mkdir(parents=True, exist_ok=False)
env = os.environ.copy()
env.update(QT_QPA_PLATFORM='wayland', OBS_BROWSER_GPU='nvidia', OBS_BROWSER_TEST_CAPTURE_INTERVAL_MS='50')
workers = [subprocess.Popen([sys.executable, '-c', 'import time; end=time.monotonic()+12\nwhile time.monotonic()<end: pass']) for _ in range(4)]
try:
    with (folder / 'host.log').open('w') as log:
        subprocess.run([str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
                        str(root / 'data'), str(root / 'tests/tearing-fixture.html'), str(folder), '1', '9'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=True)
finally:
    for worker in workers:
        worker.terminate()
        worker.wait()
decoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-pattern_type', 'glob', '-i', str(folder / 'frame-*.png'),
                            '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], stdout=subprocess.PIPE)
frame_bytes = 1280 * 720 * 4
frames, nonuniform, empty = 0, 0, 0
colors = set()
while True:
    data = bytearray()
    while len(data) < frame_bytes:
        part = decoder.stdout.read(frame_bytes - len(data))
        if not part:
            break
        data.extend(part)
    if not data:
        break
    if len(data) != frame_bytes:
        raise RuntimeError('Truncated decoded frame')
    samples = {bytes(data[(y * 1280 + x) * 4:(y * 1280 + x) * 4 + 4])
               for y in [20, 180, 360, 540, 700] for x in [20, 320, 640, 960, 1260]}
    if samples == {b'\0\0\0\0'}:
        empty += 1  # startup before the first page paint
        continue
    frames += 1
    nonuniform += len(samples) > 1
    colors.update(samples)
rc = decoder.wait()
text = (folder / 'host.log').read_text()
result = {'sampled_frames': frames, 'startup_blank_frames': empty, 'nonuniform_frames': nonuniform,
          'colors_seen': len(colors), 'cpu_stress_workers': 4, 'accelerated': 'accelerated DMA-BUF frame' in text,
          'fallback': 'CPU paint fallback' in text}
result['passed'] = rc == 0 and frames > 50 and nonuniform == 0 and len(colors) > 1 and result['accelerated'] and not result['fallback']
(folder / 'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['passed'] else 1)
