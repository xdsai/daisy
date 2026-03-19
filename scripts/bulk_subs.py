#!/usr/bin/env python3
"""
Bulk subtitle downloader for Jellyfin movies.

Connects to Jellyfin, finds all movies missing English subtitles,
downloads the best match via Jellyfin's remote subtitle search (subbuzz/OpenSubtitles),
and runs jf-subsync to synchronize timing.

Uses the same config (config.json) and libraries as the main Daisy app.
"""

import os
import sys
import time
import subprocess
import logging

# Ensure we can import from the daisy repo
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import requests
from daisy.config import Config
from daisy.jellyfin_manager import JellyfinManager

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bulk_subs")

SUBSYNC = os.environ.get("JF_SUBSYNC_PATH", "jf-subsync")
SUB_EXTS = (".srt", ".ass", ".ssa", ".sub", ".vtt")
LANGUAGE = "eng"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_all_movies(jf: JellyfinManager):
    """Fetch every movie item from Jellyfin with path and stream info."""
    resp = requests.get(
        f"{jf.config.url}/Items",
        headers=jf.headers,
        params={
            "Recursive": "true",
            "Fields": "Path,MediaStreams",
            "IncludeItemTypes": "Movie",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("Items", [])


def has_english_subs(movie: dict) -> bool:
    """Return True if the movie already has at least one English subtitle stream."""
    for stream in movie.get("MediaStreams", []):
        if stream.get("Type") != "Subtitle":
            continue
        lang = (stream.get("Language") or "").lower()
        if lang in ("eng", "en", "english"):
            return True
    return False


def list_subtitle_files(directory: str) -> set:
    """Return a set of subtitle file paths in a directory."""
    result = set()
    if not os.path.isdir(directory):
        return result
    for f in os.listdir(directory):
        if f.endswith(SUB_EXTS) and not f.endswith(".bak"):
            result.add(os.path.join(directory, f))
    return result


def sync_subtitle(sub_path: str):
    """Run jf-subsync on a single subtitle file."""
    log.info("  Syncing subtitle: %s", os.path.basename(sub_path))
    try:
        result = subprocess.run(
            [SUBSYNC, sub_path],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            log.info("  Sync OK: %s", os.path.basename(sub_path))
        else:
            log.warning("  Sync FAILED (%d): %s", result.returncode, result.stderr[:300])
    except subprocess.TimeoutExpired:
        log.warning("  Sync TIMED OUT for %s", sub_path)
    except FileNotFoundError:
        log.error("  jf-subsync binary not found at '%s'. Set JF_SUBSYNC_PATH if needed.", SUBSYNC)
    except Exception as exc:
        log.error("  Sync error: %s", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = Config.load()
    jf = JellyfinManager(config.jellyfin)

    log.info("Connecting to Jellyfin at %s", config.jellyfin.url)

    # 1. Fetch all movies
    movies = get_all_movies(jf)
    log.info("Found %d movie(s) in Jellyfin", len(movies))

    # 2. Filter to those without English subs
    need_subs = [m for m in movies if not has_english_subs(m)]
    already_ok = len(movies) - len(need_subs)
    log.info("%d movie(s) already have English subs — skipping", already_ok)
    log.info("%d movie(s) need English subs", len(need_subs))

    if not need_subs:
        log.info("Nothing to do. All movies have English subtitles.")
        return

    # 3. Process each movie
    downloaded = 0
    failed = 0

    for i, movie in enumerate(need_subs, 1):
        name = movie.get("Name", "Unknown")
        item_id = movie["Id"]
        video_path = movie.get("Path", "")
        video_dir = os.path.dirname(video_path)

        log.info("[%d/%d] %s", i, len(need_subs), name)

        # Snapshot existing subtitle files so we can detect newly created ones
        subs_before = list_subtitle_files(video_dir)

        # Search and download best subtitle via Jellyfin API
        ok = jf.auto_download_subtitles(item_id, language=LANGUAGE)
        if not ok:
            log.warning("  No subtitles found for '%s'", name)
            failed += 1
            continue

        downloaded += 1
        log.info("  Subtitle downloaded for '%s'", name)

        # Give Jellyfin a moment to write the file to disk
        time.sleep(5)

        # Detect newly added subtitle files
        subs_after = list_subtitle_files(video_dir)
        new_subs = subs_after - subs_before

        if new_subs:
            for sub_path in sorted(new_subs):
                sync_subtitle(sub_path)
        else:
            # Fallback: if we can't detect the new file, sync all subs in the dir
            log.info("  Could not detect new subtitle file; syncing all subs in directory")
            for sub_path in sorted(subs_after):
                sync_subtitle(sub_path)

        log.info("  Done: %s", name)
        print()

    # 4. Summary
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("  Total movies:      %d", len(movies))
    log.info("  Already had subs:  %d", already_ok)
    log.info("  Subs downloaded:   %d", downloaded)
    log.info("  Failed/no subs:    %d", failed)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
