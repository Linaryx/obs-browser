#!/usr/bin/env python3
"""Benchmark browser rendering on an NVIDIA desktop."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time


def process_ticks(root):
    processes = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = path.read_text()
            fields = text[text.rfind(')') + 2:].split()
            processes[int(path.parent.name)] = (int(fields[1]), int(fields[11]) + int(fields[12]))
        except (OSError, ValueError, IndexError):
            continue
    descendants = {root}
    for _ in range(8):
        descendants.update(pid for pid, (ppid, _) in processes.items() if ppid in descendants)
    return {pid: ticks for pid, (_, ticks) in processes.items() if pid in descendants}


def inspect_frames(folder):
    frames = sorted(folder.glob('frame-*.png'), key=lambda p: int(p.stem.split('-')[1]))
    if not frames:
        return {'passed': False, 'reason': 'no screenshots'}
    images = [subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(p), '-f', 'rawvideo', '-pix_fmt', 'rgba', '-']) for p in frames[-3:]]
    data = images[-1]
    def pixel(x, y):
        pos = (y * 1280 + x) * 4
        return list(data[pos:pos + 4])
    red, green, blue, clear = pixel(50, 50), pixel(1230, 50), pixel(50, 670), pixel(1230, 670)
    colors = red[0] > 240 and red[1] < 10 and red[3] > 240 and blue[2] > 240 and blue[0] < 10
    alpha = 120 <= green[3] <= 136 and green[1] > 100 and clear[3] == 0
    animation = len({hashlib.sha256(d).hexdigest() for d in images}) > 1
    return {'passed': colors and alpha and animation, 'colors': colors, 'alpha': alpha, 'animation': animation,
            'samples': {'red': red, 'half_green': green, 'webgl_blue': blue, 'transparent': clear}}


def run(root, case, seconds):
    name, platform, mode, count, failure, extra = case
    folder = root / 'test-results' / name
    folder.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM=platform, OBS_BROWSER_GPU=mode, OBS_BROWSER_DIAGNOSTICS='1')
    env.pop('OBS_BROWSER_PROXY', None)
    if failure:
        env['OBS_BROWSER_TEST_GPU_FAILURE'] = failure
    else:
        env.pop('OBS_BROWSER_TEST_GPU_FAILURE', None)
    command = [str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
               str(root / 'data'), str(root / 'tests/fixture.html'), str(folder), str(count), str(seconds),
               '--enable-logging=stderr', *extra]
    samples = []
    with (folder / 'host.log').open('w') as log:
        p = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        old = process_ticks(p.pid)
        last = time.monotonic()
        deadline = last + seconds + 25
        while p.poll() is None:
            if time.monotonic() > deadline:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                break
            time.sleep(1)
            ticks = process_ticks(p.pid)
            now = time.monotonic()
            cpu = 100 * sum(max(0, value - old.get(pid, value)) for pid, value in ticks.items()) / os.sysconf('SC_CLK_TCK') / (now - last)
            old, last = ticks, now
            gpu = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True)
            samples.append({'cpu_tree_percent': cpu, 'gpu_global_util_and_memory': gpu.stdout.strip()})
        rc = p.wait()
    text = (folder / 'host.log').read_text()
    metrics = [{k: float(v) for k, v in re.findall(r'(\w+)=([\d.]+)', line)} for line in text.splitlines() if line.startswith('METRICS ')]
    paints = [dict(re.findall(r'(\w+)=(\S+)', line)) for line in text.splitlines() if line.startswith('PAINT ')]
    result = {'case': name, 'exit_code': rc, 'pixels': inspect_frames(folder), 'metrics': metrics, 'paints': paints,
              'mean_tree_cpu_percent': statistics.mean(s['cpu_tree_percent'] for s in samples) if samples else None,
              'resource_samples': samples,
              'accelerated': 'accelerated DMA-BUF frame' in text, 'fallback': 'CPU paint fallback' in text}
    result['passed'] = rc == 0 and result['pixels']['passed'] and bool(metrics) and metrics[-1]['audio_frames'] > 0
    if mode == 'nvidia' and not failure:
        result['passed'] &= result['accelerated'] and not result['fallback']
    if failure:
        result['passed'] &= result['fallback'] and any(int(p.get('cpu', '0')) > 0 for p in paints)
    (folder / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ('resource_samples', 'metrics', 'paints')}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=22)
    parser.add_argument('--case')
    parser.add_argument('--suffix', default='')
    parser.add_argument('--native-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    cases = [
        ('wayland-gpu-1-final', 'wayland', 'nvidia', 1, None, []),
        ('wayland-cpu-1-final', 'wayland', 'cpu', 1, None, []),
        ('wayland-gpu-4-final', 'wayland', 'nvidia', 4, None, []),
        ('wayland-fallback-import', 'wayland', 'nvidia', 1, 'import', []),
        ('wayland-fallback-timeout', 'wayland', 'nvidia', 1, 'timeout', []),
        ('x11-gpu-diagnostic', 'xcb', 'nvidia', 1, None, []),
        ('x11-gpu-angle-gl', 'xcb', 'nvidia', 1, None, ['--use-gl=angle', '--use-angle=gl']),
        ('x11-gpu-angle-gl-egl', 'xcb', 'nvidia', 1, None, ['--use-gl=angle', '--use-angle=gl-egl']),
    ]
    selected = [c for c in cases if not args.case or c[0] == args.case]
    if args.native_only:
        selected = [c for c in selected if c[1] == 'wayland']
    if not selected:
        parser.error('unknown case')
    results = [run(root, (case[0] + args.suffix, *case[1:]), args.seconds) for case in selected]
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)
