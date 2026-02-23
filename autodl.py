"""
Automated download daemon for SubsPlease RSS feed.
Monitors RSS feed and automatically downloads matching shows.
"""

import logging
import json
import os
import time
import re
import requests
import feedparser


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        filename='alog',
        filemode='a',
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',  # Fixed date format
        level=logging.INFO
    )


logger = logging.getLogger(__name__)


SUBSPLEASE_RSS = 'https://subsplease.org/rss/?r=1080'
QUERIES_FILE = 'autodl_queries.json'
DOWNLOADED_FILE = 'downloaded.json'
CHECK_INTERVAL = 1200  # 20 minutes

API_PORT = os.getenv('DAISY_PORT', '5000')
API_KEY = os.getenv('DAISY_API_KEY', '')
API_BASE = f'http://127.0.0.1:{API_PORT}'


def load_json_file(filepath: str, default=None):
    """Load a JSON file with error handling."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File not found: {filepath}, using default")
        return default or []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return default or []


def save_json_file(filepath: str, data):
    """Save data to JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")
        return False


def fetch_shows():
    """
    Fetch shows from SubsPlease RSS feed.

    Returns:
        List of dicts with 'name', 'magnet', and 'title'
    """
    try:
        feed = feedparser.parse(SUBSPLEASE_RSS)
        releases = []

        for entry in feed.entries:
            name = re.sub('- 1080', '', entry.category).strip()
            releases.append({
                "name": name,
                "magnet": entry.link,
                "title": entry.title
            })

        logger.info(f"Fetched {len(releases)} releases from RSS feed")
        return releases

    except Exception as e:
        logger.error(f"Failed to fetch shows: {e}")
        return []


def trigger_download(show_name: str, magnet: str) -> bool:
    """
    Trigger a download via the Daisy API server.

    Args:
        show_name: Name of the show
        magnet: Magnet link to download

    Returns:
        True if API accepted the download, False otherwise
    """
    try:
        logger.info(f"Triggering download via API: {show_name}")
        response = requests.post(
            f"{API_BASE}/download",
            json={
                'name': show_name,
                'type': 'show',
                'magnet': magnet,
            },
            headers={'X-API-Key': API_KEY},
            timeout=30,
        )
        if response.status_code == 200:
            logger.info(f"API accepted download: {show_name}")
            return True
        else:
            logger.error(f"API error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to trigger download for {show_name}: {e}")
        return False


def process_releases(queries: list, releases: list, downloaded: list) -> list:
    """
    Process releases and trigger downloads for matches.

    Args:
        queries: List of query strings to match
        releases: List of release dicts
        downloaded: List of already downloaded titles

    Returns:
        Updated downloaded list
    """
    for query in queries:
        logger.info(f"Checking query: {query}")

        for show in releases:
            # Case-insensitive match
            if query.lower() in show['name'].lower():
                logger.info(f"Query matched: {show['name']}")

                # Check if already downloaded
                if show['title'] in downloaded:
                    logger.info(f"Already downloaded, skipping: {show['title']}")
                    continue

                # Trigger download
                logger.info(f"New show to download: {show['title']}")
                if trigger_download(show['name'], show['magnet']):
                    downloaded.append(show['title'])
                    save_json_file(DOWNLOADED_FILE, downloaded)

                    # Sleep to avoid overloading
                    time.sleep(20)

    return downloaded


def main():
    """Main loop."""
    setup_logging()
    logger.info("Starting autodl daemon...")

    while True:
        try:
            logger.info("--------------NEW ITERATION---------------")

            # Load queries and downloaded list
            queries = load_json_file(QUERIES_FILE, default=[])
            downloaded = load_json_file(DOWNLOADED_FILE, default=[])

            logger.info(f"Loaded {len(queries)} queries")
            logger.info(f"Downloaded list has {len(downloaded)} items")

            # Fetch releases
            releases = fetch_shows()

            if releases:
                # Process and trigger downloads
                downloaded = process_releases(queries, releases, downloaded)
            else:
                logger.warning("No releases fetched")

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)

        # Sleep before next check
        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds")
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
