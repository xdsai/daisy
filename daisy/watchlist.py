"""
Letterboxd watchlist monitor daemon.
Polls a Letterboxd watchlist for new movies, uses an LLM to pick the best
1080p torrent from search results, and triggers download via the Daisy API.
"""

import json
import logging
import os
import time
import requests

_REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

WATCHLIST_USER = os.getenv('WATCHLIST_USER', 'alexsex')
SEEN_FILE = os.path.join(_REPO_ROOT, 'watchlist_seen.json')
CHECK_INTERVAL = 120  # 2 minutes

API_PORT = os.getenv('DAISY_PORT', '5000')
API_KEY = os.getenv('DAISY_API_KEY', '')
API_BASE = f'http://127.0.0.1:{API_PORT}'

LLM_BASE = os.getenv('LLM_BASE', 'http://127.0.0.1:3456')
LLM_MODEL = os.getenv('LLM_MODEL', 'claude-sonnet-4-6')


def setup_logging():
    logging.basicConfig(
        filename=os.path.join(_REPO_ROOT, 'logs', 'watchlist.log'),
        filemode='a',
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.INFO,
    )


logger = logging.getLogger(__name__)


# ---- persistence ----

def load_seen() -> list[str]:
    try:
        with open(SEEN_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_seen(seen: list[str]):
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f, indent=2)


# ---- letterboxd ----

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# State across cycles so we don't spam logs/discord on transient blips.
_scrape_alert_sent = False
_consecutive_failures = 0
# Threshold before pinging discord — 3 cycles = ~6 min at the default interval.
# A single failed cycle is almost always a transient network/DNS blip.
_FAILURE_THRESHOLD = 3
# Whether letterboxdpy is currently in a known-broken state. Used to suppress
# the per-cycle "letterboxdpy returned 0 movies" warning once we've already
# logged it; only re-log when state transitions.
_letterboxdpy_broken = False


def _alert_scrape_failure(reason: str):
    """
    Log loudly and send a Discord notification when scraping fails.
    Deduplicated across cycles — only fires once until the next successful
    scrape resets the flag.
    """
    global _scrape_alert_sent
    logger.error(f"WATCHLIST SCRAPE FAILURE: {reason}")
    if _scrape_alert_sent:
        return
    try:
        from .config import Config
        from .notifications import DiscordNotifier
        config = Config.load()
        DiscordNotifier(config.discord).send_embed(
            f"⚠️ Daisy watchlist scrape broken: {reason}",
            color=16711680,  # red
        )
        _scrape_alert_sent = True
    except Exception as e:
        logger.error(f"Failed to send scrape-failure notification: {e}")


def _parse_letterboxdpy_movie(movie: dict) -> dict:
    """Normalize a letterboxdpy movie dict into our internal format."""
    return {
        'name': movie.get('name', ''),
        'year': movie.get('year'),
        'slug': movie.get('slug', ''),
    }


def _fetch_via_letterboxdpy(username: str) -> list[dict]:
    from letterboxdpy.watchlist import Watchlist
    import letterboxdpy
    logger.debug(f"letterboxdpy version: {getattr(letterboxdpy, '__version__', 'unknown')}")
    w = Watchlist(username)
    return [_parse_letterboxdpy_movie(m) for m in w.movies.values()]


def _fetch_via_scrape(username: str) -> list[dict]:
    """
    DIY scraper against the current li.griditem / LazyPoster HTML structure.
    Kept as a fallback so letterboxdpy breaking doesn't fully take us down.
    """
    from bs4 import BeautifulSoup
    import re

    movies = []
    page = 1
    while True:
        url = f"https://letterboxd.com/{username}/watchlist/page/{page}/"
        resp = requests.get(url, headers=_UA, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"Watchlist page {page} returned HTTP {resp.status_code}")
            break

        soup = BeautifulSoup(resp.text, 'html.parser')
        posters = soup.select('li.griditem div.react-component[data-component-class="LazyPoster"]')
        if not posters:
            break

        for el in posters:
            slug = el.get('data-item-slug', '')
            full = el.get('data-item-full-display-name') or el.get('data-item-name', '')
            m = re.match(r'^(.*?)\s*\((\d{4})\)\s*$', full)
            if m:
                name, year = m.group(1), int(m.group(2))
            else:
                name, year = full, None
            if slug:
                movies.append({'name': name, 'year': year, 'slug': slug})

        if len(posters) < 28:
            break
        page += 1

    return movies


