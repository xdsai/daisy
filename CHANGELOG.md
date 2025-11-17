# Changelog

## [API & Search Update] - 2025

### Added - Major Features
- **🔍 Torrent Search Engine** (`torrent_search.py`)
  - Search multiple torrent indexes (nyaa.si, 1337x.to)
  - Smart ranking by seeders, quality, and trusted uploaders
  - Auto-detect anime vs general media
  - Extract metadata: seeders, leechers, file size, quality, uploader
  - Score-based result ranking (seeders × 10 + quality bonuses)

- **📱 HTTP API Server** (`api_server.py`)
  - RESTful API for remote control
  - iOS Shortcuts support
  - API key authentication
  - Endpoints:
    - `GET/POST /search` - Search torrents with filters
    - `POST /download` - Download specific torrent
    - `POST /quick-download` - Auto-download best match
    - `GET /status` - Monitor active downloads
    - `GET /health` - Service health check
  - CORS enabled for web/mobile access

- **📖 iOS Shortcut Guide** (`iOS_SHORTCUT_GUIDE.md`)
  - Complete setup instructions for iOS Shortcuts
  - Interactive search & select workflow
  - Quick download shortcut
  - Siri integration examples
  - API reference documentation

### Dependencies
- Added `Flask==2.3.0` - Web framework
- Added `flask-cors==4.0.0` - CORS support

### User Experience Improvements
- **Before**: Manual torrent site search → copy magnet → SSH → paste
- **After**: Type query in iOS Shortcut → pick from ranked list → done
- Massive UX improvement for mobile downloads

## [Refactor 2025] - Modernization & Bug Fixes

### Added
- **Modular Architecture**: Separated code into dedicated modules
  - `config.py` - Configuration management with dataclasses
  - `magnet_converters.py` - Magnet link conversion logic
  - `download_manager.py` - qBittorrent client wrapper
  - `file_operations.py` - File system operations
  - `plex_manager.py` - Plex Media Server integration
  - `notifications.py` - Discord webhook notifications
  - `media_processor.py` - Main orchestration logic

- **Configuration System**: Support for external `config.json` file
- **Type Hints**: Added type annotations throughout
- **Error Handling**: Improved error handling and logging
- **Documentation**: Comprehensive README.md and inline documentation

### Fixed
- **ext.to magnet converter**: Now uses JavaScript rendering to handle dynamic page content
  - Uses `requests_html` session with rendering
  - Implements fallback to static parsing
  - Adds proper timeout handling

- **Plex POST failures**: Fixed URL encoding issues
  - Uses `urllib.parse.urlencode()` for proper encoding
  - Handles special characters in show names correctly
  - Added 409 status code handling (already exists)
  - Added timeout to Plex requests

- **autodl.py date format**: Fixed invalid date format string
  - Changed from `%YYYY-%MM-%DD-%H:%M:%S` to `%Y-%m-%d %H:%M:%S`

### Changed
- **Code Organization**: Reduced 200+ line `process()` function to organized classes
- **Eliminated Duplication**: Plex POST request code consolidated into single methods
- **Improved Logging**: Consistent logging patterns across all modules
- **Better Separation of Concerns**: Each module has single responsibility
- **Maintainability**: Easier to test, modify, and extend

### Backward Compatibility
- Original files backed up as `daisy_old.py` and `autodl_old.py`
- Command-line interface unchanged
- Log file formats unchanged
- Shell scripts work without modification
- Windows clients compatible

### Refactoring Details

#### Before
- Single 334-line monolithic script
- Hardcoded credentials throughout
- 4+ duplicate Plex POST request blocks
- Limited error handling
- No type hints
- Difficult to test or modify

#### After
- 7 focused modules with single responsibilities
- Centralized configuration management
- DRY principle applied (no duplication)
- Comprehensive error handling
- Type hints throughout
- Easy to test and extend

### Technical Debt Addressed
1. ✅ Configuration management
2. ✅ Code duplication
3. ✅ Mixed concerns
4. ✅ Poor modularity
5. ✅ Limited error handling
6. ✅ Lack of documentation
7. ✅ Hard-to-test code

### Known Limitations
- Requires all original dependencies
- Still uses `sudo chown` for file ownership changes
- Storage paths remain hardcoded in config defaults
- No automated tests yet

### Migration Guide

#### No Changes Required For:
- Existing shell scripts
- Windows clients (`daisy_win.py`, `windl.py`)
- Cron jobs or systemd services
- Log file locations

#### Optional Changes:
1. Create `config.json` to externalize configuration
2. Update any scripts that import from `daisy.py` directly
3. Review and adjust logging levels if needed

### Future Improvements
- [ ] Add unit tests
- [ ] Add retry logic with exponential backoff for network operations
- [ ] Support for additional torrent sites
- [ ] Web UI for monitoring
- [ ] Database for download history instead of JSON
- [ ] Remove sudo dependency for file operations
- [ ] Docker containerization
