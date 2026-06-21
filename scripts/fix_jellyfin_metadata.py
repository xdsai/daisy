#!/usr/bin/env python3
"""
Fix Jellyfin movie metadata problems:

  * screengrab posters — items matched to TMDB but with no backdrop (a reliable
    sign Jellyfin failed to pull artwork and fell back to a video frame), and
  * misidentifications — a messy release filename matched to the wrong title
    (e.g. "WALL-E ..." -> a behind-the-scenes featurette).

Usage:
    python scripts/fix_jellyfin_metadata.py scan              # list suspect items
    python scripts/fix_jellyfin_metadata.py refresh           # force art+meta refresh on suspects
    python scripts/fix_jellyfin_metadata.py identify "<path substr>" <tmdb_id>
                                                              # force a specific item to a TMDB id
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import requests
from daisy.config import Config
from daisy.jellyfin_manager import JellyfinManager

c = Config.load()
jf = JellyfinManager(c.jellyfin)
BASE = c.jellyfin.url


def all_movies(fields: str):
    r = requests.get(
        f"{BASE}/Items", headers=jf.headers,
        params={'Recursive': 'true', 'IncludeItemTypes': 'Movie', 'Fields': fields},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('Items', [])


def suspects() -> list:
    """Movies matched to TMDB but missing a backdrop — likely screengrab posters."""
    out = []
    for it in all_movies('BackdropImageTags,ProviderIds,Path'):
        pid = it.get('ProviderIds') or {}
        if pid.get('Tmdb') and not (it.get('BackdropImageTags') or []):
            out.append(it)
    return out


def refresh_item(item_id: str, replace_images: bool = True):
    return requests.post(
        f"{BASE}/Items/{item_id}/Refresh", headers=jf.headers,
        params={
            'metadataRefreshMode': 'FullRefresh',
            'imageRefreshMode': 'FullRefresh',
            'replaceAllImages': str(replace_images).lower(),
        },
        timeout=60,
    )


def cmd_scan():
    s = suspects()
    print(f"{len(s)} suspect movie(s) (TMDB-matched but no backdrop):")
    for it in s:
        print(f"  {it['Name']:40}  {it.get('Path','')}")


def cmd_refresh():
    s = suspects()
    if not s:
        print("No suspect items — nothing to refresh.")
        return
    for it in s:
        rr = refresh_item(it['Id'])
        print(f"  refresh {it['Name']:40} HTTP {rr.status_code}")
    print(f"Triggered refresh on {len(s)} item(s). Give Jellyfin a minute to fetch.")


def cmd_identify(path_substr: str, tmdb_id: str):
    matches = [it for it in all_movies('Path') if path_substr.lower() in (it.get('Path') or '').lower()]
    if not matches:
        print(f"No movie whose path contains {path_substr!r}")
        return
    if len(matches) > 1:
        print(f"Ambiguous — {len(matches)} matches, be more specific:")
        for it in matches:
            print(f"  {it.get('Path')}")
        return
    it = matches[0]
    body = {'ProviderIds': {'Tmdb': str(tmdb_id)}}
    rr = requests.post(
        f"{BASE}/Items/RemoteSearch/Apply/{it['Id']}", headers=jf.headers,
        params={'replaceAllImages': 'true'}, json=body, timeout=60,
    )
    print(f"Re-identified {it['Name']!r} → TMDB {tmdb_id}: HTTP {rr.status_code}")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    if cmd == 'scan':
        cmd_scan()
    elif cmd == 'refresh':
        cmd_refresh()
    elif cmd == 'identify' and len(sys.argv) == 4:
        cmd_identify(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
