#!/usr/bin/env python3
"""Verify OBS log levels remain visible by default and quiet mode emits a summary."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
for quiet in [False, True]:
    folder = root / 'test-results' / ('console-quiet' if quiet else 'console-normal')
    folder.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='wayland', OBS_BROWSER_GPU='cpu', OBS_BROWSER_QUIET_CONSOLE='1' if quiet else '0')
    with (folder / 'host.log').open('w') as log:
        subprocess.run([str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
                        str(root / 'data'), str(root / 'tests/console-fixture.html'), str(folder), '1', '5'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=True)
    text = (folder / 'host.log').read_text()
    expected = 'debug:' if quiet else 'warning:'
    assert any(line.startswith(expected) and 'OBS_CONSOLE_AUDIT_ERROR' in line for line in text.splitlines()), text[-2000:]
    if quiet:
        assert 'Console summary: warnings=1 errors=1 fatal=0' in text
    print('quiet=' + str(quiet), 'passed')
