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
        webhook: Optional[str] = None,
        fields: Optional[list] = None,
    ) -> bool:
        """
        Send an embed message to Discord.

        Args:
            title: Message title
            color: Embed color (default green)
            webhook: Webhook URL (defaults to daisy_webhook)
            fields: Optional list of {name, value, inline} dicts for embed fields

        Returns:
            True if successful, False otherwise
        """
        webhook_url = webhook or self.config.daisy_webhook

        try:
            embed = {'title': title, 'color': color}
            if fields:
                embed['fields'] = fields
            payload = {'embeds': [embed]}

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

    def notify_download_completed(
        self,
        name: str,
        storage_report: Optional[dict] = None,
    ) -> bool:
        """
        Notify that a download has completed. Bundles the storage report
        into the same embed when provided.
        """
        fields = None
        if storage_report:
            movies = storage_report.get('movies', {})
            other = storage_report.get('other', {})
            fields = [
                {
                    'name': 'Shows',
                    'value': f"{other.get('free_gb', 0)} / {other.get('capacity_gb', 0)} GB free",
                    'inline': True,
                },
                {
                    'name': 'Movies',
                    'value': f"{movies.get('free_gb', 0)} / {movies.get('capacity_gb', 0)} GB free",
                    'inline': True,
                },
            ]
        return self.send_embed(
            f"Download of {name} completed",
            color=65436,  # Green
            fields=fields,
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

