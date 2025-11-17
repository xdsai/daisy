"""
Plex Media Server management module.
Handles Plex library operations and section creation.
"""

import logging
from typing import Optional
from urllib.parse import urlencode
import requests
from plexapi.server import PlexServer

from config import PlexConfig


logger = logging.getLogger(__name__)


class PlexManager:
    """Manages Plex Media Server operations."""

    def __init__(self, config: PlexConfig):
        self.config = config
        self.server = PlexServer(config.url, config.token)
        logger.info(f"Connected to Plex server: {self.server}")

    def update_library(self) -> bool:
        """
        Update all Plex libraries.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.server.library.update()
            logger.info("Updated Plex library")
            return True
        except Exception as e:
            logger.error(f"Failed to update Plex library: {e}")
            return False

    def create_show_section(
        self,
        name: str,
        location: str
    ) -> bool:
        """
        Create a new TV show section in Plex.

        Args:
            name: Display name for the section
            location: File system path to the show directory

        Returns:
            True if successful, False otherwise
        """
        params = {
            'name': name,
            'type': 'show',
            'agent': 'tv.plex.agents.series',
            'scanner': 'Plex TV Series',
            'language': 'en-US',
            'location': location,
            'X-Plex-Token': self.config.token,
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '4.76.1',
            'X-Plex-Client-Identifier': '9fqw27x73r6ygz9hstlg47kq',
            'X-Plex-Platform': 'Firefox',
            'X-Plex-Platform-Version': '99.0',
            'X-Plex-Sync-Version': '2',
            'X-Plex-Features': 'external-media,indirect-media',
            'X-Plex-Model': 'bundled',
            'X-Plex-Device': 'Linux',
            'X-Plex-Device-Name': 'Firefox',
            'X-Plex-Device-Screen-Resolution': '1920x921,1920x1080',
            'X-Plex-Language': 'en',
        }

        url = f"{self.config.url}/library/sections"
        return self._create_section(url, params, name)

    def create_movie_section(
        self,
        name: str,
        location: str
    ) -> bool:
        """
        Create a new movie section in Plex.

        Args:
            name: Display name for the section
            location: File system path to the movie directory

        Returns:
            True if successful, False otherwise
        """
        params = {
            'name': name,
            'type': 'movie',
            'agent': 'com.plexapp.agents.none',
            'scanner': 'Plex Video Files Scanner',
            'language': 'xn',
            'location': location,
            'X-Plex-Token': self.config.token,
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '4.76.1',
            'X-Plex-Client-Identifier': '9fqw27x73r6ygz9hstlg47kq',
            'X-Plex-Platform': 'Firefox',
            'X-Plex-Platform-Version': '99.0',
            'X-Plex-Sync-Version': '2',
            'X-Plex-Features': 'external-media,indirect-media',
            'X-Plex-Model': 'bundled',
            'X-Plex-Device': 'Linux',
            'X-Plex-Device-Name': 'Firefox',
            'X-Plex-Device-Screen-Resolution': '1920x921,1920x1080',
            'X-Plex-Language': 'en',
        }

        url = f"{self.config.url}/library/sections"
        return self._create_section(url, params, name)

    def _create_section(self, url: str, params: dict, name: str) -> bool:
        """
        Internal method to create a section with proper error handling.

        Args:
            url: Base URL for the request
            params: Query parameters
            name: Section name (for logging)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Properly encode the URL with parameters
            # This fixes the issue where special characters in show names cause failures
            query_string = urlencode(params)
            full_url = f"{url}?{query_string}"

            logger.info(f"Creating Plex section for: {name}")
            logger.debug(f"Request URL: {full_url}")

            response = requests.post(full_url, timeout=30)

            if response.status_code == 201:
                logger.info(f"Successfully created Plex section: {name}")
                return True
            elif response.status_code == 409:
                # Section already exists
                logger.info(f"Plex section already exists: {name}")
                return True
            else:
                logger.error(
                    f"Failed to create Plex section '{name}': "
                    f"status={response.status_code}, reason={response.reason}"
                )
                logger.debug(f"Response body: {response.text}")
                return False

        except requests.exceptions.Timeout:
            logger.error(f"Timeout creating Plex section: {name}")
            return False
        except Exception as e:
            logger.error(f"Exception creating Plex section '{name}': {e}")
            return False

    def section_exists(self, name: str) -> bool:
        """
        Check if a Plex section exists.

        Args:
            name: Section name to check

        Returns:
            True if exists, False otherwise
        """
        try:
            sections = self.server.library.sections()
            for section in sections:
                if section.title == name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking if section exists: {e}")
            return False
