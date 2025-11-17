"""
Torrent search module - searches multiple torrent indexes.
Returns ranked results with metadata for user selection.
"""

import logging
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import requests
from bs4 import BeautifulSoup
import feedparser

from config import USER_AGENT


logger = logging.getLogger(__name__)


@dataclass
class TorrentResult:
    """Represents a single torrent search result."""
    title: str
    magnet: str
    size: str
    seeders: int
    leechers: int
    source: str
    uploader: str = "Unknown"
    quality: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'title': self.title,
            'magnet': self.magnet,
            'size': self.size,
            'seeders': self.seeders,
            'leechers': self.leechers,
            'source': self.source,
            'uploader': self.uploader,
            'quality': self.quality,
            'score': self.calculate_score()
        }

    def calculate_score(self) -> float:
        """
        Calculate a score for ranking torrents.
        Higher score = better torrent.
        """
        score = 0.0

        # Seeders are most important
        score += self.seeders * 10

        # Quality bonuses
        if '1080p' in self.quality or '1080p' in self.title.lower():
            score += 50
        elif '720p' in self.quality or '720p' in self.title.lower():
            score += 30
        elif '2160p' in self.quality or '4k' in self.title.lower():
            score += 40

        # Trusted uploaders
        trusted_uploaders = ['subsplease', 'eztv', 'yts', 'rarbg', 'ettv']
        if any(uploader in self.uploader.lower() for uploader in trusted_uploaders):
            score += 25

        # Penalty for no seeders
        if self.seeders == 0:
            score = 0

        return score


