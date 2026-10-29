#!/usr/bin/env python3
"""OBS frontend smoke test with a separate config."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import re
import signal
import socket
import subprocess
import time
from benchmark import inspect_frames
from ws_client import Client

parser = argparse.ArgumentParser()
parser.add_argument('--platform', choices=['wayland', 'xcb'], default='wayland')
parser.add_argument('--name', default='frontend-wayland')
parser.add_argument('--dock', action='store_true', help='Add a synthetic custom dock (XWayland only)')
parser.add_argument('--gpu-mode', choices=['nvidia', 'cpu'], default='nvidia')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
folder = root / 'test-results' / args.name
folder.mkdir(parents=True, exist_ok=False)
config = folder / 'xdg/obs-studio'
(config / 'plugin_config/obs-websocket').mkdir(parents=True)
if args.dock and args.platform != 'xcb':
    parser.error('Native Wayland docks are unsupported by the pinned CEF SDK')
dock_config = ''
if args.dock:
    docks = [{'title': 'Audit Dock', 'url': (root / 'tests/dock-fixture.html').as_uri(), 'uuid': '4ade570ef0f84d2a877746dcd48a4e11'}]
    dock_config = 'ExtraBrowserDocks=' + json.dumps(docks) + '\n'
(config / 'user.ini').write_text('[General]\nFirstRun=true\n\n[BasicWindow]\nWarnBeforeStartingStream=true\n' + dock_config)
(config / 'global.ini').write_text('[General]\nLastVersion=553648128\nBrowserHWAccel=true\n')
password = secrets.token_urlsafe(24)
port = 4456
with socket.socket() as sock:
    sock.bind(('127.0.0.1', port))
credentials = config / 'plugin_config/obs-websocket/config.json'
credentials.write_text(json.dumps({'server_enabled': True, 'server_port': port, 'auth_required': True,
                                   'server_password': password, 'first_load': False, 'alerts_enabled': False}))
credentials.chmod(0o600)
env = os.environ.copy()
env.update(XDG_CONFIG_HOME=str(folder / 'xdg'), QT_QPA_PLATFORM=args.platform, OBS_BROWSER_GPU=args.gpu_mode,
           OBS_BROWSER_DIAGNOSTICS='1', OBS_BROWSER_RUNTIME_ROOT=str(root / 'stage/usr/lib/obs-browser-nvidia'),
           OBS_BROWSER_DATA_ROOT=str(root / 'data'))
env.pop('OBS_BROWSER_PROXY', None)
client = None
with (folder / 'obs.log').open('w') as log:
    process = subprocess.Popen(['bash', str(root / 'scripts/obs-nvidia-browser'), '--multi', '--disable-shutdown-check', '--enable-logging=stderr'],
                               env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('OBS launcher exited; inspect obs.log')
            try:
                client = Client(port, password)
                break
            except (OSError, ConnectionError):
                time.sleep(1)
        if client is None:
            raise RuntimeError('Websocket startup timeout')
        scene = client.request('GetCurrentProgramScene')['currentProgramSceneName']
        client.request('CreateInput', sceneName=scene, inputName='frontend-fixture', inputKind='browser_source',
                       inputSettings={'is_local_file': True, 'local_file': str(root / 'tests/frontend.html'),
                                      'width': 1280, 'height': 720, 'fps_custom': True, 'fps': 60, 'reroute_audio': True},
                       sceneItemEnabled=True)
        if args.platform == 'xcb' and args.gpu_mode == 'nvidia':
            time.sleep(18)  # unsupported GPU path may need its 15-second CPU fallback
        for i in range(3):
            time.sleep(3 if args.platform == 'xcb' else 7)
            shot = client.request('GetSourceScreenshot', sourceName='frontend-fixture', imageFormat='png', imageWidth=1280, imageHeight=720)
            (folder / f'frame-{i}.png').write_bytes(base64.b64decode(shot['imageData'].split(',', 1)[1]))
        result = {'stream': client.request('GetStreamStatus'), 'record': client.request('GetRecordStatus'),
                  'stats': client.request('GetStats'), 'pixels': inspect_frames(folder)}
        assert not result['stream']['outputActive'] and not result['record']['outputActive']
        (folder / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        if client:
            client.close()
        # Close only the test process group.
        children = subprocess.run(['pgrep', '-g', str(process.pid), '-x', 'obs'], capture_output=True, text=True)
        for pid in children.stdout.split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
text = (folder / 'obs.log').read_text()
print('GPU frame:', 'accelerated DMA-BUF frame' in text, 'OBS JS callback:', 'OBS_JS_STATUS' in text)
assert result['pixels']['passed']
assert 'OBS_JS_STATUS' in text
if args.platform == 'wayland' and args.gpu_mode == 'nvidia':
    assert 'accelerated DMA-BUF frame' in text and 'CPU paint fallback' not in text
if args.dock:
    sizes = [(int(w), int(h)) for w, h in re.findall(r'OBS_DOCK_AUDIT:(\d+)x(\d+)', text)]
    # Tiled docks can shrink to ~80px wide; reject the initial 100x30 viewport.
    assert sizes and any(w >= 64 and h > 100 for w, h in sizes), sizes
    print('Custom dock viewport sizes:', sizes)