def fetch_watchlist(username: str) -> list[dict]:
    """
    Fetch a Letterboxd watchlist using letterboxdpy, with a DIY scrape fallback.

    Both scrapers can return 0 movies silently when Letterboxd changes its HTML
    or starts blocking specific request signatures. We track consecutive
    failures across cycles and only alert (log ERROR + Discord) once we've
    seen N back-to-back failures, so transient DNS/network blips don't page.
    """
    global _scrape_alert_sent, _consecutive_failures, _letterboxdpy_broken
    seen = load_seen()

    # primary: letterboxdpy
    letterboxdpy_failed = False
    try:
        movies = _fetch_via_letterboxdpy(username)
    except Exception as e:
        letterboxdpy_failed = True
        # Only log when state transitions from working → broken, so we don't
        # spam every 2 minutes when letterboxd is persistently blocking us.
        if not _letterboxdpy_broken:
            logger.warning(f"letterboxdpy started failing: {e}")
            _letterboxdpy_broken = True
        movies = []

    if not movies and not letterboxdpy_failed:
        # letterboxdpy returned 0 with no exception — likely an HTML change.
        if not _letterboxdpy_broken:
            logger.warning("letterboxdpy returned 0 movies (no exception)")
            _letterboxdpy_broken = True

    # fallback: DIY scrape — only if letterboxdpy returned nothing
    if not movies:
        try:
            movies = _fetch_via_scrape(username)
        except Exception as e:
            logger.error(f"DIY scrape also failed: {e}")
            movies = []

    # State transitions
    if movies:
        # reset failure tracking on any successful scrape
        if _consecutive_failures > 0 or _scrape_alert_sent:
            logger.info(f"Watchlist scraping recovered ({len(movies)} movies)")
        if _letterboxdpy_broken and not letterboxdpy_failed:
            logger.info("letterboxdpy recovered")
            _letterboxdpy_broken = False
        _consecutive_failures = 0
        _scrape_alert_sent = False
        return movies

    # Both scrapers failed — count it.
    _consecutive_failures += 1
    logger.warning(
        f"Both scrapers returned 0 movies (failure {_consecutive_failures}/{_FAILURE_THRESHOLD})"
    )

    # Loud alert only after threshold AND if we have prior history
    # (empty seen list on a fresh install is a legitimate 0 result).
    if _consecutive_failures >= _FAILURE_THRESHOLD and seen:
        _alert_scrape_failure(
            f"both letterboxdpy and DIY scrape returned 0 movies for "
            f"{username} for {_consecutive_failures} consecutive cycles "
            f"(seen list has {len(seen)} prior entries)"
        )

    return movies


# ---- torrent search (via daisy API) ----

