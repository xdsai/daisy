"""
Daisy - Automated torrent download and media management system.

Integrates with qBittorrent, Plex Media Server, and Discord.
"""

import logging
import sys
import argparse

from config import Config
from media_processor import MediaProcessor


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        filename='dlog',
        filemode='a',
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO
    )


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Daisy torrent downloader and media organizer"
    )
    parser.add_argument(
        '-t', '--type',
        required=True,
        type=str,
        choices=['movie', 'show', 'other'],
        help='Type of media (movie, show, or other)'
    )
    parser.add_argument(
        '-n', '--name',
        required=True,
        type=str,
        help='Name of the show or movie'
    )
    parser.add_argument(
        '-m', '--magnet',
        required=True,
        type=str,
        help='Magnet link or URL to download'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("------------------NEW TORRENT------------------")

    # Parse arguments
    try:
        args = parse_arguments()
    except SystemExit:
        logger.error("Invalid arguments provided")
        return 1

    logger.info(
        f"Parsed args - type: {args.type}, name: {args.name}, "
        f"link: {args.magnet[:60]}..."
    )

    # Load configuration
    try:
        config = Config.load()
        logger.info("Configuration loaded")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1

    # Initialize processor
    try:
        processor = MediaProcessor(config)
        logger.info("Media processor initialized")
    except Exception as e:
        logger.error(f"Failed to initialize media processor: {e}")
        return 1

    # Connect to qBittorrent
    if not processor.connect():
        logger.error("Failed to connect to qBittorrent")
        return 1

    # Process the download
    try:
        success = processor.process(
            torrent_type=args.type,
            show_name=args.name,
            link=args.magnet
        )

        if success:
            logger.info("Processing completed successfully")
            return 0
        else:
            logger.error("Processing failed")
            return 1

    except Exception as e:
        logger.error(f"Exception during processing: {e}", exc_info=True)
        return 1

    finally:
        processor.cleanup()


if __name__ == '__main__':
    sys.exit(main())
