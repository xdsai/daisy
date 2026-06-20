#!/usr/bin/env python3
"""
One-off tool: re-download the existing movie library in 4K (2160p).

For each movie currently in the library, search for a 4K release and let the
LLM pick the best one. A 4K download is triggered via the Daisy API only when
a genuine 2160p release with enough seeders exists — otherwise the movie is
left alone (we already have the 1080p copy).

A manifest (watchlist-style JSON) records what was triggered so the cleanup
step can delete the superseded 1080p file once its 4K replacement lands on disk.

Usage:
    python scripts/redownload_4k.py search            # find + trigger 4K downloads
    python scripts/redownload_4k.py status            # show manifest progress
    python scripts/redownload_4k.py cleanup           # DRY RUN: show 1080p files to delete
    python scripts/redownload_4k.py cleanup --confirm # actually delete superseded 1080p
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import requests
from daisy.config import Config

_REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
MANIFEST_FILE = os.path.join(_REPO_ROOT, 'redownload_4k_manifest.json')

API_PORT = os.getenv('DAISY_PORT', '5000')
API_KEY = os.getenv('DAISY_API_KEY', '')
API_BASE = f'http://127.0.0.1:{API_PORT}'

LLM_BASE = os.getenv('LLM_BASE', 'http://127.0.0.1:3456')
LLM_MODEL = os.getenv('LLM_MODEL', 'claude-sonnet-4-6')

VIDEO_EXTS = ('.mkv', '.mp4', '.avi')
SUB_EXTS = ('.srt', '.ass', '.ssa', '.sub', '.vtt')
FO1080 = ('1080p', '1080i')
FO4K = ('2160p', '4k', 'uhd')


# ---- manifest persistence ----

def load_manifest() -> dict:
    try:
        with open(MANIFEST_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_manifest(m: dict):
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(m, f, indent=2)


# ---- filename parsing (via LLM, robust to messy release names) ----

def extract_title_year(filename: str) -> tuple[str, int | None]:
    """Ask the LLM to pull a clean {title, year} out of a release filename."""
    prompt = (
        "Extract the movie title and release year from this torrent/release "
        f"filename:\n\n{filename}\n\n"
        'Respond with ONLY compact JSON: {"title": "...", "year": 1234}. '
        'If you cannot find a year, use null for year. No other text.'
    )
    try:
        resp = requests.post(
            f"{LLM_BASE}/v1/chat/completions",
            json={
                'model': LLM_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 60,
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()['choices'][0]['message']['content'].strip()
        # strip code fences if present
        answer = re.sub(r'^```(?:json)?|```$', '', answer, flags=re.MULTILINE).strip()
        data = json.loads(answer)
        year = data.get('year')
        return data['title'].strip(), (int(year) if year else None)
    except Exception as e:
        print(f"  ! title extraction failed for {filename!r}: {e}")
        # crude fallback: strip extension, take text before a 4-digit year
        base = os.path.splitext(filename)[0]
        m = re.search(r'(.+?)[.\s(]+(19|20)\d{2}', base)
        if m:
            return m.group(1).replace('.', ' ').strip(), int(base[m.end(1):m.end()][-4:])
        return base.replace('.', ' ').strip(), None


# ---- search + 4K-strict LLM pick ----

def search_movie(name: str, year: int | None) -> list[dict]:
    query = f"{name} {year}" if year else name
    try:
        resp = requests.get(
            f"{API_BASE}/search",
            params={'q': query, 'type': 'movie', 'limit': '30'},
            headers={'X-API-Key': API_KEY},
            timeout=90,
        )
        if resp.status_code == 200:
            return resp.json().get('results', [])
        print(f"  ! search API {resp.status_code}: {resp.text[:120]}")
        return []
    except Exception as e:
        print(f"  ! search error: {e}")
        return []


def pick_4k(name: str, year: int | None, results: list[dict]) -> int | None:
    """LLM picks the best 4K release, or SKIP if there's no usable 4K."""
    if not results:
        return None
    options = '\n'.join(
        f"[{i}] {r['title']}  |  size: {r.get('size','?')}  |  "
        f"seeders: {r.get('seeders',0)}  |  source: {r.get('source','?')}  |  "
        f"quality: {r.get('quality','?')}"
        for i, r in enumerate(results)
    )
    year_str = f" ({year})" if year else ""
    prompt = f"""I already own this movie in 1080p and want to UPGRADE it to 4K: "{name}"{year_str}.

Search results:

{options}

Pick the single best 4K (2160p / UHD) release. Rules:
1. MUST be 4K / 2160p / UHD. If there is NO real 4K release here, respond "SKIP" (I keep my 1080p copy).
2. MUST have at least 5 seeders.
3. For non-English films / anime: prefer nyaa.si or sources with original-language audio + subs, NEVER English dubs (YTS strips original audio).
4. Prefer UHD BluRay or WEB-DL; prefer HEVC/x265 encodes 8-30 GB. Avoid full REMUX over ~50 GB unless it's the only 4K option.
5. Make sure it's the SAME movie (matching title and year), not a sequel/remake/different film.
6. Between similar 4K options, pick the most seeders.

Respond with ONLY the index number, or "SKIP". Nothing else."""
    try:
        resp = requests.post(
            f"{LLM_BASE}/v1/chat/completions",
            json={'model': LLM_MODEL,
                  'messages': [{'role': 'user', 'content': prompt}],
                  'max_tokens': 10},
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()['choices'][0]['message']['content'].strip()
        if answer.upper().startswith('SKIP'):
            return None
        idx = int(re.search(r'\d+', answer).group())
        return idx if 0 <= idx < len(results) else None
    except Exception as e:
        print(f"  ! LLM pick failed: {e}")
        return None


def trigger_download(name: str, magnet: str) -> bool:
    try:
        resp = requests.post(
            f"{API_BASE}/download",
            json={'name': name, 'type': 'movie', 'magnet': magnet},
            headers={'X-API-Key': API_KEY},
            timeout=30,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"  ! download trigger failed: {e}")
        return False


# ---- disk helpers ----

def movies_dir() -> str:
    return Config.load().storage.movies_dir


def list_video_files(directory: str) -> list[str]:
    return sorted(
        f for f in os.listdir(directory)
        if f.endswith(VIDEO_EXTS) and not f.lower().startswith('sample')
        and os.path.getsize(os.path.join(directory, f)) > 100 * 1024 * 1024
    )


def title_tokens(title: str) -> list[str]:
    """Significant lowercase word tokens from a title (len > 2)."""
    return [t for t in re.findall(r'[a-z0-9]+', title.lower()) if len(t) > 2]


def find_4k_on_disk(directory: str, title: str, year: int | None, exclude: str) -> str | None:
    """
    Find a 4K file on disk for this movie (excluding the old 1080p file).
    Requires 2160p/4k/uhd in the name, year match (if known), and most title
    tokens present. Returns the filename only if exactly one candidate matches.
    """
    toks = title_tokens(title)
    needed = max(1, int(len(toks) * 0.6))
    candidates = []
    for f in os.listdir(directory):
        if f == exclude or not f.endswith(VIDEO_EXTS):
            continue
        low = f.lower()
        if not any(q in low for q in FO4K):
            continue
        if year and str(year) not in f:
            continue
        hits = sum(1 for t in toks if t in low)
        if hits >= needed:
            candidates.append(f)
    return candidates[0] if len(candidates) == 1 else None


# ---- commands ----

def cmd_search():
    directory = movies_dir()
    files = list_video_files(directory)
    print(f"Found {len(files)} movie files in {directory}\n")

    manifest = load_manifest()
    triggered = skipped = already = 0

    for i, fname in enumerate(files, 1):
        # already processed?
        existing = next((k for k, v in manifest.items() if v.get('old_file') == fname), None)
        if existing and manifest[existing].get('status') in ('triggered', 'done'):
            already += 1
            continue

        print(f"[{i}/{len(files)}] {fname}")
        title, year = extract_title_year(fname)
        print(f"      → {title} ({year})")

        results = search_movie(title, year)
        if not results:
            print("      no search results\n")
            manifest[f"{title}-{year}"] = {'old_file': fname, 'title': title,
                                           'year': year, 'status': 'no_results'}
            save_manifest(manifest)
            skipped += 1
            continue

        pick = pick_4k(title, year, results)
        key = f"{title}-{year}"
        if pick is None:
            print("      no usable 4K — keeping 1080p\n")
            manifest[key] = {'old_file': fname, 'title': title, 'year': year,
                             'status': 'no_4k'}
            save_manifest(manifest)
            skipped += 1
            continue

        sel = results[pick]
        print(f"      4K pick: {sel['title'][:70]}  ({sel.get('seeders',0)} seeds, {sel.get('size','?')})")
        ok = trigger_download(title, sel['magnet'])
        manifest[key] = {'old_file': fname, 'title': title, 'year': year,
                         'new_pick': sel['title'], 'status': 'triggered' if ok else 'trigger_failed'}
        save_manifest(manifest)
        print(f"      {'triggered' if ok else 'TRIGGER FAILED'}\n")
        if ok:
            triggered += 1
            time.sleep(5)  # be gentle on qbittorrent

    print(f"\nDone. triggered={triggered}  skipped(no 4K)={skipped}  already={already}")
    print(f"Manifest: {MANIFEST_FILE}")
    print("Run `redownload_4k.py cleanup` later (once downloads finish) to remove the old 1080p files.")


def cmd_status():
    manifest = load_manifest()
    if not manifest:
        print("No manifest yet — run `search` first.")
        return
    by_status: dict[str, list] = {}
    for k, v in manifest.items():
        by_status.setdefault(v.get('status', '?'), []).append(v)
    for status, items in sorted(by_status.items()):
        print(f"\n=== {status} ({len(items)}) ===")
        for v in items:
            print(f"  {v.get('title')} ({v.get('year')})")


def cmd_cleanup(confirm: bool):
    directory = movies_dir()
    manifest = load_manifest()
    pending = [(k, v) for k, v in manifest.items() if v.get('status') == 'triggered']
    if not pending:
        print("Nothing pending cleanup.")
        return

    print(f"{'DELETING' if confirm else 'DRY RUN — would delete'} superseded 1080p files:\n")
    deleted = waiting = 0
    for key, v in pending:
        old = v['old_file']
        new4k = find_4k_on_disk(directory, v['title'], v.get('year'), old)
        if not new4k:
            print(f"  WAIT  {v['title']} ({v.get('year')}) — 4K not on disk yet")
            waiting += 1
            continue

        old_base = os.path.splitext(old)[0]
        siblings = [f for f in os.listdir(directory)
                    if f.startswith(old_base) and (f.endswith(SUB_EXTS)
                    or f.endswith('.bak') or f == old)]
        print(f"  {'DEL ' if confirm else 'would'}  {old}")
        print(f"        ↳ replaced by: {new4k}")
        for s in siblings:
            if s != old:
                print(f"        ↳ + sidecar: {s}")
        if confirm:
            for s in siblings:
                try:
                    os.remove(os.path.join(directory, s))
                except FileNotFoundError:
                    pass
            v['status'] = 'done'
            v['new_file'] = new4k
            save_manifest(manifest)
            deleted += 1

    print(f"\n{'Deleted' if confirm else 'Would delete'} {len(pending) - waiting} movie(s); "
          f"{waiting} still waiting on their 4K download.")
    if not confirm:
        print("Re-run with --confirm to actually delete.")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'search':
        cmd_search()
    elif cmd == 'status':
        cmd_status()
    elif cmd == 'cleanup':
        cmd_cleanup('--confirm' in sys.argv)
    else:
        print(__doc__)
        sys.exit(1)
