# Daisy

Automated torrent downloader and media organizer. Searches multiple torrent indexes, downloads via qBittorrent, organizes files into your media library, syncs subtitles, and notifies you on Discord. Comes with an HTTP API for iOS Shortcuts integration and an RSS auto-downloader for anime.

## Features

- **Multi-site torrent search** — nyaa.si, 1337x.to, The Pirate Bay, with results ranked by seeders and quality
- **Smart file organization** — automatically sorts movies and shows into the right folders, handles SubsPlease naming conventions, season detection
- **Jellyfin integration** — triggers library refresh after every download, can create new libraries on the fly
- **Subtitle auto-sync** — runs [ffsubsync](https://github.com/smacke/ffsubsync) on subtitle files after download to fix timing
- **Discord notifications** — real-time updates for download started/completed/failed, plus storage status
- **HTTP API** — Flask server with search, download, quick-download, and status endpoints
- **iOS Shortcuts support** — designed to work with Apple Shortcuts for phone-based downloading
- **RSS auto-downloader** — monitors SubsPlease feed and automatically grabs new episodes of shows you're tracking
- **Magnet conversion** — converts URLs from 1337x, nyaa.si, ext.to, and SubsPlease show pages into magnet links

## Architecture

```
daisy/
├── config.py              # Configuration management
├── api_server.py          # HTTP API server
├── daisy.py               # CLI entry point
├── autodl.py              # RSS auto-download daemon
├── media_processor.py     # Download + organization orchestration
├── download_manager.py    # qBittorrent client
├── file_operations.py     # File organization and management
├── magnet_converters.py   # URL → magnet link conversion
├── torrent_search.py      # Multi-site search engine
├── jellyfin_manager.py    # Jellyfin API integration
├── notifications.py       # Discord webhooks
└── daisy_shell.sh         # Shell wrapper
```

## Setup

### Prerequisites

- Python 3.10+
- qBittorrent with Web UI enabled
- Jellyfin (optional, for library management)
- ffsubsync + [jf-subsync](https://github.com/smacke/ffsubsync) (optional, for subtitle auto-sync)

### Install

```bash
git clone https://github.com/xdsai/daisy.git
cd daisy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp config.example.json config.json
```

Edit `config.json` with your actual values:
- **qbittorrent** — host, port, and Web UI credentials
- **jellyfin** — host, port, and API key (generate one in Jellyfin dashboard → API Keys)
- **discord** — webhook URLs for download notifications and storage status
- **storage** — paths to your media directories and their temp folders

The `movies_docker_path` and `other_docker_path` fields are for when qBittorrent runs in Docker — they map the container's save path to your actual filesystem path. If qBittorrent runs natively, set these to match your temp paths.

## Usage

### API Server (recommended)

```bash
export DAISY_API_KEY="your-secret-key"
python3 api_server.py
```

Endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET/POST | `/search` | Search torrents (`q` param) |
| POST | `/download` | Download by magnet link |
| POST | `/quick-download` | Search + download best match |
| GET | `/status` | Active downloads + storage info |

All endpoints except `/health` require the API key via `X-API-Key` header or `api_key` query param.

**Search:**
```bash
curl "http://localhost:5000/search?q=movie+name&api_key=your-key"
```

**Download:**
```bash
curl -X POST http://localhost:5000/download \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"magnet": "magnet:?xt=...", "name": "Movie Name", "type": "movie"}'
```

**Quick download (search + grab best result):**
```bash
curl -X POST http://localhost:5000/quick-download \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "movie name", "type": "auto"}'
```

For iOS Shortcuts setup, see [iOS_SHORTCUT_GUIDE.md](iOS_SHORTCUT_GUIDE.md).

### CLI

```bash
python3 daisy.py -t movie -n "Movie Name" -m "magnet:?xt=..."
python3 daisy.py -t show -n "Show Name" -m "https://nyaa.si/view/12345"
python3 daisy.py -t other -n "Anime Name" -m "https://subsplease.org/shows/anime-name/"
```

### RSS Auto-downloader

```bash
python3 autodl.py
```

Add shows to `autodl_queries.json`:
```json
["show name one", "show name two"]
```

The daemon checks SubsPlease RSS every 20 minutes and triggers downloads for new matching episodes. Already-downloaded episodes are tracked in `downloaded.json`.

## How It Works

1. **Search/receive** a torrent link (via API, CLI, or RSS)
2. **Convert** URL to magnet link if needed (supports 1337x, nyaa, SubsPlease, ext.to)
3. **Download** via qBittorrent Web API, monitoring progress until completion
4. **Organize** — movies go to the movies folder, shows get their own directories with season subfolders
5. **Sync subtitles** — if subtitle files are present, run ffsubsync to fix timing against the video
6. **Update Jellyfin** — trigger a library refresh so new content appears immediately
7. **Notify** — send Discord embeds for download status and storage usage

## License

MIT
