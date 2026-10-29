#!/usr/bin/env python3
"""Cache upstream PR metadata, histories, reviews and diffs (49 API requests)."""
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--refresh', action='store_true', help='Refresh public data instead of reusing the cache (49 API calls)')
args = parser.parse_args()
CACHE = ROOT / 'audit-cache'
PRS = {
    'chromiumembedded/cef': [4238, 3954, 4233],
    'obsproject/obs-browser': [531, 533, 546, 508, 155, 554, 556, 558, 528, 530, 440],
    'obsproject/obs-studio': [13797],
}


def fetch(url, destination):
    if destination.exists() and not args.refresh:
        return
    request = urllib.request.Request(url, headers={'User-Agent': 'obs-browser-nvidia-upstream-audit'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            destination.write_bytes(response.read())
        error_path = destination.with_suffix(destination.suffix + '.error')
        if error_path.exists():
            error_path.unlink()
    except Exception as error:
        destination.with_suffix(destination.suffix + '.error').write_text(f'{url}\n{error}\n')
        print(f'FAILED {url}: {error}', flush=True)


jobs = []
for repo, numbers in PRS.items():
    for number in numbers:
        folder = CACHE / repo.replace('/', '-') / str(number)
        folder.mkdir(parents=True, exist_ok=True)
        api = f'https://api.github.com/repos/{repo}/pulls/{number}'
        for suffix, name in [('', 'pull.json'), ('/commits?per_page=100', 'commits.json'),
                             ('/reviews?per_page=100', 'reviews.json')]:
            jobs.append((api + suffix, folder / name))
        if number in [531, 533, 3954, 4233]:
            jobs.append((api + '/comments?per_page=100', folder / 'review-comments.json'))
        jobs.append((f'https://github.com/{repo}/pull/{number}', folder / 'discussion.html'))
        jobs.append((f'https://patch-diff.githubusercontent.com/raw/{repo}/pull/{number}.diff', folder / 'changes.diff'))
with ThreadPoolExecutor(max_workers=4) as executor:
    list(executor.map(lambda job: fetch(*job), jobs))
summary = {'generated_at': datetime.now(timezone.utc).isoformat(), 'cache_mode': 'refresh' if args.refresh else 'reuse', 'pulls': []}
for repo, numbers in PRS.items():
    for number in numbers:
        folder = CACHE / repo.replace('/', '-') / str(number)
        if not (folder / 'pull.json').exists():
            summary['pulls'].append({'repo': repo, 'number': number, 'error': 'metadata unavailable'})
            continue
        pr = json.loads((folder / 'pull.json').read_text())
        commits = json.loads((folder / 'commits.json').read_text()) if (folder / 'commits.json').exists() else []
        reviews = json.loads((folder / 'reviews.json').read_text()) if (folder / 'reviews.json').exists() else []
        item = {k: pr.get(k) for k in ['number', 'title', 'html_url', 'state', 'merged', 'merged_at',
                                      'merge_commit_sha', 'updated_at', 'changed_files']}
        item.update(repo=repo, head_sha=pr['head']['sha'], base_sha=pr['base']['sha'],
                    fetched_at=datetime.fromtimestamp((folder / 'pull.json').stat().st_mtime, timezone.utc).isoformat(),
                    commits=[{'sha': c['sha'], 'subject': c['commit']['message']} for c in commits],
                    reviews=[{'state': r['state'], 'body': r['body'], 'user': r['user']['login']} for r in reviews],
                    missing=[p.name for p in folder.glob('*.error')])
        summary['pulls'].append(item)
(ROOT / 'docs/upstream-snapshot.json').write_text(json.dumps(summary, indent=2) + '\n')
for pr in summary['pulls']:
    print(pr['repo'], pr['number'], pr.get('state'), 'merged=', pr.get('merged'), pr.get('title'), flush=True)
