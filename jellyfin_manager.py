"""
Jellyfin Media Server management module.
Handles library refresh and virtual folder creation via REST API.
"""

import logging
from typing import Optional
from urllib.parse import quote
import requests

from config import JellyfinConfig


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
