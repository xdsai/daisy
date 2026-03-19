"""
Jellyfin Media Server management module.
Handles library refresh, virtual folder creation, and subtitle management via REST API.
"""

import logging
import time
from typing import Optional
from urllib.parse import quote
import requests

from .config import JellyfinConfig


logger = logging.getLogger(__name__)


class JellyfinManager:
    """Manages Jellyfin Media Server operations."""

    def __init__(self, config: JellyfinConfig):
        self.config = config
        self.headers = {
            "Authorization": f"MediaBrowser Token={config.api_key}",
            "Content-Type": "application/json",
        }

    def update_library(self) -> bool:
        """Trigger a full library refresh."""
        try:
            response = requests.post(
                f"{self.config.url}/Library/Refresh",
                headers=self.headers,
                timeout=30,
            )
            if response.status_code == 204:
                logger.info("Triggered Jellyfin library refresh")
                return True
            else:
                logger.error(f"Library refresh failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to refresh Jellyfin library: {e}")
            return False

    def create_show_section(self, name: str, location: str) -> bool:
        """Create a new TV show virtual folder in Jellyfin."""
        return self._create_virtual_folder(name, "tvshows", location)

    def create_movie_section(self, name: str, location: str) -> bool:
        """Create a new movie virtual folder in Jellyfin."""
        return self._create_virtual_folder(name, "movies", location)

    def _create_virtual_folder(self, name: str, collection_type: str, location: str) -> bool:
        """Create a virtual folder (library) in Jellyfin."""
        try:
            url = (
                f"{self.config.url}/Library/VirtualFolders"
                f"?name={quote(name)}"
                f"&collectionType={collection_type}"
                f"&paths={quote(location)}"
                f"&refreshLibrary=true"
            )
            response = requests.post(
                url,
                headers=self.headers,
                json={"LibraryOptions": {}},
                timeout=30,
            )
            if response.status_code == 204:
                logger.info(f"Created Jellyfin library: {name} ({collection_type})")
                return True
            elif response.status_code == 409:
                logger.info(f"Jellyfin library already exists: {name}")
                return True
            else:
                logger.error(
                    f"Failed to create Jellyfin library '{name}': "
                    f"status={response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Exception creating Jellyfin library '{name}': {e}")
            return False

    def section_exists(self, name: str) -> bool:
        """Check if a virtual folder exists."""
        try:
            response = requests.get(
                f"{self.config.url}/Library/VirtualFolders",
                headers=self.headers,
                timeout=10,
            )
            if response.status_code == 200:
                folders = response.json()
                return any(f["Name"] == name for f in folders)
            return False
        except Exception as e:
            logger.error(f"Error checking if library exists: {e}")
            return False

    def find_item_by_path(self, file_path: str, retries: int = 5, delay: int = 10) -> Optional[str]:
        """
        Find a Jellyfin item ID by its file path. Retries to allow library scan to complete.

        Returns:
            Item ID string or None
        """
        for attempt in range(retries):
            try:
                response = requests.get(
                    f"{self.config.url}/Items",
                    headers=self.headers,
                    params={
                        "Recursive": "true",
                        "Fields": "Path",
                        "IncludeItemTypes": "Movie",
                    },
                    timeout=30,
                )
                if response.status_code == 200:
                    for item in response.json().get("Items", []):
                        if item.get("Path") == file_path:
                            logger.info(f"Found Jellyfin item: {item['Name']} ({item['Id']})")
                            return item["Id"]
            except Exception as e:
                logger.warning(f"Error searching Jellyfin items: {e}")

            if attempt < retries - 1:
                logger.info(f"Item not found yet, waiting {delay}s for library scan (attempt {attempt + 1}/{retries})")
                time.sleep(delay)

        logger.warning(f"Could not find Jellyfin item for path: {file_path}")
        return None

    def auto_download_subtitles(self, item_id: str, language: str = "eng") -> bool:
        """
        Search for and download the best subtitle for a Jellyfin item.
        Prefers non-HI, non-forced, highest download count.

        Returns:
            True if a subtitle was downloaded
        """
        try:
            # Search for subtitles
            response = requests.get(
                f"{self.config.url}/Items/{item_id}/RemoteSearch/Subtitles/{language}",
                headers=self.headers,
                timeout=60,
            )
            if response.status_code != 200:
                logger.warning(f"Subtitle search failed: HTTP {response.status_code}")
                return False

            results = response.json()
            if not results:
                logger.info("No subtitles found")
                return False

            # Score and pick the best subtitle
            best = None
            best_score = -1
            for sub in results:
                score = sub.get("DownloadCount", 0)
                # Prefer non-HI
                if sub.get("HearingImpaired", False):
                    score -= 500
                # Prefer non-forced
                if sub.get("Forced", False):
                    score -= 1000
                # Prefer srt format
                if sub.get("Format", "").lower() == "srt":
                    score += 100
                if score > best_score:
                    best_score = score
                    best = sub

            if not best:
                logger.info("No suitable subtitle found")
                return False

            logger.info(f"Downloading subtitle: {best.get('Name', 'unknown')} "
                       f"(downloads: {best.get('DownloadCount', 0)}, "
                       f"HI: {best.get('HearingImpaired', False)})")

            # Download the subtitle
            dl_response = requests.post(
                f"{self.config.url}/Items/{item_id}/RemoteSearch/Subtitles/{best['Id']}",
                headers=self.headers,
                timeout=60,
            )
            if dl_response.status_code == 204:
                logger.info("Subtitle downloaded successfully")
                return True
            else:
                logger.warning(f"Subtitle download failed: HTTP {dl_response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error during subtitle auto-download: {e}")
            return False
