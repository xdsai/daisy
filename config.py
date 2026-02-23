"""
Configuration management for Daisy torrent downloader.
"""

import os
import json
from dataclasses import dataclass


@dataclass
class QBittorrentConfig:
    """qBittorrent client configuration."""
    host: str = "127.0.0.1"
    port: int = 8080
    username: str = "admin"
    password: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"


@dataclass
class JellyfinConfig:
    """Jellyfin server configuration."""
    host: str = "127.0.0.1"
    port: int = 8096
    api_key: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class DiscordConfig:
    """Discord webhook configuration."""
    daisy_webhook: str = ""
    storage_webhook: str = ""


@dataclass
class StorageConfig:
    """Storage drive configuration."""
    movies_path: str = "/path/to/movies"
    movies_temp_path: str = "/path/to/movies/temp/"
    movies_docker_path: str = "/movies/temp/"
    movies_capacity_gb: int = 500

    other_path: str = "/path/to/shows"
    other_temp_path: str = "/path/to/shows/temp/"
    other_docker_path: str = "/other/temp/"
    other_jellyfin_path: str = "/path/to/shows/"
    other_capacity_gb: int = 500

    @property
    def movies_dir(self) -> str:
        return f"{self.movies_path}/movies/"


@dataclass
class Config:
    """Main configuration container."""
    qbittorrent: QBittorrentConfig
    jellyfin: JellyfinConfig
    discord: DiscordConfig
    storage: StorageConfig

    @classmethod
    def load(cls, config_file: str = "config.json") -> "Config":
        """Load configuration from file, or use defaults."""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                data = json.load(f)
                storage_data = data.get('storage', {})
                # Backwards compat: accept old "other_plex_path" key
                if 'other_plex_path' in storage_data and 'other_jellyfin_path' not in storage_data:
                    storage_data['other_jellyfin_path'] = storage_data.pop('other_plex_path')
                elif 'other_plex_path' in storage_data:
                    storage_data.pop('other_plex_path')
                return cls(
                    qbittorrent=QBittorrentConfig(**data.get('qbittorrent', {})),
                    jellyfin=JellyfinConfig(**data.get('jellyfin', {})),
                    discord=DiscordConfig(**data.get('discord', {})),
                    storage=StorageConfig(**storage_data)
                )
        else:
            return cls(
                qbittorrent=QBittorrentConfig(),
                jellyfin=JellyfinConfig(),
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
            'jellyfin': {
                'host': self.jellyfin.host,
                'port': self.jellyfin.port,
                'api_key': self.jellyfin.api_key,
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
                'other_jellyfin_path': self.storage.other_jellyfin_path,
                'other_capacity_gb': self.storage.other_capacity_gb,
            }
        }
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)


USER_AGENT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
}
