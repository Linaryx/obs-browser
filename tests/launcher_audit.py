#!/usr/bin/env python3
"""Check launcher defaults without starting OBS."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
temporary_root = '/tmp/opencode' if Path('/tmp/opencode').is_dir() else None
with tempfile.TemporaryDirectory(prefix='obs-launcher-', dir=temporary_root) as work:
    folder = Path(work)
    (folder / 'bin').mkdir()
    (folder / 'runtime').mkdir()
    (folder / 'data').mkdir()
    (folder / 'runtime/obs-browser.so').touch()
    stub = folder / 'bin/bwrap'
    stub.write_text('#!/usr/bin/env bash\nprintf "%s %s %s\\n" "$QT_QPA_PLATFORM" "$OBS_BROWSER_GPU" "$QT_NO_GLIB"\n')
    stub.chmod(0o755)
    for display, qt, gpu, expected in [
        ('wayland-audit', None, None, 'wayland nvidia 1'),
        (None, None, None, 'xcb cpu 1'),
        ('wayland-audit', 'xcb', 'nvidia', 'xcb nvidia 1'),
        ('wayland-audit', 'wayland', 'cpu', 'wayland cpu 1'),
    ]:
        env = os.environ.copy()
        for name, value in [('WAYLAND_DISPLAY', display), ('QT_QPA_PLATFORM', qt), ('OBS_BROWSER_GPU', gpu), ('QT_NO_GLIB', None)]:
            env.pop(name, None)
            if value is not None:
                env[name] = value
        env.update(PATH=str(folder / 'bin') + ':' + env['PATH'], OBS_BROWSER_RUNTIME_ROOT=str(folder / 'runtime'),
                   OBS_BROWSER_DATA_ROOT=str(folder / 'data'))
        result = subprocess.check_output(['bash', str(root / 'scripts/obs-nvidia-browser')], env=env, text=True).strip()
        assert result == expected, (result, expected)
print('launcher defaults: passed')