def search_movie(name: str, year: int | None) -> list[dict]:
    """Search for torrents via the Daisy API."""
    query = f"{name} {year}" if year else name
    try:
        resp = requests.get(
            f"{API_BASE}/search",
            params={'q': query, 'type': 'movie', 'limit': '15'},
            headers={'X-API-Key': API_KEY},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get('results', [])
        else:
            logger.error(f"Search API returned {resp.status_code}: {resp.text}")
            return []
    except Exception as e:
        logger.error(f"Search API error: {e}")
        return []


# ---- LLM selection ----

def ask_llm_to_pick(movie_name: str, year: int | None, results: list[dict]) -> int | None:
    """
    Send search results to the LLM and ask it to pick the best 1080p torrent.
    Returns the index of the chosen result, or None if it can't decide.
    """
    if not results:
        return None

    # build a concise summary of each result for the LLM
    options = []
    for i, r in enumerate(results):
        options.append(
            f"[{i}] {r['title']}  |  size: {r.get('size', '?')}  |  "
            f"seeders: {r.get('seeders', 0)}  |  source: {r.get('source', '?')}  |  "
            f"quality: {r.get('quality', '?')}"
        )
    options_text = '\n'.join(options)

    year_str = f" ({year})" if year else ""
    prompt = f"""I want to download the movie "{movie_name}"{year_str} in 1080p.

Here are the torrent search results:

{options_text}

Pick the single best option. Rules (in priority order):
1. MUST be 1080p — skip anything that isn't 1080p
2. MUST have at least 10 seeders — low-seed torrents will never finish downloading
3. For ALL non-English movies (Japanese, Korean, Cantonese, French, etc.) and anime: ALWAYS prefer nyaa.si or other sources that include original language audio over YTS. YTS often strips original audio and only has English dubs. We want original language audio with subtitles, NEVER dubs.
4. Prefer BluRay or WEB-DL over cam/hdtv/screener
5. Prefer reputable sources (nyaa.si for anime/Japanese, YTS for Western films, RARBG, etc.)
6. Prefer reasonable file size (1-5 GB ideal for 1080p, up to 8 GB acceptable for better quality)
7. When in doubt, pick the one with the MOST seeders

Respond with ONLY the index number (e.g. "3"). Nothing else. If none of the results are a good 1080p match for this specific movie, respond with "SKIP"."""

    try:
        resp = requests.post(
            f"{LLM_BASE}/v1/chat/completions",
            json={
                'model': LLM_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 10,
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json()['choices'][0]['message']['content'].strip()
        logger.info(f"LLM response for '{movie_name}': {answer}")

        if answer.upper() == 'SKIP':
            return None

        idx = int(answer)
        if 0 <= idx < len(results):
            return idx
        else:
            logger.warning(f"LLM returned out-of-range index {idx}")
            return None
    except (ValueError, KeyError, IndexError):
        logger.warning(f"Could not parse LLM response: {answer!r}")
        return None
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return None


# ---- download trigger ----

def trigger_download(name: str, magnet: str) -> bool:
    """Trigger a download via the Daisy API."""
    try:
        resp = requests.post(
            f"{API_BASE}/download",
            json={'name': name, 'type': 'movie', 'magnet': magnet},
            headers={'X-API-Key': API_KEY},
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info(f"Download triggered: {name}")
            return True
        else:
            logger.error(f"Download API returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Download API error: {e}")
        return False


# ---- main loop ----

def process_watchlist():
    """Check watchlist for new movies and process them."""
    seen = load_seen()
    movies = fetch_watchlist(WATCHLIST_USER)

    if not movies:
        logger.warning("No movies fetched from watchlist")
        return

    logger.info(f"Watchlist has {len(movies)} movies, {len(seen)} already seen")

    for movie in movies:
        key = movie['slug'] or movie['name']
        if key in seen:
            continue

        name = movie['name']
        year = movie.get('year')
        logger.info(f"New movie: {name} ({year})")

        # search for torrents
        results = search_movie(name, year)
        if not results:
            logger.warning(f"No search results for '{name}', will retry next cycle")
            continue

        logger.info(f"Found {len(results)} results for '{name}'")

        # ask LLM to pick
        pick = ask_llm_to_pick(name, year, results)
        if pick is None:
            logger.info(f"LLM skipped '{name}' — no good 1080p match")
            # still mark as seen so we don't spam the LLM every cycle
            seen.append(key)
            save_seen(seen)
            continue

        selected = results[pick]
        logger.info(f"LLM picked [{pick}]: {selected['title']}")

        # trigger download
        if trigger_download(name, selected['magnet']):
            seen.append(key)
            save_seen(seen)
            # avoid hammering the API
            time.sleep(10)
        else:
            logger.error(f"Failed to trigger download for '{name}'")


def main():
    setup_logging()
    logger.info("Starting watchlist monitor daemon...")
    logger.info(f"Watching Letterboxd user: {WATCHLIST_USER}")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")

    while True:
        try:
            logger.info("--- checking watchlist ---")
            process_watchlist()
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
