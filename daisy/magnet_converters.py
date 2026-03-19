"""
Magnet link converter module.
Converts various torrent site URLs to magnet links.
"""

import asyncio
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession

from .config import USER_AGENT


logger = logging.getLogger(__name__)


class MagnetConverter:
    """Handles conversion of torrent site URLs to magnet links."""

    def __init__(self):
        self._ensure_event_loop()
        self.session = HTMLSession()

    @staticmethod
    def _ensure_event_loop():
        """Ensure an event loop exists for the current thread (needed by requests_html)."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def convert(self, link: str) -> List[str]:
        """
        Convert a URL or magnet link to a list of magnet links.

        Args:
            link: URL or magnet link to convert

        Returns:
            List of magnet links (empty if conversion fails)
        """
        self._ensure_event_loop()

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
            # Handle .torrent download URLs by converting to view page
            if '/download/' in link and link.endswith('.torrent'):
                # Extract ID from: https://nyaa.si/download/965131.torrent
                torrent_id = link.split('/download/')[1].replace('.torrent', '')
                view_url = f"https://nyaa.si/view/{torrent_id}"
                logger.info(f"Converted .torrent download URL to view page: {view_url}")
                link = view_url

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
        Convert subsplease.org show page URLs to magnet links.
        Uses the SubsPlease JSON API instead of JS rendering.
        Returns all 1080p magnet links, prioritizing batch releases.
        """
        try:
            logger.info("Converting subsplease.org link via API")

            # Extract show slug from URL: /shows/sousou-no-frieren-s2/ -> sousou-no-frieren-s2
            path = urlparse(link).path.rstrip('/')
            slug = path.split('/')[-1]

            if not slug:
                logger.error("Could not extract show slug from subsplease URL")
                return []

            # Use the search API with the slug as query (more reliable than /show endpoint)
            # Convert slug to search terms: "sousou-no-frieren-s2" -> "sousou no frieren s2"
            search_query = slug.replace('-', ' ')
            api_url = f"https://subsplease.org/api/?f=search&tz=UTC&s={search_query}"

            logger.info(f"Fetching SubsPlease API: {api_url}")
            response = requests.get(api_url, headers=USER_AGENT, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data or isinstance(data, list):
                logger.error("No results from SubsPlease API")
                return []

            # Collect 1080p magnets, filtering to entries whose show name matches the slug
            # e.g. slug "sousou-no-frieren-s2" should match "Sousou no Frieren S2" entries
            # but not "Sousou no Frieren" (S1) entries
            magnets = []
            batch_magnets = []

            for entry_key, entry in data.items():
                show_name = entry.get('show', '')
                # Normalize both to compare: lowercase, strip spaces/hyphens
                normalized_show = re.sub(r'[\s\-]+', '', show_name.lower())
                normalized_slug = re.sub(r'[\s\-]+', '', slug.lower())

                if normalized_show != normalized_slug:
                    continue

                for dl in entry.get('downloads', []):
                    if dl.get('res') == '1080':
                        magnet = dl.get('magnet', '')
                        if magnet:
                            if 'batch' in entry_key.lower():
                                batch_magnets.append(magnet)
                            else:
                                magnets.append(magnet)

            # Batch takes priority
            if batch_magnets:
                logger.info(f"Found {len(batch_magnets)} batch magnet(s) on subsplease")
                return batch_magnets

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
