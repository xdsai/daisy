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
CHECK_INTERVAL = 1800  # 30 minutes

API_PORT = os.getenv('DAISY_PORT', '5000')
API_KEY = os.getenv('DAISY_API_KEY', '')
API_BASE = f'http://127.0.0.1:{API_PORT}'

LLM_BASE = os.getenv('LLM_BASE', 'http://127.0.0.1:3456')
LLM_MODEL = os.getenv('LLM_MODEL', 'claude-haiku-4-5-20251001')


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

def fetch_watchlist(username: str) -> list[dict]:
    """Fetch watchlist using letterboxdpy, with DIY scrape fallback."""
    try:
        from letterboxdpy.watchlist import Watchlist
        w = Watchlist(username)
        movies = []
        for _, movie in w.movies.items():
            movies.append({
                'name': movie['name'],
                'year': movie.get('year'),
                'slug': movie.get('slug', ''),
            })
        return movies
    except Exception as e:
        logger.warning(f"letterboxdpy failed ({e}), trying DIY scrape")
        return _scrape_watchlist(username)


def _scrape_watchlist(username: str) -> list[dict]:
    """Fallback scraper using requests + BeautifulSoup."""
    from bs4 import BeautifulSoup

    movies = []
    page = 1
    while True:
        url = f"https://letterboxd.com/{username}/watchlist/page/{page}/"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, 'html.parser')
        posters = soup.select('li.poster-container div.really-lazy-load')
        if not posters:
            break
        for el in posters:
            name = el.img.get('alt', '') if el.img else ''
            slug = el.get('data-film-slug', '')
            movies.append({'name': name, 'year': None, 'slug': slug})
        if len(posters) < 28:
            break
        page += 1
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

Pick the single best option. Prefer:
- 1080p quality (required — skip anything that isn't 1080p)
- BluRay or WEB-DL over cam/hdtv
- high seeder count
- reputable sources (YTS, RARBG, etc.)
- reasonable file size (1-5 GB ideal for 1080p)

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
