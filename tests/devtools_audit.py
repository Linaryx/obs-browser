#!/usr/bin/env python3
"""Request Inspect twice, verify one actual window, ongoing GPU paint/audio and clean teardown."""
import json
import os
from pathlib import Path
import re
import subprocess
from benchmark import inspect_frames

root = Path(__file__).resolve().parent.parent
folder = root / 'test-results/devtools-verified'
folder.mkdir(parents=True, exist_ok=False)
env = os.environ.copy()
env.update(QT_QPA_PLATFORM='wayland', OBS_BROWSER_GPU='nvidia', OBS_BROWSER_TEST_DEVTOOLS='1')
with (folder / 'host.log').open('w') as log:
    subprocess.run([str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
                    str(root / 'data'), str(root / 'tests/fixture.html'), str(folder), '1', '10'],
                   env=env, stdout=log, stderr=subprocess.STDOUT, timeout=35, check=True)
text = (folder / 'host.log').read_text()
gpu = [int(n) for n in re.findall(r'PAINT source=test-0 gpu=(\d+)', text)]
audio = [int(n) for n in re.findall(r'audio_frames=(\d+)', text)]
result = {'requested_twice': 'DEVTOOLS requested=1' in text,
          'windows_created': text.count('Source DevTools window created'),
          'windows_closed': text.count('Source DevTools window closed'),
          'gpu_frames_advanced': len(gpu) > 1 and gpu[-1] > gpu[0],
          'audio_frames_advanced': len(audio) > 1 and audio[-1] > audio[0],
          'fallback': 'CPU paint fallback' in text, 'pixels': inspect_frames(folder)}
result['passed'] = (result['requested_twice'] and result['windows_created'] == 1 and result['windows_closed'] == 1
                    and result['gpu_frames_advanced'] and result['audio_frames_advanced'] and not result['fallback']
                    and result['pixels']['passed'])
(folder / 'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['passed'] else 1)
