"""
Media processor module - orchestrates downloads and organization.
"""

import os
import re
import logging
import subprocess
from typing import Optional

from config import Config
from magnet_converters import MagnetConverter
from download_manager import DownloadManager
from file_operations import FileOperations
from jellyfin_manager import JellyfinManager
from notifications import DiscordNotifier


logger = logging.getLogger(__name__)


class MediaProcessor:
    """Orchestrates media download and organization workflow."""

    def __init__(self, config: Config):
        self.config = config
        self.magnet_converter = MagnetConverter()
        self.download_manager = DownloadManager(config.qbittorrent)
        self.file_ops = FileOperations(config.storage)
        self.media_server = JellyfinManager(config.jellyfin)
        self.notifier = DiscordNotifier(config.discord)

    def connect(self) -> bool:
        """Connect to required services."""
        return self.download_manager.connect()

    def process(
        self,
        torrent_type: str,
        show_name: str,
        link: str
    ) -> bool:
        """
        Process a torrent download request.

        Args:
            torrent_type: 'movie', 'show', or 'other'
            show_name: Name of the show/movie
            link: URL or magnet link

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Processing {torrent_type}: {show_name} from {link[:60]}")

        # Convert to magnet links
        magnets = self.magnet_converter.convert(link)

        if not magnets:
            logger.error("Could not find magnet links")
            self.notifier.notify_no_magnet_found(link)
            return False

        logger.info(f"Found {len(magnets)} magnet link(s)")

        # Process based on type
        if torrent_type == 'movie':
            success = self._process_movie(magnets)
        else:
            success = self._process_show(magnets, show_name, torrent_type)

        # Send storage status update
        storage_report = self.file_ops.get_storage_report()
        self.notifier.notify_storage_status(storage_report)

        return success

    def _process_movie(self, magnets: list) -> bool:
        """
        Process movie download(s).

        Args:
            magnets: List of magnet links

        Returns:
            True if all successful, False otherwise
        """
        logger.info("Processing movie download")

        storage = self.config.storage
        success_count = 0

        for magnet in magnets:
            torrent_info = self.download_manager.download(
                magnet,
                storage.movies_docker_path,
                on_started_callback=self.notifier.notify_download_started
            )

            if not torrent_info or torrent_info.get('content_path') == '':
                logger.error("Download failed")
                continue

            # Get the actual file system path (remove docker prefix)
            content_path = torrent_info['content_path']
            save_path = re.sub(
                storage.movies_docker_path,
                storage.movies_temp_path,
                content_path
            )

            logger.info(f"Downloaded to: {save_path}")

            # Organize the files
            if os.path.isdir(save_path):
                dest_video = self._organize_movie_directory(save_path, storage.movies_dir)
            else:
                dest_video = self._organize_movie_file(save_path, storage.movies_dir)

            # Sync any subtitles matching this video
            if dest_video:
                video_base = os.path.splitext(dest_video)[0]
                video_dir = os.path.dirname(dest_video)
                for f in os.listdir(video_dir):
                    if f.endswith(('.srt', '.ass', '.ssa', '.sub', '.vtt')) and not f.endswith('.bak'):
                        full = os.path.join(video_dir, f)
                        if os.path.splitext(f)[0].startswith(os.path.basename(video_base)):
                            self._sync_subtitles(full)

            # Update library, auto-download subtitles, and notify
            self.media_server.update_library()

            if dest_video:
                self._auto_subtitle(dest_video)

            self.notifier.notify_download_completed(torrent_info['name'])
            success_count += 1

        return success_count == len(magnets)

    def _organize_movie_directory(self, source_dir: str, dest_dir: str) -> Optional[str]:
        """Organize movie from a directory download. Returns dest video path or None."""
        try:
            video_file = self.file_ops.find_video_file(source_dir)
            if not video_file:
                logger.error("No video file found in directory")
                return None

            # Move video file
            src_video = f"{source_dir}/{video_file}"
            dst_video = f"{dest_dir}{video_file}"
            logger.info(f"Moving video: {src_video} -> {dst_video}")
            os.rename(src_video, dst_video)

            # Move subtitle if present
            subtitle_file = self.file_ops.find_subtitle_file(source_dir)
            if subtitle_file:
                video_name_no_ext = video_file[:-4]
                src_sub = f"{source_dir}/{subtitle_file}"
                dst_sub = f"{dest_dir}{video_name_no_ext}.srt"
                logger.info(f"Moving subtitle: {src_sub} -> {dst_sub}")
                os.rename(src_sub, dst_sub)

            # Remove temp directory
            import shutil
            logger.info(f"Removing temp directory: {source_dir}")
            shutil.rmtree(source_dir)

            return dst_video
        except Exception as e:
            logger.error(f"Failed to organize movie directory: {e}")
            return None

    def _organize_movie_file(self, source_file: str, dest_dir: str) -> Optional[str]:
        """Organize a single movie file. Returns dest video path or None."""
        try:
            filename = os.path.basename(source_file)
            dst = f"{dest_dir}{filename}"
            logger.info(f"Moving file: {source_file} -> {dst}")
            os.rename(source_file, dst)
            return dst
        except Exception as e:
            logger.error(f"Failed to organize movie file: {e}")
            return None

    def _process_show(
        self,
        magnets: list,
        show_name: str,
        torrent_type: str
    ) -> bool:
        """
        Process show/other download(s).

        Args:
            magnets: List of magnet links
            show_name: Name of the show
            torrent_type: 'show' or 'other'

        Returns:
            True if all successful, False otherwise
        """
        logger.info(f"Processing show download: {show_name}")

        storage = self.config.storage
        success_count = 0

        for magnet in magnets:
            torrent_info = self.download_manager.download(
                magnet,
                storage.other_docker_path,
                on_started_callback=self.notifier.notify_download_started
            )

            if not torrent_info or torrent_info.get('content_path') == '':
                logger.error("Download failed")
                continue

            # Get actual file system path
            content_path = torrent_info['content_path']
            save_path = re.sub(
                storage.other_docker_path,
                storage.other_temp_path,
                content_path
            )

            logger.info(f"Downloaded to: {save_path}")

            # Organize based on whether it's a directory or file
            if os.path.isdir(save_path):
                dest_path = self._organize_show_directory(
                    save_path,
                    show_name,
                    torrent_type
                )
            else:
                dest_path = self._organize_show_file(
                    save_path,
                    show_name,
                    torrent_type
                )

            if dest_path:
                # Sync subtitles before updating library
                self._sync_subtitles(dest_path)
                self.media_server.update_library()
                self.notifier.notify_download_completed(torrent_info['name'])
                success_count += 1

        return success_count == len(magnets)

    def _organize_show_directory(
        self,
        source_dir: str,
        show_name: str,
        torrent_type: str
    ) -> Optional[str]:
        """Organize show from a directory download. Returns dest dir path or None."""
        try:
            storage = self.config.storage
            normalized_name = self.file_ops.normalize_name(show_name)
            dest_dir = f"{storage.other_path}/{normalized_name}"

            if os.path.exists(dest_dir):
                # Show directory exists, move files into it
                logger.info(f"Show directory exists: {dest_dir}")
                for filename in os.listdir(source_dir):
                    src = f"{source_dir}/{filename}"
                    dst = f"{dest_dir}/{filename}"
                    logger.info(f"Moving: {src} -> {dst}")
                    os.rename(src, dst)

                # Remove temp directory
                import shutil
                shutil.rmtree(source_dir)
            else:
                # Create new show directory
                logger.info(f"Creating new show directory: {dest_dir}")
                self.file_ops.chown_to_user(source_dir)
                os.rename(source_dir, dest_dir)
                os.chmod(dest_dir, 0o777)

            return dest_dir
        except Exception as e:
            logger.error(f"Failed to organize show directory: {e}")
            return None

    def _organize_show_file(
        self,
        source_file: str,
        show_name: str,
        torrent_type: str
    ) -> Optional[str]:
        """Organize a single show file. Returns dest dir path or None."""
        try:
            storage = self.config.storage
            filename = os.path.basename(source_file)
            season = None

            # Check if it's a SubsPlease file
            subsplease_info = self.file_ops.extract_subsplease_info(filename)
            if subsplease_info:
                extracted_name, normalized_name, season = subsplease_info
                show_name = extracted_name
            else:
                normalized_name = self.file_ops.normalize_name(show_name)

            dest_dir = f"{storage.other_path}/{normalized_name}"

            # Ensure show directory exists
            if not os.path.exists(dest_dir):
                logger.info(f"Creating directory: {dest_dir}")
                self.file_ops.ensure_directory(dest_dir)

            # If season detected, organize into Season subdirectory
            if season is not None:
                season_dir = f"{dest_dir}/Season {season}"
                if not os.path.exists(season_dir):
                    logger.info(f"Creating season directory: {season_dir}")
                    self.file_ops.ensure_directory(season_dir)
                dest_dir = season_dir

            # Move the file
            self.file_ops.chown_to_user(source_file)
            dst = f"{dest_dir}/{filename}"
            logger.info(f"Moving: {source_file} -> {dst}")
            os.rename(source_file, dst)

            return dest_dir
        except Exception as e:
            logger.error(f"Failed to organize show file: {e}")
            return None

    def _auto_subtitle(self, video_path: str):
        """
        Auto-download subtitles for a movie via Jellyfin, then sync timing.
        Waits for Jellyfin to scan the file, searches for subs, downloads the best one,
        and runs jf-subsync on it.
        """
        logger.info(f"Auto-subtitle: looking up {video_path} in Jellyfin")
        item_id = self.media_server.find_item_by_path(video_path)
        if not item_id:
            logger.warning(f"Auto-subtitle: could not find item in Jellyfin, skipping")
            return

        if self.media_server.auto_download_subtitles(item_id):
            # Give Jellyfin a moment to write the subtitle file
            import time
            time.sleep(3)
            # Find and sync the new subtitle
            video_dir = os.path.dirname(video_path)
            video_base = os.path.splitext(os.path.basename(video_path))[0]
            for f in os.listdir(video_dir):
                if f.endswith(('.srt', '.ass', '.ssa', '.sub', '.vtt')) and not f.endswith('.bak'):
                    self._sync_subtitles(os.path.join(video_dir, f))
        else:
            logger.info(f"Auto-subtitle: no subtitles downloaded for {video_path}")

    def _sync_subtitles(self, path: str):
        """
        Find and sync all subtitle files at a given path using jf-subsync.

        Args:
            path: File or directory path to scan for subtitles
        """
        SUBSYNC = os.environ.get("JF_SUBSYNC_PATH", "jf-subsync")
        SUB_EXTS = ('.srt', '.ass', '.ssa', '.sub', '.vtt')

        sub_files = []
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in files:
                    if f.endswith(SUB_EXTS) and not f.endswith('.bak'):
                        sub_files.append(os.path.join(root, f))
        elif os.path.isfile(path) and path.endswith(SUB_EXTS):
            sub_files.append(path)

        for sub in sub_files:
            try:
                logger.info(f"Auto-syncing subtitle: {sub}")
                result = subprocess.run(
                    [SUBSYNC, sub],
                    capture_output=True, text=True, timeout=600
                )
                if result.returncode == 0:
                    logger.info(f"Subtitle synced: {sub}")
                else:
                    logger.warning(f"Subtitle sync failed for {sub}: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Subtitle sync timed out for {sub}")
            except Exception as e:
                logger.error(f"Subtitle sync error for {sub}: {e}")

    def cleanup(self):
        """Cleanup resources."""
        try:
            self.magnet_converter.close()
        except:
            pass
