#!/usr/bin/env python3
"""Stream the current scene collection to a local RTMP receiver with isolated OBS config."""
import argparse
import configparser
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from benchmark import process_ticks
from ws_client import Client

ROOT = Path(__file__).resolve().parent.parent
CLOCK_TICKS = os.sysconf('SC_CLK_TCK')
SOURCE_SCENES = Path.home() / '.config/obs-studio/basic/scenes'
CAPTURE_IDS = {'pulse_input_capture', 'pipewire_audio_application_capture',
               'pipewire-window-capture-source', 'pipewire-screen-capture-source'}

parser = argparse.ArgumentParser()
parser.add_argument('--gpu-mode', choices=['nvidia', 'cpu'])
parser.add_argument('--stock', action='store_true', help='Use the obs-browser module from the installed obs-studio package')
parser.add_argument('--name', required=True)
parser.add_argument('--seconds', type=int, default=60)
parser.add_argument('--scene-file', default='linaryx-studio.json')
parser.add_argument('--scene-name', default='linaryx · Studio')
parser.add_argument('--runtime', type=Path)
parser.add_argument('--index', type=int, default=0, help='Port offset for parallel runs')
args = parser.parse_args()
if not 0 <= args.index <= 20:
    parser.error('--index must be between 0 and 20')
rtmp_port = 1935 + args.index
if '/' in args.name or args.seconds < 20:
    parser.error('use a plain name and at least 20 seconds')
if args.stock == bool(args.gpu_mode):
    parser.error('use exactly one of --stock or --gpu-mode')

folder = ROOT / 'test-results' / args.name
folder.mkdir(parents=True, exist_ok=False)
stock_root = folder / 'stock'
if args.stock:
    stock_root.mkdir()
    packages = sorted(Path('/var/cache/pacman/pkg').glob('obs-studio-33*.pkg.tar.zst'))
    if not packages:
        parser.error('obs-studio 33 package is not in the pacman cache')
    subprocess.run(['bsdtar', '-xf', str(packages[-1]), '-C', str(stock_root),
                    'usr/lib/obs-modules/core/obs-browser.so', 'usr/lib/obs-modules/core/obs-browser-page',
                    'usr/share/obs/obs-modules/core/obs-browser'], check=True)
    runtime = stock_root / 'usr/lib/obs-modules/core'
    data = stock_root / 'usr/share/obs/obs-modules/core/obs-browser'
else:
    runtime = args.runtime or ROOT / 'stage/usr/lib/obs-browser-nvidia'
    data = ROOT / 'data'
config = folder / 'xdg/obs-studio'
profile = config / 'basic/profiles/stream-audit'
scenes = config / 'basic/scenes'
(config / 'plugin_config/obs-websocket').mkdir(parents=True)
profile.mkdir(parents=True)
scenes.mkdir(parents=True)

collection = json.loads((SOURCE_SCENES / args.scene_file).read_text())
for source in collection['sources']:
    if source['id'] in CAPTURE_IDS:
        source['enabled'] = False
(scenes / args.scene_file).write_text(json.dumps(collection, ensure_ascii=False, indent=4))

width, height, fps = 1920, 1080, 60
(profile / 'basic.ini').write_text(
    '[General]\nName=Stream Audit\n\n'
    f'[Video]\nBaseCX={width}\nBaseCY={height}\nOutputCX={width}\nOutputCY={height}\nFPSType=0\nFPSCommon={fps}\n\n'
    '[Output]\nMode=Simple\n\n[SimpleOutput]\nVBitrate=6000\nStreamEncoder=obs_x264\nPreset=veryfast\n')
(profile / 'service.json').write_text(json.dumps({'type': 'rtmp_custom', 'settings': {
    'server': f'rtmp://127.0.0.1:{rtmp_port}/live', 'key': 'stream-audit', 'use_auth': False}}))
