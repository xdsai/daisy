"""
Download manager module for qBittorrent operations.
"""

import time
import re
import logging
from typing import Optional, Dict, Any

from qbittorrent import Client

from config import QBittorrentConfig


logger = logging.getLogger(__name__)


class DownloadManager:
    """Manages torrent downloads via qBittorrent."""

    def __init__(self, config: QBittorrentConfig):
        self.config = config
        self.client = Client(config.url)
        self.connected = False

    def connect(self) -> bool:
        """
        Connect to qBittorrent.

        Returns:
            True if successful, False otherwise
        """
        try:
            login_result = self.client.login(
                self.config.username,
                self.config.password
            )

            if login_result == 'Fails':
                logger.error("Failed to login to qBittorrent")
                self.connected = False
                return False

            logger.info("Successfully logged in to qBittorrent")
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Exception connecting to qBittorrent: {e}")
            self.connected = False
            return False

    def download(
        self,
        magnet: str,
        save_path: str,
        timeout: int = 120
    ) -> Optional[Dict[str, Any]]:
        """
        Download a torrent and wait for completion.

        Args:
            magnet: Magnet link
            save_path: Path to save downloaded files
            timeout: Metadata download timeout in seconds

        Returns:
            Torrent info dict if successful, None if failed
        """
        if not self.connected:
            logger.error("Not connected to qBittorrent")
            return None

        logger.info(f"Starting download to: {save_path}")

        # Extract infohash from magnet for tracking
        infohash = None
        try:
            match = re.search(r'btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})', magnet)
            if match:
                infohash = match.group(1).upper()
                logger.info(f"Extracted infohash: {infohash}")
        except Exception as e:
            logger.warning(f"Could not extract infohash: {e}")

        try:
            # Start the download
            # NOTE: qBittorrent API sometimes returns "Fails." even when it works
            # So we don't trust the response - we check if torrent actually appears
            response = self.client.download_from_link(magnet, save_path=save_path)
            logger.info(f"qBittorrent response: {response}")

        except Exception as e:
            logger.error(f"Exception starting download: {e}")
            return None

        # Wait for torrent to appear in the queue
        time.sleep(5)

        try:
            # Get the most recently added torrent
            torrents = self.client.torrents(limit=1, sort='added_on', reverse=True)
            if not torrents:
                logger.error("No torrents found after starting download")
                return None

            torrent_info = torrents[0]

            # Verify this is actually our torrent
            if infohash:
                torrent_hash = torrent_info.get('infohash_v1', '').upper()
                if torrent_hash != infohash:
                    logger.warning(f"Most recent torrent hash mismatch: {torrent_hash} != {infohash}")
                    # Try to find our torrent in the full list
                    all_torrents = self.client.torrents()
                    for t in all_torrents:
                        if t.get('infohash_v1', '').upper() == infohash:
                            torrent_info = t
                            logger.info(f"Found our torrent by infohash: {t['name']}")
                            break
                    else:
                        logger.error("Could not find torrent with matching infohash")
                        return None

            torrent_name = torrent_info['name']
            logger.info(f"Found torrent: {torrent_name}")

            # Monitor download progress
            return self._monitor_download(torrent_info, torrent_name, timeout)

        except Exception as e:
            logger.error(f"Exception during download monitoring: {e}")
            return None

    def _monitor_download(
        self,
        torrent_info: Dict[str, Any],
        torrent_name: str,
        metadata_timeout: int
    ) -> Optional[Dict[str, Any]]:
        """
        Monitor torrent download until completion.

        Args:
            torrent_info: Initial torrent info dict
            torrent_name: Name of the torrent
            metadata_timeout: Timeout for metadata download in seconds

        Returns:
            Final torrent info dict, or None if failed
        """
        meta_dl_counter = 0

        # Wait for download to complete
        while torrent_info['amount_left'] != 0 or torrent_info['state'] == 'metaDL':
            # Refresh torrent info
            for torrent in self.client.torrents():
                if torrent['name'] == torrent_name:
                    torrent_info = torrent
                    break

            time.sleep(1)

            # Check for metadata download timeout
            if torrent_info['state'] == 'metaDL':
                meta_dl_counter += 1

                if meta_dl_counter > metadata_timeout:
                    logger.error(f"Metadata download timeout: {torrent_name}")
                    self._delete_torrent(torrent_info.get('infohash_v1'))
                    return None

        logger.info("Download completed")
        logger.debug(f"Final torrent info: {torrent_info}")

        return torrent_info

    def _delete_torrent(self, infohash: Optional[str]) -> bool:
        """
        Delete a torrent by infohash.

        Args:
            infohash: Torrent infohash

        Returns:
            True if successful, False otherwise
        """
        if not infohash:
            logger.error("No infohash provided for deletion")
            return False

        try:
            self.client.delete(infohash)
            logger.info(f"Deleted torrent with infohash: {infohash}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete torrent {infohash}: {e}")
            return False

    def get_torrents(self) -> list:
        """
        Get list of all torrents.

        Returns:
            List of torrent info dicts
        """
        try:
            return self.client.torrents()
        except Exception as e:
            logger.error(f"Failed to get torrents: {e}")
            return []
