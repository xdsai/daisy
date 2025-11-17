"""
Configuration management for Daisy torrent downloader.
"""

import os
import json
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class QBittorrentConfig:
    """qBittorrent client configuration."""
    host: str = "192.168.0.101"
    port: int = 8080
    username: str = "xdsai"
    password: str = "admins"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"


@dataclass
class PlexConfig:
    """Plex server configuration."""
    host: str = "192.168.0.101"
    port: int = 32400
    token: str = "iUZBWnFpHhsfMoTFjPAk"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class DiscordConfig:
    """Discord webhook configuration."""
    daisy_webhook: str = "https://discord.com/api/webhooks/993897033259810946/7mDq6-TXPL5BPM7n0zsAnUlMzdtXJQBCinRsyCQZzJ4GwIxM3CfjqUdiIP-Y6P1LCKSZ"
    storage_webhook: str = "https://discord.com/api/webhooks/1079119240986107976/d6GsHCrHSHTVqLIWT71pISSUQHHxmzt6nFXHo4Kz5zQZVg-mVo3uI3j7raCjtb9leJpi"


@dataclass
class StorageConfig:
    """Storage drive configuration."""
    movies_path: str = "/home/alex/hdd5a"
    movies_temp_path: str = "/home/alex/hdd5a/temp/"
    movies_docker_path: str = "/movies/temp/"
    movies_capacity_gb: int = 465

    other_path: str = "/home/alex/hdd1a"
    other_temp_path: str = "/home/alex/hdd1a/temp/"
    other_docker_path: str = "/other/temp/"
    other_plex_path: str = "/app/hdd1a/"
    other_capacity_gb: int = 931

    @property
    def movies_dir(self) -> str:
        return f"{self.movies_path}/movies/"


@dataclass
class Config:
    """Main configuration container."""
    qbittorrent: QBittorrentConfig
    plex: PlexConfig
    discord: DiscordConfig
    storage: StorageConfig

    @classmethod
    def load(cls, config_file: str = "config.json") -> "Config":
        """Load configuration from file, or use defaults."""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                data = json.load(f)
                return cls(
                    qbittorrent=QBittorrentConfig(**data.get('qbittorrent', {})),
                    plex=PlexConfig(**data.get('plex', {})),
                    discord=DiscordConfig(**data.get('discord', {})),
                    storage=StorageConfig(**data.get('storage', {}))
                )
        else:
            # Use defaults
            return cls(
                qbittorrent=QBittorrentConfig(),
                plex=PlexConfig(),
                discord=DiscordConfig(),
                storage=StorageConfig()
            )

    def save(self, config_file: str = "config.json") -> None:
        """Save configuration to file."""
        data = {
            'qbittorrent': {
                'host': self.qbittorrent.host,
                'port': self.qbittorrent.port,
                'username': self.qbittorrent.username,
                'password': self.qbittorrent.password,
            },
            'plex': {
                'host': self.plex.host,
                'port': self.plex.port,
                'token': self.plex.token,
            },
            'discord': {
                'daisy_webhook': self.discord.daisy_webhook,
                'storage_webhook': self.discord.storage_webhook,
            },
            'storage': {
                'movies_path': self.storage.movies_path,
                'movies_temp_path': self.storage.movies_temp_path,
                'movies_docker_path': self.storage.movies_docker_path,
                'movies_capacity_gb': self.storage.movies_capacity_gb,
                'other_path': self.storage.other_path,
                'other_temp_path': self.storage.other_temp_path,
                'other_docker_path': self.storage.other_docker_path,
                'other_plex_path': self.storage.other_plex_path,
                'other_capacity_gb': self.storage.other_capacity_gb,
            }
        }
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)


# User agent for web scraping
USER_AGENT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
}
