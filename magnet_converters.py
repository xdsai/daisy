"""
Magnet link converter module.
Converts various torrent site URLs to magnet links.
"""

import logging
import re
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession

from config import USER_AGENT


logger = logging.getLogger(__name__)


class MagnetConverter:
    """Handles conversion of torrent site URLs to magnet links."""

    def __init__(self):
        self.session = HTMLSession()

    def convert(self, link: str) -> List[str]:
        """
        Convert a URL or magnet link to a list of magnet links.

        Args:
            link: URL or magnet link to convert

        Returns:
            List of magnet links (empty if conversion fails)
        """
        if link.startswith('magnet:?xt='):
            logger.info("Link is already a magnet link")
            return [link]

        logger.info(f"Converting link: {link[:60]}...")

        if '1337x.to' in link:
            return self._convert_1337x(link)
        elif 'nyaa.si' in link:
            return self._convert_nyaa(link)
        elif 'ext.to' in link:
            return self._convert_ext_to(link)
        elif 'subsplease.org' in link:
            return self._convert_subsplease(link)
        else:
            logger.warning(f"Unknown site, attempting generic conversion")
            return self._convert_generic(link)

    def _convert_generic(self, link: str) -> List[str]:
        """Generic converter using BeautifulSoup."""
        try:
            response = requests.get(link, headers=USER_AGENT, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            for href_tag in soup.find_all('a', href=True):
                href = href_tag['href']
                if href.startswith('magnet:?xt='):
                    logger.info(f"Found magnet link via generic conversion")
                    return [href]

            logger.error("No magnet link found with generic conversion")
            return []
        except Exception as e:
            logger.error(f"Generic conversion failed: {e}")
            return []

    def _convert_1337x(self, link: str) -> List[str]:
        """Convert 1337x.to URLs to magnet links."""
        try:
            response = requests.get(link, headers=USER_AGENT, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            for href_tag in soup.find_all('a', href=True):
                href = href_tag['href']
                if href.startswith('magnet:?xt='):
                    logger.info("Found magnet link on 1337x")
                    return [href]

            logger.error("No magnet link found on 1337x page")
            return []
        except Exception as e:
            logger.error(f"Failed to convert 1337x link: {e}")
            return []

    def _convert_nyaa(self, link: str) -> List[str]:
        """Convert nyaa.si URLs to magnet links."""
        try:
            response = requests.get(link, headers=USER_AGENT, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            for href_tag in soup.find_all('a', href=True):
                href = href_tag['href']
                if href.startswith('magnet:?xt='):
                    logger.info("Found magnet link on nyaa.si")
                    return [href]

            logger.error("No magnet link found on nyaa.si page")
            return []
        except Exception as e:
            logger.error(f"Failed to convert nyaa link: {e}")
            return []

    def _convert_ext_to(self, link: str) -> List[str]:
        """
        Convert ext.to URLs to magnet links.
        Uses JavaScript rendering since ext.to loads content dynamically.
        """
        try:
            logger.info("Converting ext.to link (using JS rendering)")

            # Try with JavaScript rendering first (ext.to likely uses dynamic content)
            response = self.session.get(link, headers=USER_AGENT, timeout=30)

            # Render JavaScript and wait for content to load
            response.html.render(wait=5, timeout=20)

            # Look for magnet links in the rendered content
            for abs_link in response.html.absolute_links:
                if abs_link.startswith('magnet:?xt='):
                    logger.info("Found magnet link on ext.to (via JS rendering)")
                    return [abs_link]

            # Fallback to checking the HTML elements
            for element in response.html.find('a'):
                href = element.attrs.get('href', '')
                if href.startswith('magnet:?xt='):
                    logger.info("Found magnet link on ext.to (via element search)")
                    return [href]

            # If JS rendering didn't work, try simple BeautifulSoup as fallback
            logger.info("JS rendering didn't find magnet, trying static parse")
            soup = BeautifulSoup(response.html.html, 'html.parser')
            for href_tag in soup.find_all('a', href=True):
                href = href_tag['href']
                if href.startswith('magnet:?xt='):
                    logger.info("Found magnet link on ext.to (via static parse)")
                    return [href]

            logger.error("No magnet link found on ext.to page")
            return []
        except Exception as e:
            logger.error(f"Failed to convert ext.to link: {e}")
            return []

    def _convert_subsplease(self, link: str) -> List[str]:
        """
        Convert subsplease.org URLs to magnet links.
        Returns all 1080p magnet links, prioritizing batch releases.
        """
        try:
            logger.info("Converting subsplease.org link")
            magnets = []
            retry_counter = 0

            while retry_counter < 5:
                response = self.session.get(link, headers=USER_AGENT)
                response.html.render(wait=10, timeout=30)

                for abs_link in response.html.absolute_links:
                    if abs_link.startswith('magnet:?xt=') and '1080p' in abs_link:
                        if 'Batch' in abs_link:
                            logger.info("Found batch magnet on subsplease")
                            # Batch magnet takes priority, return immediately
                            return [abs_link]
                        else:
                            magnets.append(abs_link)

                if len(magnets) == 0:
                    retry_counter += 1
                    logger.info(f"No magnets found, retry {retry_counter}/5")
                else:
                    break

            logger.info(f"Found {len(magnets)} magnet(s) on subsplease")
            return magnets
        except Exception as e:
            logger.error(f"Failed to convert subsplease link: {e}")
            return []

    def close(self):
        """Close the HTML session."""
        try:
            self.session.close()
        except:
            pass
