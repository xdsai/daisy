"""
File operations module for organizing downloaded media files.
"""

import os
import re
import logging
import shutil
import subprocess
from typing import List, Optional, Tuple

from config import StorageConfig


logger = logging.getLogger(__name__)


class FileOperations:
    """Handles file system operations for media organization."""

    def __init__(self, storage_config: StorageConfig):
        self.storage = storage_config

    def get_free_space_gb(self, path: str) -> float:
        """Get free space in GB for a given path."""
        try:
            usage = shutil.disk_usage(path)
            return round(usage.free / 1_000_000_000, 2)
        except Exception as e:
            logger.error(f"Failed to get free space for {path}: {e}")
            return 0.0

    def get_storage_report(self) -> dict:
        """Get storage report for all drives."""
        return {
            'movies': {
                'free_gb': self.get_free_space_gb(self.storage.movies_path),
                'capacity_gb': self.storage.movies_capacity_gb,
            },
            'other': {
                'free_gb': self.get_free_space_gb(self.storage.other_path),
                'capacity_gb': self.storage.other_capacity_gb,
            }
        }

    def normalize_name(self, name: str) -> str:
        """Normalize a show/movie name by replacing spaces with underscores and lowercasing."""
        return re.sub(' ', '_', name).lower()

    def find_video_file(self, directory: str) -> Optional[str]:
        """
        Find the first video file in a directory.

        Args:
            directory: Path to search

        Returns:
            Filename of video file, or None if not found
        """
        if not os.path.isdir(directory):
            return None

        video_extensions = ('.mkv', '.mp4', '.avi')
        for filename in os.listdir(directory):
            if filename.endswith(video_extensions):
                logger.info(f"Found video file: {filename}")
                return filename

        logger.warning(f"No video file found in {directory}")
        return None

    def find_subtitle_file(self, directory: str) -> Optional[str]:
        """
        Find the first subtitle file in a directory.

        Args:
            directory: Path to search

        Returns:
            Filename of subtitle file, or None if not found
        """
        if not os.path.isdir(directory):
            return None

        for filename in os.listdir(directory):
            if filename.endswith('.srt'):
                logger.info(f"Found subtitle file: {filename}")
                return filename

        return None

    def extract_subsplease_info(self, filename: str) -> Optional[Tuple[str, str]]:
        """
        Extract show name from SubsPlease filename.

        Args:
            filename: SubsPlease filename (e.g., "[SubsPlease] Show Name - 01 (1080p)")

        Returns:
            Tuple of (show_name, normalized_name) or None if not a SubsPlease file
        """
        if '[SubsPlease]' not in filename:
            return None

        try:
            match = re.search(r'\] (.*) - (\d*)', filename)
            if match:
                show_name = match.group(1)
                normalized_name = self.normalize_name(show_name)
                logger.info(f"Extracted SubsPlease info: {show_name} -> {normalized_name}")
                return show_name, normalized_name
        except Exception as e:
            logger.error(f"Failed to extract SubsPlease info from {filename}: {e}")

        return None

    def chown_to_alex(self, path: str) -> bool:
        """
        Change ownership of a file/directory to alex:alex using sudo.

        Args:
            path: Path to change ownership

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Changing ownership to alex:alex: {path}")
            subprocess.call(["sudo", "chown", "alex:alex", path])
            return True
        except Exception as e:
            logger.error(f"Failed to chown {path}: {e}")
            return False

    def ensure_directory(self, path: str, mode: int = 0o777) -> bool:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path
            mode: Permissions mode (default 0o777)

        Returns:
            True if directory exists/created, False on error
        """
        try:
            if os.path.exists(path):
                logger.info(f"Directory already exists: {path}")
                return True

            logger.info(f"Creating directory: {path}")
            os.mkdir(path)
            os.chmod(path, mode)
            logger.info(f"Created directory with mode {oct(mode)}: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            return False

    def move_movie_files(
        self,
        temp_path: str,
        dest_path: str,
        docker_prefix: str
    ) -> bool:
        """
        Move movie files from temp directory to destination.

        Args:
            temp_path: Temporary download path
            dest_path: Destination directory path
            docker_prefix: Docker path prefix to remove from paths

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert docker path to actual path
            save_path = re.sub(docker_prefix, temp_path, temp_path)

            if os.path.isdir(save_path):
                logger.info(f"Processing directory: {save_path}")

                # Find and move video file
                video_file = self.find_video_file(save_path)
                if video_file:
                    src = f"{save_path}/{video_file}"
                    dst = f"{dest_path}{video_file}"
                    logger.info(f"Moving video: {src} -> {dst}")
                    os.rename(src, dst)

                    # Move subtitle file if exists (rename to match video)
                    subtitle_file = self.find_subtitle_file(save_path)
                    if subtitle_file:
                        video_name_no_ext = video_file[:-4]  # Remove extension
                        src_sub = f"{save_path}/{subtitle_file}"
                        dst_sub = f"{dest_path}{video_name_no_ext}.srt"
                        logger.info(f"Moving subtitle: {src_sub} -> {dst_sub}")
                        os.rename(src_sub, dst_sub)

                    # Remove temp directory
                    logger.info(f"Removing temp directory: {save_path}")
                    shutil.rmtree(save_path)
                else:
                    logger.warning("No video file found in directory")
                    return False
            else:
                # Single file, just move it
                logger.info(f"Moving file: {save_path} -> {dest_path}")
                filename = os.path.basename(save_path)
                os.rename(save_path, f"{dest_path}{filename}")

            return True
        except Exception as e:
            logger.error(f"Failed to move movie files: {e}")
            return False

    def move_show_files(
        self,
        temp_path: str,
        show_name: str,
        dest_base_path: str
    ) -> bool:
        """
        Move show files from temp directory to organized show directory.

        Args:
            temp_path: Path to downloaded content (may be file or directory)
            show_name: Name of the show
            dest_base_path: Base path for shows (e.g., /home/alex/hdd1a/)

        Returns:
            True if successful, False otherwise
        """
        try:
            normalized_name = self.normalize_name(show_name)
            dest_dir = f"{dest_base_path}{normalized_name}"

            logger.info(f"Moving show files to: {dest_dir}")

            # Ensure destination directory exists
            self.ensure_directory(dest_dir)

            if os.path.isdir(temp_path):
                # Directory of files - move each file
                if os.path.exists(dest_dir):
                    logger.info(f"Show directory exists, moving files into it")
                    files = os.listdir(temp_path)
                    for filename in files:
                        src = f"{temp_path}/{filename}"
                        dst = f"{dest_dir}/{filename}"
                        logger.info(f"Moving: {src} -> {dst}")
                        os.rename(src, dst)

                    # Remove empty temp directory
                    logger.info(f"Removing temp directory: {temp_path}")
                    shutil.rmtree(temp_path)
                else:
                    # Directory doesn't exist, rename temp to dest
                    self.chown_to_alex(temp_path)
                    logger.info(f"Renaming: {temp_path} -> {dest_dir}")
                    os.rename(temp_path, dest_dir)
                    os.chmod(dest_dir, 0o777)
            else:
                # Single file - move into show directory
                self.chown_to_alex(temp_path)
                filename = os.path.basename(temp_path)
                dst = f"{dest_dir}/{filename}"
                logger.info(f"Moving file: {temp_path} -> {dst}")
                os.rename(temp_path, dst)

            return True
        except Exception as e:
            logger.error(f"Failed to move show files: {e}")
            return False
