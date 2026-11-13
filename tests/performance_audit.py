#!/usr/bin/env python3
"""Compare CPU paint, GPU copy and the previous GPU path sequentially."""
import argparse
import json
from pathlib import Path
from benchmark import run

parser = argparse.ArgumentParser()
parser.add_argument('--tag', required=True)
parser.add_argument('--seconds', type=int, default=35)
parser.add_argument('--stress-seconds', type=int, default=90)
args = parser.parse_args()
if args.seconds < 15 or args.stress_seconds < 15 or '/' in args.tag:
    parser.error('use a plain tag and durations of at least 15 seconds')
root = Path(__file__).resolve().parent.parent
results = []
for count in [1, 4]:
    for variant, mode, legacy in [('cpu', 'cpu', False), ('gpu-legacy', 'nvidia', True), ('gpu', 'nvidia', False)]:
        name = f'{args.tag}-heavy-{variant}-{count}'
        results.append(run(root, (name, 'wayland', mode, count, None, []), args.seconds,
                           1920, 1080, 'heavy-fixture.html', 5, legacy))
results.append(run(root, (f'{args.tag}-stress-gpu-4', 'wayland', 'nvidia', 4, None, []),
                   args.stress_seconds, 1920, 1080, 'fixture.html', 10, False))
summary = [{key: value for key, value in result.items() if key in
            ['case', 'passed', 'steady_tree_cpu_percent', 'source_stats', 'accelerated', 'fallback']}
           for result in results]
(root / 'test-results' / f'{args.tag}-performance.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
raise SystemExit(0 if all(result['passed'] for result in results) else 1)
