# Daisy - Automated Torrent Downloader & Media Manager

Automated torrent download and media management system that integrates with qBittorrent, Plex Media Server, and Discord.

## Features

- **Automated Downloads**: Monitor SubsPlease RSS feed for new anime releases
- **Manual Downloads**: Trigger downloads via SSH from Windows clients
- **Multi-Site Support**: Convert URLs to magnet links from:
  - 1337x.to
  - nyaa.si
  - ext.to (with JavaScript rendering support)
  - subsplease.org
- **Smart Organization**: Automatically organize movies and TV shows
- **Plex Integration**: Auto-update libraries and create new sections
- **Discord Notifications**: Real-time status updates via webhooks
- **Storage Monitoring**: Track free space across multiple drives

## Architecture

The codebase has been refactored into modular components:

```
daisy/
├── config.py              # Configuration management
├── magnet_converters.py   # URL to magnet link conversion
├── download_manager.py    # qBittorrent operations
├── file_operations.py     # File organization and management
├── plex_manager.py        # Plex Media Server integration
├── notifications.py       # Discord webhook notifications
├── media_processor.py     # Main orchestration logic
├── daisy.py              # Main entry point
└── autodl.py             # Automated download daemon
```

## Configuration

### Using config.json (Optional)

Create a `config.json` file to override default settings:

```json
{
  "qbittorrent": {
    "host": "192.168.0.101",
    "port": 8080,
    "username": "your_username",
    "password": "your_password"
  },
  "plex": {
    "host": "192.168.0.101",
    "port": 32400,
    "token": "your_plex_token"
  },
  "discord": {
    "daisy_webhook": "your_webhook_url",
    "storage_webhook": "your_storage_webhook_url"
  },
  "storage": {
    "movies_path": "/home/alex/hdd5a",
    "other_path": "/home/alex/hdd1a"
  }
}
```

### Using defaults

If no `config.json` exists, the system uses hardcoded defaults from the original configuration.

## Usage

### Manual Download

```bash
python3 daisy.py -t <type> -n <name> -m <magnet_or_url>
```

**Arguments:**
- `-t, --type`: Media type (`movie`, `show`, or `other`)
- `-n, --name`: Name of the show/movie
- `-m, --magnet`: Magnet link or torrent site URL

**Examples:**

```bash
# Download a movie
python3 daisy.py -t movie -n "Example Movie" -m "https://1337x.to/torrent/..."

# Download a show
python3 daisy.py -t show -n "Example Show" -m "magnet:?xt=..."

# Download from SubsPlease
python3 daisy.py -t other -n "Anime Name" -m "https://subsplease.org/shows/..."
```

### Automated Downloads

The `autodl.py` daemon continuously monitors SubsPlease RSS feed:

```bash
python3 autodl.py
```

Configure queries in `autodl_queries.json`:

```json
["chainsaw man", "blue lock", "mob psycho 100 s3"]
```

Downloaded shows are tracked in `downloaded.json` to prevent duplicates.

### Windows Client

Use `daisy_win.py` or `windl.py` to trigger downloads from Windows via SSH:

```bash
python daisy_win.py
```

Update the SSH credentials in the file before use.

## Refactoring Changes

### Bug Fixes

1. **ext.to magnet converter**: Now uses JavaScript rendering to handle dynamic content
2. **Plex POST failures**: Proper URL encoding prevents failures with special characters in show names
3. **Date format in autodl**: Fixed invalid date format string

### Code Improvements

1. **Modular Design**: Separated concerns into dedicated modules
2. **Configuration Management**: Centralized config with support for external config file
3. **Error Handling**: Improved error handling and logging throughout
4. **Code Reusability**: Eliminated duplicate code (e.g., Plex POST requests)
5. **Type Hints**: Added type hints for better code documentation
6. **Logging**: Consistent logging across all modules
7. **Maintainability**: Reduced 200+ line function to organized, single-responsibility classes

### Backward Compatibility

- Original files backed up as `daisy_old.py` and `autodl_old.py`
- Shell script (`daisy_shell.sh`) unchanged
- Command-line arguments unchanged
- Log files (`dlog`, `alog`) unchanged
- Windows clients work without modification

## Storage Organization

### Movies
- **Path**: `/home/alex/hdd5a/movies/`
- **Temp**: `/home/alex/hdd5a/temp/`
- **Capacity**: 465 GB

### Shows/Other
- **Path**: `/home/alex/hdd1a/`
- **Temp**: `/home/alex/hdd1a/temp/`
- **Capacity**: 931 GB
- **Plex Path**: `/app/hdd1a/`

## Dependencies

```
beautifulsoup4==4.11.2
feedparser==6.0.10
PlexAPI==4.13.1
python_qbittorrent==0.4.3
qbittorrent==0.1.6
requests==2.25.1
requests_html==0.10.0
```

Install with:
```bash
pip install -r requirements.txt
```

## Logging

- **daisy.py**: Logs to `dlog`
- **autodl.py**: Logs to `alog`

## Development

### Running Tests

(Add test instructions here when tests are created)

### Adding New Torrent Sites

To add support for a new site, update `magnet_converters.py`:

```python
def _convert_newsite(self, link: str) -> List[str]:
    """Convert newsite.com URLs to magnet links."""
    # Implementation here
    pass
```

Then add the site check in the `convert()` method.

## Troubleshooting

### qBittorrent Connection Failed
- Verify qBittorrent is running and accessible
- Check credentials in config
- Ensure Web UI is enabled in qBittorrent

### Plex Not Updating
- Verify Plex token is correct
- Check Plex server is accessible
- Review logs for specific error messages

### Downloads Not Starting
- Check magnet link is valid
- Verify sufficient disk space
- Review qBittorrent logs

### ext.to Not Working
- Ensure `requests_html` is installed
- Check if Chrome/Chromium is available for rendering
- Site may be blocking automated access

## License

Personal project - use at your own discretion.

## Credits

Original author: xdsai
Refactored: 2025