(config / 'user.ini').write_text(
    f'[General]\nFirstRun=true\n\n[Basic]\nProfile=Stream Audit\nProfileDir=stream-audit\n'
    f'SceneCollection={args.scene_name}\nSceneCollectionFile={args.scene_file}\n\n[BasicWindow]\nWarnBeforeStartingStream=false\n')
(config / 'global.ini').write_text('[General]\nLastVersion=553648128\nBrowserHWAccel=true\n')

password = secrets.token_urlsafe(24)
port = 4457 + args.index
with socket.socket() as sock:
    sock.bind(('127.0.0.1', port))
credentials = config / 'plugin_config/obs-websocket/config.json'
credentials.write_text(json.dumps({'server_enabled': True, 'server_port': port, 'auth_required': True,
                                   'server_password': password, 'first_load': False, 'alerts_enabled': False}))
credentials.chmod(0o600)

received = folder / 'received.flv'
receiver = subprocess.Popen(
    ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-listen', '1', '-i', f'rtmp://127.0.0.1:{rtmp_port}/live/stream-audit',
     '-c', 'copy', '-t', str(args.seconds + 25), '-y', str(received)],
    stdout=subprocess.DEVNULL, stderr=(folder / 'receiver.log').open('w'), start_new_session=True)
time.sleep(1)

env = os.environ.copy()
env.update(XDG_CONFIG_HOME=str(folder / 'xdg'), QT_QPA_PLATFORM='wayland', OBS_BROWSER_DIAGNOSTICS='1',
           OBS_BROWSER_RUNTIME_ROOT=str(runtime), OBS_BROWSER_DATA_ROOT=str(data))
if args.gpu_mode:
    env['OBS_BROWSER_GPU'] = args.gpu_mode
env.pop('OBS_BROWSER_PROXY', None)
client = None
result = {'mode': 'stock' if args.stock else f'fork-{args.gpu_mode}', 'scene': args.scene_name,
          'width': width, 'height': height, 'fps': fps}
with (folder / 'obs.log').open('w') as log:
    process = subprocess.Popen(['bash', str(ROOT / 'scripts/obs-nvidia-browser'), '--multi',
                                '--disable-shutdown-check', '--enable-logging=stderr'],
                               env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 45
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
        time.sleep(10)
        client.request('StartStream')
        started = False
        for _ in range(40):
            time.sleep(1)
            if client.request('GetStreamStatus')['outputActive']:
                started = True
                break
        if not started:
            raise RuntimeError('stream did not start')
        samples = []
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            samples.append((time.monotonic(), sum(process_ticks(process.pid).values())))
            time.sleep(5)
        steady = [s for s in samples if s[0] - start >= 15] or samples
        tree_cpu = (steady[-1][1] - steady[0][1]) / CLOCK_TICKS / (steady[-1][0] - steady[0][0]) * 100
        result['tree_cpu_percent_steady'] = round(tree_cpu, 1)
        result['during'] = {'stream': client.request('GetStreamStatus'), 'stats': client.request('GetStats')}
        client.request('StopStream')
        for _ in range(30):
            time.sleep(1)
            if not client.request('GetStreamStatus')['outputActive']:
                break
        result['after'] = client.request('GetStreamStatus')
    finally:
        if client:
            client.close()
        for pid in subprocess.run(['pgrep', '-g', str(process.pid), '-x', 'obs'], capture_output=True, text=True).stdout.split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        try:
            receiver.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(receiver.pid, signal.SIGTERM)
            receiver.wait(timeout=10)

probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,bit_rate',
                        '-count_packets', '-of', 'json', str(received)], capture_output=True, text=True)
result['received'] = json.loads(probe.stdout) if probe.returncode == 0 and received.exists() else {'error': probe.stderr}
text = (folder / 'obs.log').read_text()
result['accelerated_dmabuf'] = 'accelerated DMA-BUF frame' in text
result['cpu_fallback'] = 'CPU paint fallback' in text
result['nvidia_blocklist_message'] = 'Blacklisted driver detected' in text
(folder / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
print(json.dumps(result, indent=2, ensure_ascii=False))
