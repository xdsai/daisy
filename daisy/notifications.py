"""
Discord notifications module.
"""

import logging
from typing import Optional
import requests

from .config import DiscordConfig


logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Handles Discord webhook notifications."""

    def __init__(self, config: DiscordConfig):
        self.config = config

    def send_embed(
        self,
        title: str,
        color: int = 65436,  # Green by default
        webhook: Optional[str] = None
    ) -> bool:
        """
        Send an embed message to Discord.

        Args:
            title: Message title
            color: Embed color (default green)
            webhook: Webhook URL (defaults to daisy_webhook)

        Returns:
            True if successful, False otherwise
        """
        webhook_url = webhook or self.config.daisy_webhook

        try:
            payload = {
                'embeds': [{
                    'title': title,
                    'color': color
                }]
            }

            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"Sent Discord notification: {title}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    def notify_download_started(self, name: str) -> bool:
        """Notify that a download has started."""
        return self.send_embed(
            f"Download of {name} started",
            color=65436  # Green
        )

    def notify_download_completed(self, name: str) -> bool:
        """Notify that a download has completed."""
        return self.send_embed(
            f"Download of {name} completed",
            color=65436  # Green
        )

    def notify_download_failed(self, name: str, reason: str = "") -> bool:
        """Notify that a download has failed."""
        title = f"Download failed: {name}"
        if reason:
            title += f" - {reason}"

        return self.send_embed(
            title,
            color=16711680  # Red
        )

    def notify_no_magnet_found(self, link: str) -> bool:
        """Notify that no magnet link could be found."""
        return self.send_embed(
            f"Could not find magnets for {link}",
            color=16711680  # Red
        )

    def notify_storage_status(self, storage_report: dict) -> bool:
        """
        Send storage status notification.

        Args:
            storage_report: Dict with 'movies' and 'other' drive info

        Returns:
            True if successful, False otherwise
        """
        movies = storage_report.get('movies', {})
        other = storage_report.get('other', {})

        title = (
            f"Free space:\n"
            f"Shows - {other.get('free_gb', 0)}/{other.get('capacity_gb', 0)} GB\n"
            f"Movies - {movies.get('free_gb', 0)}/{movies.get('capacity_gb', 0)} GB"
        )

        return self.send_embed(
            title,
            color=65436,
            webhook=self.config.storage_webhook
        )
