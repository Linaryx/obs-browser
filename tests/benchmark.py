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


def inspect_frames(folder, width=1280, height=720):
    try:
        frames = sorted(folder.glob('frame-*.png'), key=lambda p: int(p.stem.split('-', 1)[1]))
    except (IndexError, ValueError):
        return {'passed': False, 'reason': 'malformed frame name'}
    if not frames:
        return {'passed': False, 'reason': 'no screenshots'}
    try:
        images = [subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(p), '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], timeout=30) for p in frames[-3:]]
    except FileNotFoundError:
        return {'passed': False, 'reason': 'missing ffmpeg'}
    except subprocess.TimeoutExpired:
        return {'passed': False, 'reason': 'ffmpeg timeout'}
    except (OSError, subprocess.SubprocessError):
        return {'passed': False, 'reason': 'ffmpeg failed'}
    if any(len(image) != width * height * 4 for image in images):
        return {'passed': False, 'reason': 'wrong frame size'}
    def pixel(data, x, y):
        pos = (y * width + x) * 4
        return list(data[pos:pos + 4])
    def sample(data):
        return {'red': pixel(data, 50, 50), 'half_green': pixel(data, width - 50, 50),
                'webgl_blue': pixel(data, 50, height - 50), 'transparent': pixel(data, width - 50, height - 50)}
    samples = [sample(image) for image in images]
    def colors_ok(s):
        red, blue = s['red'], s['webgl_blue']
        return (red[0] > 240 and red[1] < 10 and red[2] < 10 and red[3] > 240 and
                blue[0] < 10 and blue[1] < 10 and blue[2] > 240 and blue[3] > 240)
    def alpha_ok(s):
        green, clear = s['half_green'], s['transparent']
        return (green[0] < 10 and 100 < green[1] < 140 and green[2] < 10 and
                120 <= green[3] <= 136 and clear[3] == 0)
    colors = all(colors_ok(s) for s in samples)
    alpha = all(alpha_ok(s) for s in samples)
    animation = len({hashlib.sha256(d).hexdigest() for d in images}) > 1
    return {'passed': colors and alpha and animation, 'colors': colors, 'alpha': alpha, 'animation': animation,
            'samples': samples[-1]}


def run(root, case, seconds, width=1280, height=720, fixture='fixture.html', warmup=5, legacy=False):
    name, platform, mode, count, failure, extra = case
    folder = root / 'test-results' / name
    folder.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM=platform, OBS_BROWSER_GPU=mode, OBS_BROWSER_DIAGNOSTICS='1')
    env.update(OBS_BROWSER_TEST_WIDTH=str(width), OBS_BROWSER_TEST_HEIGHT=str(height))
    if legacy:
        env['OBS_BROWSER_TEST_LEGACY_COPY'] = '1'
    else:
        env.pop('OBS_BROWSER_TEST_LEGACY_COPY', None)
    env.pop('OBS_BROWSER_PROXY', None)
    if failure:
        env['OBS_BROWSER_TEST_GPU_FAILURE'] = failure
    else:
        env.pop('OBS_BROWSER_TEST_GPU_FAILURE', None)
    command = [str(root / 'build/browser-test-host'), str(root / 'stage/usr/lib/obs-browser-nvidia/obs-browser.so'),
               str(root / 'data'), str(root / 'tests' / fixture), str(folder), str(count), str(seconds),
               '--enable-logging=stderr', *extra]
    samples = []
    with (folder / 'host.log').open('w') as log:
        p = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        old = process_ticks(p.pid)
        last = time.monotonic()
        started = last
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
            samples.append({'elapsed_s': now - started, 'cpu_tree_percent': cpu, 'gpu_global_util_and_memory': gpu.stdout.strip()})
        rc = p.wait()
    text = (folder / 'host.log').read_text()
    metrics = [{k: float(v) for k, v in re.findall(r'(\w+)=([\d.]+)', line)} for line in text.splitlines() if line.startswith('METRICS ')]
    paints = [dict(re.findall(r'(\w+)=(\S+)', line)) for line in text.splitlines() if line.startswith('PAINT ')]
    steady = [sample for sample in samples if warmup <= sample['elapsed_s'] <= seconds - 1]
    source_stats = []
    for source in sorted({paint['source'] for paint in paints}):
        records = [paint for paint in paints if paint['source'] == source and float(paint.get('elapsed_s', 0)) >= warmup]
        if len(records) < 2:
            continue
        first, last = records[0], records[-1]
        elapsed = float(last['elapsed_s']) - float(first['elapsed_s'])
        frames = int(last['gpu']) - int(first['gpu'])
        stats = {'source': source, 'paint_fps': (frames + int(last['cpu']) - int(first['cpu'])) / elapsed,
                 'render_fps': (int(last['renders']) - int(first['renders'])) / elapsed,
                 'extra_copy_fps': (int(last['extra']) - int(first['extra'])) / elapsed}
        for field in ['copy_ns', 'import_ns', 'wait_ns']:
            stats[field.replace('_ns', '_ms_per_gpu_frame')] = ((int(last[field]) - int(first[field])) / frames / 1e6) if frames else None
        source_stats.append(stats)
    result = {'case': name, 'exit_code': rc, 'width': width, 'height': height, 'fixture': fixture,
              'legacy_copy': legacy, 'pixels': inspect_frames(folder, width, height), 'metrics': metrics, 'paints': paints,
              'mean_tree_cpu_percent': statistics.mean(s['cpu_tree_percent'] for s in samples) if samples else None,
              'steady_tree_cpu_percent': statistics.mean(s['cpu_tree_percent'] for s in steady) if steady else None,
              'source_stats': source_stats,
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
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fixture', choices=['fixture.html', 'heavy-fixture.html'], default='fixture.html')
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--legacy-copy', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    cases = [
        ('wayland-gpu-1-final', 'wayland', 'nvidia', 1, None, []),
        ('wayland-cpu-1-final', 'wayland', 'cpu', 1, None, []),
        ('wayland-gpu-4-final', 'wayland', 'nvidia', 4, None, []),
        ('wayland-cpu-4', 'wayland', 'cpu', 4, None, []),
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
    if args.width < 256 or args.height < 256 or args.seconds <= args.warmup + 5:
        parser.error('resolution must be at least 256x256 and duration must exceed warmup by five seconds')
    results = [run(root, (case[0] + args.suffix, *case[1:]), args.seconds, args.width, args.height,
                   args.fixture, args.warmup, args.legacy_copy) for case in selected]
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)