class TorrentSearcher:
    """Searches multiple torrent indexes and aggregates results."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(USER_AGENT)

    def search(
        self,
        query: str,
        media_type: str = 'auto',
        limit: int = 20
    ) -> List[TorrentResult]:
        """
        Search for torrents across multiple indexes.

        Args:
            query: Search query (e.g., "Chainsaw Man 05")
            media_type: 'anime', 'movie', 'show', or 'auto'
            limit: Maximum number of results to return

        Returns:
            List of TorrentResult objects, sorted by score
        """
        results = []

        # Determine which sources to search
        if media_type == 'anime' or self._looks_like_anime(query):
            logger.info("Searching anime sources")
            results.extend(self._search_nyaa(query))
        else:
            logger.info("Searching general sources")
            results.extend(self._search_1337x(query))

        # Sort by score (best first)
        results.sort(key=lambda x: x.calculate_score(), reverse=True)

        # Return top results
        return results[:limit]

    def _looks_like_anime(self, query: str) -> bool:
        """Heuristic to detect if query is for anime."""
        anime_keywords = [
            'sub', 'dub', 'episode', 'ep', 'season',
            'subsplease', 'horriblesubs', 'erai-raws'
        ]
        return any(keyword in query.lower() for keyword in anime_keywords)

    def _search_nyaa(self, query: str) -> List[TorrentResult]:
        """
        Search nyaa.si for anime torrents.
        Uses RSS feed for reliable parsing.
        """
        results = []

        try:
            # Nyaa RSS search
            url = f"https://nyaa.si/?page=rss&q={requests.utils.quote(query)}"
            logger.info(f"Searching nyaa.si: {url}")

            feed = feedparser.parse(url)

            for entry in feed.entries:
                try:
                    # Extract seeders/leechers from description
                    seeders = 0
                    leechers = 0
                    size = "Unknown"

                    if hasattr(entry, 'nyaa_seeders'):
                        seeders = int(entry.nyaa_seeders)
                    if hasattr(entry, 'nyaa_leechers'):
                        leechers = int(entry.nyaa_leechers)
                    if hasattr(entry, 'nyaa_size'):
                        size = entry.nyaa_size

                    # Parse from summary if available
                    if hasattr(entry, 'summary'):
                        summary = entry.summary
                        seeders_match = re.search(r'(\d+)\s*seeder', summary, re.I)
                        leechers_match = re.search(r'(\d+)\s*leecher', summary, re.I)
                        size_match = re.search(r'(\d+\.?\d*\s*[KMGT]iB)', summary, re.I)

                        if seeders_match:
                            seeders = int(seeders_match.group(1))
                        if leechers_match:
                            leechers = int(leechers_match.group(1))
                        if size_match:
                            size = size_match.group(1)

                    # Extract quality from title
                    quality = ""
                    quality_match = re.search(r'(1080p|720p|480p|2160p|4K)', entry.title, re.I)
                    if quality_match:
                        quality = quality_match.group(1)

                    # Extract uploader from title (usually in brackets)
                    uploader = "Unknown"
                    uploader_match = re.search(r'\[([^\]]+)\]', entry.title)
                    if uploader_match:
                        uploader = uploader_match.group(1)

                    result = TorrentResult(
                        title=entry.title,
                        magnet=entry.link,
                        size=size,
                        seeders=seeders,
                        leechers=leechers,
                        source='nyaa.si',
                        uploader=uploader,
                        quality=quality
                    )

                    results.append(result)

                except Exception as e:
                    logger.warning(f"Failed to parse nyaa entry: {e}")
                    continue

            logger.info(f"Found {len(results)} results from nyaa.si")

        except Exception as e:
            logger.error(f"Failed to search nyaa.si: {e}")

        return results

    def _search_1337x(self, query: str) -> List[TorrentResult]:
        """
        Search 1337x.to for general torrents.
        """
        results = []

        try:
            # Search page
            search_url = f"https://1337x.to/search/{requests.utils.quote(query)}/1/"
            logger.info(f"Searching 1337x.to: {search_url}")

            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all torrent rows
            rows = soup.find_all('tr')

            for row in rows:
                try:
                    # Find title and link
                    name_cell = row.find('td', class_='name')
                    if not name_cell:
                        continue

                    title_link = name_cell.find('a', href=re.compile(r'/torrent/'))
                    if not title_link:
                        continue

                    title = title_link.text.strip()
                    detail_url = "https://1337x.to" + title_link['href']

                    # Get seeders/leechers
                    seeders_cell = row.find('td', class_='seeds')
                    leechers_cell = row.find('td', class_='leeches')
                    size_cell = row.find('td', class_='size')

                    seeders = int(seeders_cell.text.strip()) if seeders_cell else 0
                    leechers = int(leechers_cell.text.strip()) if leechers_cell else 0
                    size = size_cell.text.strip() if size_cell else "Unknown"

                    # Get uploader
                    uploader_cell = row.find('td', class_='uploader')
                    uploader = uploader_cell.text.strip() if uploader_cell else "Unknown"

                    # Extract quality
                    quality = ""
                    quality_match = re.search(r'(1080p|720p|480p|2160p|4K)', title, re.I)
                    if quality_match:
                        quality = quality_match.group(1)

                    # We need to get the magnet link from detail page
                    # For now, store the detail URL and get magnet later
                    magnet = self._get_magnet_from_1337x(detail_url)

                    if magnet:
                        result = TorrentResult(
                            title=title,
                            magnet=magnet,
                            size=size,
                            seeders=seeders,
                            leechers=leechers,
                            source='1337x.to',
                            uploader=uploader,
                            quality=quality
                        )

                        results.append(result)

                except Exception as e:
                    logger.warning(f"Failed to parse 1337x row: {e}")
                    continue

            logger.info(f"Found {len(results)} results from 1337x.to")

        except Exception as e:
            logger.error(f"Failed to search 1337x.to: {e}")

        return results

    def _get_magnet_from_1337x(self, detail_url: str) -> Optional[str]:
        """Get magnet link from 1337x detail page."""
        try:
            response = self.session.get(detail_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find magnet link
            magnet_link = soup.find('a', href=re.compile(r'^magnet:\?'))

            if magnet_link:
                return magnet_link['href']

        except Exception as e:
            logger.warning(f"Failed to get magnet from {detail_url}: {e}")

        return None


def search_torrents(query: str, media_type: str = 'auto', limit: int = 20) -> List[Dict]:
    """
    Convenience function to search torrents.

    Args:
        query: Search query
        media_type: Type of media
        limit: Max results

    Returns:
        List of torrent dicts
    """
    searcher = TorrentSearcher()
    results = searcher.search(query, media_type, limit)
    return [r.to_dict() for r in results]
