#!/usr/bin/env python3
"""Batch download and sync subtitles for all movies missing English subs."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from daisy.config import Config
from daisy.jellyfin_manager import JellyfinManager

config = Config.load()
jf = JellyfinManager(config.jellyfin)

# Get all movies
resp = __import__('requests').get(
    f"{config.jellyfin.url}/Items",
    headers=jf.headers,
    params={
        "Recursive": "true",
        "Fields": "Path,MediaStreams",
        "IncludeItemTypes": "Movie",
    },
    timeout=30,
)
resp.raise_for_status()
movies = resp.json().get("Items", [])

SUBSYNC = os.environ.get("JF_SUBSYNC_PATH", "jf-subsync")
SUB_EXTS = ('.srt', '.ass', '.ssa', '.sub', '.vtt')

for movie in movies:
    name = movie.get("Name", "Unknown")
    item_id = movie["Id"]
    path = movie.get("Path", "")

    # Check if it already has English subs
    streams = movie.get("MediaStreams", [])
    has_eng_sub = any(
        s.get("Type") == "Subtitle" and s.get("Language", "").lower() in ("eng", "en", "english")
        for s in streams
    )
    if has_eng_sub:
        print(f"SKIP {name} — already has English subs")
        continue

    print(f"PROCESSING {name} ({item_id})...")

    # Download best subtitle
    ok = jf.auto_download_subtitles(item_id)
    if not ok:
        print(f"  NO SUBS FOUND for {name}")
        continue

    print(f"  Downloaded subtitle for {name}")

    # Wait for Jellyfin to write the file
    time.sleep(5)

    # Find and sync subtitle files
    video_dir = os.path.dirname(path)
    if os.path.isdir(video_dir):
        for f in os.listdir(video_dir):
            if f.endswith(SUB_EXTS) and not f.endswith('.bak'):
                sub_path = os.path.join(video_dir, f)
                print(f"  Syncing {f}...")
                import subprocess
                result = subprocess.run(
                    [SUBSYNC, sub_path],
                    capture_output=True, text=True, timeout=600
                )
                if result.returncode == 0:
                    print(f"  Synced OK")
                else:
                    print(f"  Sync failed: {result.stderr[:200]}")

    print(f"  DONE {name}")
    print()

print("All done.")
