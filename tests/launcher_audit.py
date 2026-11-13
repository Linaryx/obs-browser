#!/usr/bin/env python3
"""Check launcher defaults without starting OBS."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='obs-launcher-') as work:
    folder = Path(work)
    (folder / 'bin').mkdir()
    (folder / 'runtime').mkdir()
    (folder / 'data').mkdir()
    (folder / 'core').mkdir()
    (folder / 'core/obs-browser.so').touch()
    (folder / 'runtime/obs-browser.so').touch()
    stub = folder / 'bin/bwrap'
    stub.write_text('#!/usr/bin/env bash\nprintf "%s %s %s\\n" "$QT_QPA_PLATFORM" "$OBS_BROWSER_GPU" "$QT_NO_GLIB"\n')
    stub.chmod(0o755)
    for display, qt, gpu, workaround, expected in [
        ('wayland-audit', None, None, None, 'wayland nvidia'),
        (None, None, None, None, 'xcb cpu'),
        ('wayland-audit', 'xcb', 'nvidia', None, 'xcb nvidia'),
        ('wayland-audit', 'wayland', 'cpu', None, 'wayland cpu'),
        ('wayland-audit', None, None, '1', 'wayland nvidia 1'),
    ]:
        env = os.environ.copy()
        for name, value in [('WAYLAND_DISPLAY', display), ('QT_QPA_PLATFORM', qt), ('OBS_BROWSER_GPU', gpu), ('QT_NO_GLIB', None)]:
            env.pop(name, None)
            if value is not None:
                env[name] = value
        env.pop('OBS_BROWSER_QT_NO_GLIB', None)
        if workaround is not None:
            env['OBS_BROWSER_QT_NO_GLIB'] = workaround
        env.update(PATH=str(folder / 'bin') + ':' + env['PATH'], OBS_BROWSER_RUNTIME_ROOT=str(folder / 'runtime'),
                   OBS_BROWSER_DATA_ROOT=str(folder / 'data'), OBS_BROWSER_CORE_ROOT=str(folder / 'core'),
                   OBS_BROWSER_COREDATA_ROOT=str(folder / 'coredata'))
        result = subprocess.check_output(['bash', str(root / 'scripts/obs-nvidia-browser')], env=env, text=True).strip()
        assert result == expected, (result, expected)
    env['OBS_BROWSER_CORE_ROOT'] = str(folder / 'missing-core')
    result = subprocess.run(['bash', str(root / 'scripts/obs-nvidia-browser')], env=env,
                            capture_output=True, text=True)
    assert result.returncode != 0 and 'Arch OBS 33 core module layout' in result.stderr
print('launcher defaults: passed')
