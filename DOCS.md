# Daisy -- Developer Documentation

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Components](#2-components)
3. [Data Flow](#3-data-flow)
4. [API Server](#4-api-server)
5. [AutoDL Daemon](#5-autodl-daemon)
6. [Configuration](#6-configuration)
7. [Storage Layout](#7-storage-layout)
8. [External Dependencies](#8-external-dependencies)
9. [Deployment](#9-deployment)

---

## 1. System Overview

Daisy is an automated torrent download and media management system designed to run on a Linux home server. It integrates with qBittorrent (running natively via `qbittorrent-nox`) to download torrents, organizes the resulting media files into a structured directory layout, registers new content with Jellyfin Media Server, and sends status notifications to Discord via webhooks.

> **Setup guide:** See [SETUP.md](SETUP.md) for step-by-step installation instructions suitable for handing to an AI agent.

### High-Level Architecture

```
                        +-----------------+
                        |  iOS Shortcut / |
                        |  Windows Client |
                        +--------+--------+
                                 |
              +------------------+------------------+
              |                  |                  |
              v                  v                  v
     +--------+-------+  +------+------+   +-------+-------+
     | CLI (daisy.py)  |  | API Server  |   | AutoDL Daemon |
     | (direct use)    |  | (Flask)     |   | (autodl.py)   |
     +--------+--------+  +------+------+   +-------+-------+
              |                  |                  |
              |                  |          (HTTP POST /download)
              |                  |                  |
              +------------------+------------------+
                                 |
                         +-------v--------+
                         | MediaProcessor |
                         | (orchestrator) |
                         +-------+--------+
                                 |
          +----------+-----------+-----------+----------+
          |          |           |           |          |
          v          v           v           v          v
   +------+---+ +---+----+ +---+-----+ +---+---+ +----+------+
   | Magnet   | |Download| | File    | |Jellyfin| | Discord   |
   |Converter | |Manager | | Ops     | |Manager| | Notifier  |
   +----------+ +--------+ +---------+ +-------+ +-----------+
       |            |           |          |           |
       v            v           v          v           v
   Torrent Sites  qBittorrent  Local FS   Jellyfin API   Discord
   (scraping)     (Web API)    (mv/chown) (HTTP)     Webhooks
```

### Codebase Generations

The repository contains three generations of code:

| Generation | Files | Description |
|---|---|---|
| **Legacy (v1)** | `daisy_old.py`, `autodl_old.py` | Monolithic single-file implementations. All logic in one file with inline configuration. |
| **Refactored (v2)** | `daisy_refactored.py`, `autodl_refactored.py` | Identical to the current active files; appear to be snapshots taken during the refactor. |
| **Current (v2)** | `daisy.py`, `autodl.py`, plus all modules | Modular architecture with separated concerns across dedicated modules. |

The current architecture splits responsibilities across eight Python modules described below.

---

## 2. Components

### 2.1 `config.py` -- Configuration Management

Defines all configuration as typed dataclasses with hardcoded defaults. Supports optional loading/saving to `config.json`.

**Classes:**

| Class | Purpose | Key Fields |
|---|---|---|
| `QBittorrentConfig` | qBittorrent WebUI connection | `host`, `port`, `username`, `password`; property `url` builds `http://host:port/` |
| `JellyfinConfig` | Jellyfin server connection | `host`, `port`, `api_key`; property `url` builds `http://host:port` |
| `DiscordConfig` | Discord webhook URLs | `daisy_webhook` (download events), `storage_webhook` (disk space reports) |
| `StorageConfig` | File system paths and capacities | `movies_path`, `movies_temp_path`, `movies_docker_path`, `movies_capacity_gb`, `other_path`, `other_temp_path`, `other_docker_path`, `other_jellyfin_path`, `other_capacity_gb`; property `movies_dir` returns `movies_path + "/movies/"` |
| `Config` | Top-level container aggregating all sub-configs | `qbittorrent`, `jellyfin`, `discord`, `storage` |

**Methods on `Config`:**

- `Config.load(config_file="config.json")` -- Class method. Reads JSON file if it exists; otherwise returns defaults.
- `Config.save(config_file="config.json")` -- Serializes all settings to JSON.

**Module-level constant:**

- `USER_AGENT` -- A Chrome user-agent string dict used for all web scraping requests.

---

### 2.2 `daisy.py` -- CLI Entry Point

The primary command-line interface. Parses arguments, loads config, instantiates `MediaProcessor`, connects to qBittorrent, and runs the full download-organize-notify pipeline synchronously.

**Functions:**

| Function | Description |
|---|---|
| `setup_logging()` | Configures `logging` to append to file `dlog` with `HH:MM:SS` timestamps at `INFO` level. |
| `parse_arguments()` | Defines argparse with three required arguments: `-t/--type` (choices: `movie`, `show`, `other`), `-n/--name`, `-m/--magnet`. |
| `main()` | Orchestration: parse args, load config, create `MediaProcessor`, connect, call `processor.process()`, call `processor.cleanup()`. Returns exit code 0 or 1. |

**Usage:**

```bash
python3 daisy.py -t movie -n "Movie Name" -m "magnet:?xt=urn:btih:..."
python3 daisy.py -t show -n "Show Name" -m "https://nyaa.si/view/12345"
python3 daisy.py -t other -n "autodl" -m "magnet:?xt=urn:btih:..."
```

---

### 2.3 `media_processor.py` -- Orchestrator

The central coordination module. It wires together all other modules and implements the business logic for processing downloads by type.

**Class: `MediaProcessor`**

Constructor takes a `Config` and instantiates:

- `self.magnet_converter` -- `MagnetConverter()`
- `self.download_manager` -- `DownloadManager(config.qbittorrent)`
- `self.file_ops` -- `FileOperations(config.storage)`
- `self.media_server` -- `JellyfinManager(config.jellyfin)`
- `self.notifier` -- `DiscordNotifier(config.discord)`

**Public methods:**

| Method | Description |
|---|---|
| `connect()` | Delegates to `download_manager.connect()`. Returns `bool`. |
| `process(torrent_type, show_name, link)` | Main pipeline. Converts link to magnets, dispatches to `_process_movie()` or `_process_show()`, sends storage report. Returns `bool`. |
| `cleanup()` | Calls `magnet_converter.close()` to shut down the HTMLSession. |

**Private methods:**

| Method | Description |
|---|---|
| `_process_movie(magnets)` | For each magnet: downloads to `movies_docker_path`, translates Docker path to host path, organizes file(s) into `movies_dir`, updates Plex library, notifies Discord. |
| `_process_show(magnets, show_name, torrent_type)` | For each magnet: downloads to `other_docker_path`, translates path, dispatches to directory or file organizer. |
| `_organize_movie_directory(source_dir, dest_dir)` | Finds the video file (and optional subtitle) in a directory, moves them to the movies folder, removes the temp directory. |
| `_organize_movie_file(source_file, dest_dir)` | Moves a single movie file to the destination. |
| `_organize_show_directory(source_dir, show_name, torrent_type)` | If a show directory already exists, merges files into it. Otherwise renames the temp dir to the normalized show name, sets permissions to 0o777, and creates a Plex library section. |
| `_organize_show_file(source_file, show_name, torrent_type)` | Handles single-file show downloads. Detects SubsPlease naming conventions to auto-extract show names. Creates the show directory and Plex section if needed, then moves the file. |

**Path translation:** When qBittorrent runs natively, `docker_path` and `temp_path` should be identical in config so `re.sub()` is a no-op. The path translation exists for backward compatibility with Docker-based qBittorrent deployments.

---

### 2.4 `magnet_converters.py` -- URL-to-Magnet Conversion

Converts torrent site URLs into magnet links. Supports direct magnet links (passthrough), multiple torrent sites, and a generic fallback.

**Class: `MagnetConverter`**

Uses `requests_html.HTMLSession` for JavaScript-rendered pages and `requests` + `BeautifulSoup` for static pages.

**Methods:**

| Method | Sites | Technique |
|---|---|---|
| `convert(link)` | All | Router. Detects site from URL, delegates to specialized method. Returns `List[str]`. |
| `_convert_1337x(link)` | 1337x.to | Static scraping with BeautifulSoup. Finds first `<a>` with `magnet:?xt=` href. |
| `_convert_nyaa(link)` | nyaa.si | Static scraping. Handles `.torrent` download URLs by converting `/download/ID.torrent` to `/view/ID` first. |
| `_convert_ext_to(link)` | ext.to | JavaScript rendering via `requests_html`. Falls back to static parsing if JS rendering finds nothing. |
| `_convert_subsplease(link)` | subsplease.org | JavaScript rendering. Collects all 1080p magnet links. Returns immediately if a "Batch" link is found; otherwise returns all individual episode links. Retries up to 5 times. |
| `_convert_generic(link)` | Any | Static scraping fallback. Searches for any `<a>` with a magnet href. |
| `close()` | -- | Shuts down the HTMLSession. |

**Key behavior:** SubsPlease conversion can return **multiple** magnet links (one per episode) unless a batch torrent is available. All other converters return a list of exactly one magnet or an empty list.

---

### 2.5 `download_manager.py` -- qBittorrent Interface

Manages the full lifecycle of a torrent download: adding, monitoring, and deleting torrents via the qBittorrent Web API.

**Class: `DownloadManager`**

Uses the `python-qbittorrent` library (`qbittorrent.Client`).

**Methods:**

| Method | Description |
|---|---|
| `connect()` | Authenticates with qBittorrent using username/password. Sets `self.connected`. |
| `download(magnet, save_path, timeout=120, on_started_callback=None)` | Full download lifecycle. Extracts infohash from the magnet URI (regex on `btih:`), calls `download_from_link()`, waits 5 seconds for the torrent to appear, verifies it matches by infohash, fires the `on_started_callback` (used for Discord notification), then delegates to `_monitor_download()`. Returns the torrent info dict or `None`. |
| `_monitor_download(torrent_info, torrent_name, metadata_timeout)` | Polls `client.torrents()` every 1 second until `amount_left == 0` and state is not `metaDL`. If the torrent stays in `metaDL` state for longer than `metadata_timeout` seconds (default 120), it deletes the torrent and returns `None`. |
| `_delete_torrent(infohash)` | Deletes a torrent by its v1 infohash. |
| `get_torrents()` | Returns the full list of torrents (used by the status API endpoint). |

**Important details:**
- The method finds the newly added torrent by fetching the most recently added torrent (`sort='added_on', reverse=True, limit=1`). If the infohash does not match, it falls back to scanning all torrents.
- Infohash extraction handles both hex-encoded (40 chars) and base32-encoded (32 chars, common in nyaa/SubsPlease magnets) hashes. Base32 hashes are decoded to hex for comparison with qBittorrent's `infohash_v1`.

---

### 2.6 `file_operations.py` -- File System Operations

Handles all file system manipulation: finding files, moving them, creating directories, changing ownership.

**Class: `FileOperations`**

| Method | Description |
|---|---|
| `get_free_space_gb(path)` | Returns free space in GB using `shutil.disk_usage()`. |
| `get_storage_report()` | Returns a dict with free/capacity for both movies and other drives. |
| `normalize_name(name)` | Replaces spaces with underscores, lowercases. Used for directory naming. |
| `find_video_file(directory)` | Scans directory for files ending in `.mkv`, `.mp4`, or `.avi`. Returns the first match. |
| `find_subtitle_file(directory)` | Scans directory for `.srt` files. Returns the first match. |
| `extract_subsplease_info(filename)` | Regex extracts show name from SubsPlease-formatted filenames like `[SubsPlease] Show Name - 01 (1080p) [HASH].mkv`. Returns `(show_name, normalized_name)` tuple. |
| `chown_to_user(path)` | Runs `sudo chown $USER:$USER <path>`. Needed because qBittorrent (in Docker) creates files owned by root. |
| `ensure_directory(path, mode=0o777)` | Creates a directory if it does not exist and sets permissions. |
| `move_movie_files(temp_path, dest_path, docker_prefix)` | Moves video (and optional subtitle) from temp to destination, removes temp dir. |
| `move_show_files(temp_path, show_name, dest_base_path)` | Creates or merges into a normalized show directory. Handles both directory and single-file downloads. |

---

### 2.7 `torrent_search.py` -- Multi-Source Torrent Search

Provides search functionality across multiple torrent indexes with result ranking. Used by the API server.

**Dataclass: `TorrentResult`**

Fields: `title`, `magnet`, `size`, `seeders`, `leechers`, `source`, `uploader`, `quality`.

| Method | Description |
|---|---|
| `to_dict(index=None)` | Serializes to dict for JSON. If `index` is provided, adds `index` and `display_text` fields (formatted for iOS Shortcuts list display). |
| `suggest_type()` | Heuristic media type detection. Returns `'other'` if title contains series indicators (season, batch, subsplease, etc.). Returns `'movie'` if title contains year in parentheses or quality indicators like bluray/webrip. Defaults to `'other'`. |
| `calculate_score()` | Ranking score. Formula: `seeders * 10` + quality bonus (1080p: +50, 720p: +30, 2160p/4K: +40) + trusted uploader bonus (+25). Score is zero if seeders == 0. Trusted uploaders: subsplease, eztv, yts, rarbg, ettv. |

**Class: `TorrentSearcher`**

| Method | Description |
|---|---|
| `search(query, media_type='auto', limit=20)` | Searches nyaa.si and TPB always; searches 1337x if fewer than 5 results. Filters by relevance, sorts by score descending, returns top `limit`. |
| `_search_nyaa(query)` | Searches nyaa.si via RSS feed. Parses `nyaa_seeders`, `nyaa_leechers`, `nyaa_size` attributes from feed entries. Extracts uploader from `[brackets]` in title. |
| `_search_tpb(query)` | Searches The Pirate Bay via `apibay.org` JSON API. Builds magnet links from info_hash, appends standard trackers. Filters out adult content by TPB category IDs (500-599) and keyword matching. |
| `_search_1337x(query, max_results=5)` | Scrapes 1337x.to search results page. Fetches individual detail pages to extract magnet links (capped at `max_results` to avoid slow page fetches). |
| `_filter_by_relevance(results, query)` | For multi-word queries, requires at least 70% of query words to appear in the title (normalized with dots replaced by spaces). Single-word queries skip filtering. |
| `_is_adult_content(title)` | Keyword-based adult content filter for TPB results. |
| `_format_size(size_bytes)` | Converts bytes to human-readable string (KiB/MiB/GiB/TiB). |

**Module-level convenience function:**

```python
def search_torrents(query, media_type='auto', limit=20) -> List[Dict]:
```

Creates a `TorrentSearcher`, runs `.search()`, returns results as a list of dicts with `index` fields added (for iOS Shortcuts integration).

---

### 2.8 `jellyfin_manager.py` -- Jellyfin Media Server Integration

Manages Jellyfin library refresh and virtual folder creation via REST API.

**Class: `JellyfinManager`**

Constructor takes a `JellyfinConfig` and sets up authorization headers using the API key.

| Method | Description |
|---|---|
| `update_library()` | Triggers a full library refresh via `POST /Library/Refresh`. Called after every successful download. Returns `bool`. |
| `create_show_section(name, location)` | Creates a new TV show virtual folder via `POST /Library/VirtualFolders`. |
| `create_movie_section(name, location)` | Creates a new movie virtual folder via `POST /Library/VirtualFolders`. |
| `_create_virtual_folder(name, collection_type, location)` | Internal method. POSTs to `/Library/VirtualFolders` with name, collectionType, and paths as query parameters. Handles 204 (created), 409 (exists). |
| `section_exists(name)` | Checks if a virtual folder with the given name exists via `GET /Library/VirtualFolders`. |

**Note:** Daisy originally supported Plex but has since migrated to Jellyfin.

---

### 2.9 Automatic Subtitle Sync (`_sync_subtitles` + `jf-subsync`)

After every successful download, Daisy automatically syncs any subtitle files to match their video's timing using `jf-subsync`, a shell wrapper around [ffsubsync](https://github.com/smacke/ffsubsync).

#### How It Works

1. `MediaProcessor._sync_subtitles(path)` scans the download path (file or directory) for subtitle files with extensions: `.srt`, `.ass`, `.ssa`, `.sub`, `.vtt` (skipping `.bak` backups).
2. For each subtitle found, it calls `jf-subsync <subtitle_file>` with a 10-minute timeout.
3. `jf-subsync` does the rest:
   - Resolves the subtitle to an absolute path.
   - Finds the matching video file in the same directory (tries exact name match, then without language suffix, then falls back to the first video file found).
   - Backs up the original subtitle as `<filename>.bak`.
   - Uses a lock file (`/tmp/subsync-locks/`) to prevent duplicate syncs on the same file.
   - Runs `ffsubsync` to retune the subtitle timing against the video's audio track, overwriting the original subtitle in place.

#### When It Runs

Subtitle sync is triggered automatically at two points in the pipeline:

- **Shows:** After organizing show files into their destination directory (`_process_show`), before the Jellyfin library refresh.
- **Movies:** After organizing movie files into the movies directory (`_organize_movie_directory`), before the Jellyfin library refresh.

#### Supported Subtitle Formats

`.srt`, `.ass`, `.ssa`, `.sub`, `.vtt`

#### Dependencies

- `ffsubsync` installed at `ffsubsync`
- `jf-subsync` wrapper at `jf-subsync`

#### Failure Handling

Subtitle sync failures (timeouts, errors, missing video files) are logged as warnings but **do not** block the download pipeline. The download still completes, the library still updates, and Discord notifications still fire.

---

### 2.10 `notifications.py` -- Discord Webhooks

Sends embed-style messages to Discord channels via webhooks.

**Class: `DiscordNotifier`**

| Method | Webhook | Color | Message |
|---|---|---|---|
| `send_embed(title, color=65436, webhook=None)` | Configurable (defaults to `daisy_webhook`) | Configurable | Generic embed sender. |
| `notify_download_started(name)` | `daisy_webhook` | Green (65436) | `"Download of {name} started"` |
| `notify_download_completed(name)` | `daisy_webhook` | Green (65436) | `"Download of {name} completed"` |
| `notify_download_failed(name, reason)` | `daisy_webhook` | Red (16711680) | `"Download failed: {name} - {reason}"` |
| `notify_no_magnet_found(link)` | `daisy_webhook` | Red (16711680) | `"Could not find magnets for {link}"` |
| `notify_storage_status(storage_report)` | `storage_webhook` | Green (65436) | Free space report for both drives. |

**Payload format:** Discord embed JSON:
```json
{
  "embeds": [{
    "title": "<message text>",
    "color": <integer color code>
  }]
}
```

---

### 2.11 `daisy_win.py` and `windl.py` -- Windows Remote Clients

Minimal interactive scripts that SSH into the server via `paramiko` and execute `daisy_shell.sh` remotely.

**`daisy_win.py`**: Prompts for magnet link, then type (`movie`/`other`), then name (if type is `other`). Auto-detects SubsPlease links and sets type to `other` with name `"subsplease"`. Quotes arguments in the remote command.

**`windl.py`**: Similar but different prompt order. Does not auto-detect SubsPlease. Does not quote arguments (older version).

Both connect to `192.168.0.101` via SSH. Username and password fields are left empty in the committed source.

---

### 2.12 `daisy_shell.sh` -- Shell Wrapper (Legacy)

```bash
cd ~/daisy
nohup python3 daisy.py -t "$1" -n "$2" -m "$3" >> dlog 2>&1 &
```

Runs `daisy.py` in the background with `nohup`. Positional arguments: `$1` = type, `$2` = name, `$3` = magnet. Appends stdout/stderr to `dlog`. **No longer used by autodl** (which now calls the API server directly). Still used by the legacy Windows remote clients.

---

## 3. Data Flow

### 3.1 Full Download Pipeline (CLI Path)

```
User runs: python3 daisy.py -t show -n "My Show" -m "https://nyaa.si/view/12345"

1. daisy.py
   |-- parse_arguments() -> type="show", name="My Show", magnet="https://..."
   |-- Config.load() -> loads config.json or uses defaults
   |-- MediaProcessor(config) -> instantiates all sub-modules
   |-- processor.connect() -> authenticates with qBittorrent WebUI
   |-- processor.process("show", "My Show", "https://nyaa.si/view/12345")

2. MediaProcessor.process()
   |-- magnet_converter.convert("https://nyaa.si/view/12345")
   |   |-- Detects "nyaa.si" in URL
   |   |-- _convert_nyaa() -> HTTP GET, BeautifulSoup, finds magnet href
   |   |-- Returns ["magnet:?xt=urn:btih:ABC123..."]
   |
   |-- type is "show", calls _process_show(magnets, "My Show", "show")

3. _process_show()
   |-- For each magnet:
   |   |-- download_manager.download(magnet, "/other/temp/", callback=notify_download_started)
   |   |   |-- Extracts infohash from magnet URI
   |   |   |-- qb.download_from_link(magnet, save_path="/other/temp/")
   |   |   |-- Waits 5s, finds torrent in queue by infohash
   |   |   |-- Calls notify_download_started(torrent_name)
   |   |   |   `-- Discord POST: "Download of {name} started" (green)
   |   |   |-- _monitor_download(): polls every 1s until amount_left == 0
   |   |   `-- Returns torrent_info dict (includes content_path)
   |   |
   |   |-- Translates Docker path: "/other/temp/MyFile" -> "/mnt/shows/temp/MyFile"
   |   |
   |   |-- _organize_show_file() or _organize_show_directory()
   |   |   |-- Normalizes name: "My Show" -> "my_show"
   |   |   |-- Creates /mnt/shows/my_show/ if needed (chmod 777)
   |   |   |-- Creates Jellyfin library section via HTTP POST
   |   |   |-- chown file to $USER:$USER (sudo)
   |   |   `-- os.rename() file into show directory
   |   |
   |   |-- jellyfin.update_library()
   |   `-- notifier.notify_download_completed(name)
   |       `-- Discord POST: "Download of {name} completed" (green)
   |
   |-- notifier.notify_storage_status(storage_report)
       `-- Discord POST to storage webhook: free space on both drives
```

### 3.2 API Server Path

```
iOS Shortcut -> POST /quick-download with JSON body

1. api_server.py receives request
   |-- require_api_key decorator validates X-API-Key header
   |-- Parses JSON: {query: "Chainsaw Man 05", type: "auto"}
   |
   |-- search_torrents(query, "auto", limit=10)
   |   |-- TorrentSearcher.search()
   |   |   |-- _search_nyaa() via RSS feed
   |   |   |-- _search_tpb() via apibay.org API
   |   |   |-- (optional) _search_1337x() if < 5 results
   |   |   |-- _filter_by_relevance()
   |   |   `-- Sort by score, return top 10
   |   `-- Returns list of dicts with index fields
   |
   |-- Selects result at index (default 0 = best match)
   |-- Resolves media_type from result's suggest_type() if "auto"
   |
   |-- Creates background thread:
   |   `-- media_processor.process(type, name, magnet)
   |       (same pipeline as CLI path above)
   |
   `-- Returns JSON immediately:
       {success: true, message: "Download started", selected_torrent: {...}}
```

### 3.3 AutoDL Daemon Path

```
autodl.py runs as a persistent daemon

Every 20 minutes:
  1. Load autodl_queries.json -> ["jujutsu kaisen", "frieren", ...]
  2. Load downloaded.json -> ["[SubsPlease] Jujutsu Kaisen - 54 (1080p) [HASH].mkv", ...]
  3. Fetch SubsPlease RSS (https://subsplease.org/rss/?r=1080)
     |-- Parse feed entries
     |-- For each: extract name (strip "- 1080"), magnet, title
  4. For each query:
     |-- For each release:
         |-- If query matches release name (case-insensitive substring)
         |   |-- If title NOT in downloaded list:
         |   |   |-- POST http://127.0.0.1:5000/download
         |   |   |   { "name": "<show_name>", "type": "show", "magnet": "<magnet>" }
         |   |   |   `-- API server handles download in background thread
         |   |   |-- Append title to downloaded list
         |   |   |-- Save downloaded.json
         |   |   `-- Sleep 20 seconds (rate limiting)
         |   |-- Else: skip (already downloaded)
  5. Sleep 1200 seconds (20 minutes)
```

---

## 4. API Server

### Entry Point

```bash
python3 api_server.py
```

Runs a Flask application on `0.0.0.0:5000` by default. CORS is enabled for iOS Shortcuts compatibility.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DAISY_API_KEY` | `your-secret-key-change-this` | API key for authentication |
| `DAISY_HOST` | `0.0.0.0` | Bind address |
| `DAISY_PORT` | `5000` | Bind port |
| `DAISY_DEBUG` | `false` | Flask debug mode |

### Authentication

All endpoints except `/health` require an API key. The key can be provided via:

- HTTP header: `X-API-Key: <key>`
- Query parameter: `?api_key=<key>`

Unauthorized requests return `401` with `{"error": "Unauthorized - invalid API key"}`.

### Endpoints

#### `GET /health`

Health check. No authentication required.

**Response (200):**
```json
{
  "status": "ok",
  "service": "daisy-api",
  "version": "2.0"
}
```

---

#### `GET /search` or `POST /search`

Search for torrents across multiple indexes.

**Parameters (query string for GET, JSON body for POST):**

| Parameter | Required | Default | Description |
|---|---|---|---|
| `q` or `query` | Yes | -- | Search query string |
| `type` | No | `auto` | Media type hint: `anime`, `movie`, `show`, or `auto` |
| `limit` | No | `20` | Maximum number of results |

**Response (200):**
```json
{
  "success": true,
  "query": "chainsaw man",
  "count": 15,
  "results": [
    {
      "title": "[SubsPlease] Chainsaw Man - 05 (1080p) [ABC123].mkv",
      "magnet": "magnet:?xt=urn:btih:...",
      "size": "1.4 GiB",
      "seeders": 500,
      "leechers": 20,
      "source": "nyaa.si",
      "uploader": "SubsPlease",
      "quality": "1080p",
      "score": 5075.0,
      "suggested_type": "other",
      "index": 0,
      "display_text": "#0 [SubsPlease] Chainsaw Man - 05...\n... nyaa.si | 500 | 1.4 GiB | 5075"
    }
  ]
}
```

**Error (400):** `{"error": "Missing query parameter"}`

**Error (500):** `{"success": false, "error": "<exception message>"}`

---

#### `POST /download`

Download a torrent by magnet link. Returns immediately; download runs in a background thread.

**Request body (JSON):**

| Field | Required | Default | Description |
|---|---|---|---|
| `magnet` | Yes | -- | Magnet link or torrent site URL |
| `name` | Yes | -- | Display name for the download |
| `type` | No | `other` | Media type: `movie`, `show`, or `other` |

**Response (200):**
```json
{
  "success": true,
  "message": "Download started: My Movie",
  "name": "My Movie",
  "type": "movie",
  "note": "Download running in background - check Discord for completion"
}
```

**Error (400):** Missing/invalid parameters.

**Error (500):** qBittorrent connection failure or other server error.

---

#### `POST /quick-download`

Search and download in a single request. Searches, selects a result, and starts the download.

**Request body (JSON):**

| Field | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | -- | Search query |
| `name` | No | Uses `query` | Custom name for the download |
| `type` | No | `auto` | Media type: `movie`, `show`, `other`, or `auto` (resolves from result) |
| `index` | No | `0` | Which search result to download (0-based) |

**Response (200):**
```json
{
  "success": true,
  "message": "Download started",
  "selected_torrent": { "...torrent result fields..." },
  "name": "chainsaw man",
  "type": "other",
  "note": "Download running in background - check Discord for completion"
}
```

**Error (404):** `{"success": false, "error": "No torrents found for query"}`

**Error (400):** Index out of range or missing query.

---

#### `GET /status`

Returns current download status and storage information.

**Response (200):**
```json
{
  "success": true,
  "active_downloads": [
    {
      "name": "Some.Torrent.Name",
      "progress": 45.2,
      "state": "downloading",
      "download_speed": 5242880,
      "eta": 3600
    }
  ],
  "storage": {
    "movies": { "free_gb": 120.5, "capacity_gb": 465 },
    "other": { "free_gb": 450.3, "capacity_gb": 931 }
  },
  "total_torrents": 12
}
```

Active download states tracked: `downloading`, `stalledDL`, `metaDL`, `allocating`.

---

### Error Handlers

| Code | Response |
|---|---|
| 404 | `{"error": "Endpoint not found"}` |
| 500 | `{"error": "Internal server error"}` |

### Threading Model

The API server uses a **global** `MediaProcessor` instance (module-level `media_processor` variable). Downloads are dispatched to daemon threads via `threading.Thread(daemon=True)`. The Flask server responds immediately to the client. Download completion is communicated via Discord webhooks, not via the API response.

**Concurrency caveat:** Multiple simultaneous downloads could interfere with each other in the `_monitor_download()` method, which identifies torrents by name in the global torrent list.

---

## 5. AutoDL Daemon

### Entry Point

```bash
python3 autodl.py
```

Runs as a persistent foreground process (typically managed with `nohup`, `screen`, `tmux`, or a systemd service).

### Configuration Files

#### `autodl_queries.json`

A JSON array of strings representing show names to watch for.

```json
["chainsaw man", "blue lock", "mob psycho 100 s3", "buddy daddies", "nier"]
```

Matching is **case-insensitive substring** against the release name from the RSS feed. For example, the query `"blue lock"` matches any release whose name contains "blue lock" (ignoring case).

#### `downloaded.json`

A JSON array of full release titles that have already been downloaded. Prevents duplicate downloads.

```json
[
  "[SubsPlease] Blue Lock - 20 (1080p) [96A5140C].mkv",
  "[SubsPlease] Buddy Daddies - 08 (1080p) [6DDD016B].mkv"
]
```

### RSS Source

**URL:** `https://subsplease.org/rss/?r=1080`

Fetches SubsPlease's 1080p releases RSS feed. Each entry provides:

- `entry.category` -- Show name with resolution suffix (e.g., `"Blue Lock - 1080"`). The `"- 1080"` is stripped.
- `entry.link` -- Magnet link.
- `entry.title` -- Full release filename including group tag, episode number, resolution, and CRC hash.

### Timing

| Constant | Value | Description |
|---|---|---|
| `CHECK_INTERVAL` | 1200 seconds (20 minutes) | Time between RSS feed checks |
| Inter-download sleep | 20 seconds | Delay between triggering consecutive downloads to avoid overwhelming the system |

### Download Trigger

Downloads are triggered via HTTP POST to the Daisy API server at `http://127.0.0.1:{DAISY_PORT}/download`. The autodl daemon sends the actual show name (extracted from the RSS feed) and type `'show'` in the JSON body, authenticated with the `DAISY_API_KEY` header.

**Environment variables** (set in the systemd service):

| Variable | Description |
|---|---|
| `DAISY_API_KEY` | API key for authenticating with the Daisy API server |
| `DAISY_PORT` | Port the API server listens on (default: 5000) |

The autodl service depends on `daisy-api.service` to ensure the API is available before triggering downloads.

### Logging

Logs to `alog` file with `YYYY-MM-DD HH:MM:SS` timestamps.

---

## 6. Configuration

### Configuration Hierarchy

1. If `config.json` exists in the working directory, it is loaded.
2. Otherwise, hardcoded defaults in the dataclass definitions are used.

### All Configuration Options

#### qBittorrent (`QBittorrentConfig`)

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | str | `127.0.0.1` | qBittorrent WebUI host |
| `port` | int | `8080` | qBittorrent WebUI port |
| `username` | str | `admin` | Login username |
| `password` | str | `""` | Login password |

Derived: `url` property returns `http://{host}:{port}/`

#### Jellyfin (`JellyfinConfig`)

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | str | `127.0.0.1` | Jellyfin server host |
| `port` | int | `8096` | Jellyfin server port |
| `api_key` | str | `""` | Jellyfin API key (created via Admin > API Keys) |

Derived: `url` property returns `http://{host}:{port}`

#### Discord (`DiscordConfig`)

| Field | Type | Default | Description |
|---|---|---|---|
| `daisy_webhook` | str | `""` | Webhook URL for download event notifications |
| `storage_webhook` | str | `""` | Webhook URL for storage status reports |

#### Storage (`StorageConfig`)

| Field | Type | Default | Description |
|---|---|---|---|
| `movies_path` | str | `/mnt/movies` | Root path for the movies drive |
| `movies_temp_path` | str | `/mnt/movies/temp/` | Temp directory for movie downloads (host path) |
| `movies_docker_path` | str | `/movies/temp/` | Temp directory as seen inside the qBittorrent Docker container |
| `movies_capacity_gb` | int | `465` | Total capacity of the movies drive in GB |
| `other_path` | str | `/mnt/shows` | Root path for the other/shows drive |
| `other_temp_path` | str | `/mnt/shows/temp/` | Temp directory for show/other downloads (host path) |
| `other_docker_path` | str | `/other/temp/` | Temp directory as seen inside the qBittorrent Docker container |
| `other_jellyfin_path` | str | `/path/to/shows/` | Path prefix as seen by Jellyfin (for library section creation) |
| `other_capacity_gb` | int | `931` | Total capacity of the other drive in GB |

Derived: `movies_dir` property returns `{movies_path}/movies/`

#### Global Constants

| Constant | Location | Value | Description |
|---|---|---|---|
| `USER_AGENT` | `config.py` | Chrome 55 UA string | Used for all HTTP scraping requests |
| `CHECK_INTERVAL` | `autodl.py` | `1200` | AutoDL polling interval in seconds |
| `SUBSPLEASE_RSS` | `autodl.py` | `https://subsplease.org/rss/?r=1080` | SubsPlease 1080p RSS feed URL |
| `QUERIES_FILE` | `autodl.py` | `autodl_queries.json` | Path to autodl watch list |
| `DOWNLOADED_FILE` | `autodl.py` | `downloaded.json` | Path to autodl download history |

---

## 7. Storage Layout

### Drive Architecture

The system uses a single LVM volume combining multiple physical disks, mounted at `/mnt/storage/` (~2.5 TB):

```
/mnt/storage/
+-- movies/
|   +-- temp/                    <- qBittorrent downloads movies here
|   |   +-- <torrent_name>/     <- directory downloads (extracted)
|   |   `-- <filename>.mkv      <- single file downloads
|   +-- movies/                  <- Final destination for organized movies
|       +-- Movie.Name.2023.1080p.mkv
|       +-- Movie.Name.2023.1080p.srt   (if subtitle found)
|       `-- ...
+-- shows/
    +-- temp/                    <- qBittorrent downloads shows here
    |   +-- <torrent_name>/
    |   `-- <filename>.mkv
    +-- <show_name_normalized>/  <- Per-show directories (e.g., "jujutsu_kaisen/")
    |   +-- [SubsPlease] Jujutsu Kaisen - 54 (1080p) [HASH].mkv
    |   +-- [SubsPlease] Jujutsu Kaisen - 55 (1080p) [HASH].mkv
    |   `-- ...
    +-- <another_show>/
    `-- ...
```

### Path Configuration

qBittorrent runs natively (not in Docker), so `docker_path` and `temp_path` fields in config are identical. The `re.sub()` path translation in `media_processor.py` becomes a no-op. These fields exist for backward compatibility with older Docker-based deployments.

### Jellyfin Libraries

| Library | Type | Path | Description |
|---|---|---|---|
| Movies | movies | `/mnt/storage/movies/movies` | Organized movie files (NOT the temp dir) |
| Shows | tvshows | `/mnt/storage/shows` | Per-show subdirectories with episodes |

**Important:** The Movies library must point to `.../movies/movies` (not `.../movies`), otherwise Jellyfin will scan the `temp/` directory and misidentify files.

### File Naming Conventions

- **Show directories:** Names are normalized: spaces replaced with underscores, lowercased. Example: `"Blue Lock"` becomes `blue_lock/`.
- **Movie files:** Kept with their original torrent filenames. Moved directly into the movies directory.
- **Subtitles:** Renamed to match the video file basename (e.g., `Movie.Name.mkv` gets `Movie.Name.srt`).
- **SubsPlease files:** Keep original names like `[SubsPlease] Show Name - 01 (1080p) [CRC32].mkv`. The show name is extracted via regex for directory placement.

### File Permissions

- New show directories are created with mode `0o777`.
- Files downloaded by Docker-based qBittorrent are owned by root. Daisy runs `sudo chown $USER:$USER` on them before moving.

---

## 8. External Dependencies

### Runtime Services

| Service | Connection | Purpose | Required |
|---|---|---|---|
| **qBittorrent** | HTTP WebUI at `127.0.0.1:8080` | Torrent downloading | Yes |
| **Jellyfin** | HTTP API at `127.0.0.1:8096` | Media library management | Yes (for library registration) |
| **Discord** | Webhook HTTP POST | Notifications | No (fails silently) |

### Torrent Sites (Search/Scrape)

| Site | Method | Used By |
|---|---|---|
| **nyaa.si** | RSS feed (search), HTML scraping (magnet extraction) | `torrent_search.py`, `magnet_converters.py` |
| **1337x.to** | HTML scraping (search + detail pages) | `torrent_search.py`, `magnet_converters.py` |
| **The Pirate Bay** | JSON API via `apibay.org` | `torrent_search.py` |
| **SubsPlease** | JavaScript-rendered page scraping, RSS feed | `magnet_converters.py`, `autodl.py` |
| **ext.to** | JavaScript-rendered page scraping | `magnet_converters.py` |

### Python Packages

From `requirements.txt`:

| Package | Version | Purpose |
|---|---|---|
| `beautifulsoup4` | 4.11.2 | HTML parsing for torrent site scraping |
| `feedparser` | 6.0.10 | RSS feed parsing (nyaa.si, SubsPlease) |
| `PlexAPI` | 4.13.1 | Legacy Plex support (no longer used; Jellyfin uses `requests` directly) |
| `python_qbittorrent` | 0.4.3 | qBittorrent WebUI client (`qbittorrent.Client`) |
| `requests` | 2.25.1 | HTTP requests |
| `requests_html` | 0.10.0 | JavaScript-rendered page fetching (uses Chromium headless) |
| `Flask` | 2.3.0 | API server framework |
| `flask-cors` | 4.0.0 | CORS support for iOS Shortcuts |
| `paramiko` | (unlisted) | SSH client for Windows remote scripts (`daisy_win.py`, `windl.py`) |

**Note:** `requests_html` requires Chromium to be installed for JavaScript rendering. On first run, it downloads Chromium automatically.

### System Dependencies

- `sudo` -- Required for `chown` operations on Docker-created files.
- `nohup` -- Used by `daisy_shell.sh` to run downloads in the background.
- `python3` -- Python 3.7+ (dataclasses, f-strings, type hints).

---

## 9. Deployment

### Prerequisites

1. **qBittorrent-nox** installed natively with WebUI enabled on port 8080.
2. **Jellyfin** installed with API key created and libraries configured.
3. **Discord webhooks** created for the target channels (optional).
4. **Python 3.10+** with packages from `requirements.txt` installed (plus `lxml_html_clean`).
5. **sudo** access for the running user (passwordless sudo for `chown` recommended).
6. Storage drives mounted at the configured paths.

> **For detailed step-by-step installation, see [SETUP.md](SETUP.md).**

### Installation

```bash
cd ~/daisy
pip3 install -r requirements.txt
```

Optionally create `config.json` to override defaults:

```json
{
  "qbittorrent": {
    "host": "127.0.0.1",
    "port": 8080,
    "username": "admin",
    "password": "admin"
  },
  "jellyfin": {
    "host": "127.0.0.1",
    "port": 8096,
    "api_key": "your-jellyfin-api-key"
  },
  "discord": {
    "daisy_webhook": "https://discord.com/api/webhooks/...",
    "storage_webhook": "https://discord.com/api/webhooks/..."
  },
  "storage": {
    "movies_path": "/mnt/storage/movies",
    "movies_temp_path": "/mnt/storage/movies/temp/",
    "movies_docker_path": "/mnt/storage/movies/temp/",
    "movies_capacity_gb": 2560,
    "other_path": "/mnt/storage/shows",
    "other_temp_path": "/mnt/storage/shows/temp/",
    "other_docker_path": "/mnt/storage/shows/temp/",
    "other_jellyfin_path": "/mnt/storage/shows/",
    "other_capacity_gb": 2560
  }
}
```

### Running the CLI (Single Download)

```bash
# Direct execution
python3 daisy.py -t movie -n "Movie Name" -m "magnet:?xt=urn:btih:..."

# Via shell wrapper (runs in background)
sh daisy_shell.sh movie "Movie Name" "magnet:?xt=urn:btih:..."

# Show with URL conversion
python3 daisy.py -t show -n "Show Name" -m "https://nyaa.si/view/12345"

# SubsPlease batch
python3 daisy.py -t other -n "autodl" -m "https://subsplease.org/shows/show-name"
```

### Running the API Server

```bash
# Default (port 5000, no auth key security)
python3 api_server.py

# With custom settings
export DAISY_API_KEY="your-secure-key-here"
export DAISY_PORT=8888
python3 api_server.py

# Production (background)
nohup python3 api_server.py >> api.log 2>&1 &
```

### Running the AutoDL Daemon

```bash
# Foreground
python3 autodl.py

# Background with nohup
nohup python3 autodl.py >> alog 2>&1 &

# With screen
screen -S autodl python3 autodl.py
```

Before starting, populate `autodl_queries.json` with show names to watch:

```json
["show name one", "show name two"]
```

And initialize `downloaded.json` if it does not exist:

```json
[]
```

### Running the Windows Remote Client

On a Windows machine with Python and paramiko installed:

```bash
python daisy_win.py
```

Edit the `host`, `user`, and `pass_` variables in the script to match your server credentials.

### Log Files

| File | Source | Content |
|---|---|---|
| `dlog` | `daisy.py` (CLI) | Download processing logs, torrent info, file operations |
| `alog` | `autodl.py` (daemon) | RSS feed checks, query matching, download triggers |
| `api.log` | `api_server.py` | API request/response logs, search results, download dispatching |

All log files are append-mode. They are listed in `.gitignore` and not tracked by version control.

### Running All Components Together

A typical deployment runs three systemd services:

```bash
# systemd user services (auto-start on boot):
systemctl --user status daisy-api        # API server (Flask on port 5000)
systemctl --user status daisy-autodl     # AutoDL daemon (RSS monitor → calls API)
systemctl --user status qbittorrent-nox  # qBittorrent (headless on port 8080)

# systemd system services:
sudo systemctl status jellyfin           # Media server (port 8096)
sudo systemctl status cloudflared        # Cloudflare Tunnel (exposes API publicly)
```

The autodl daemon triggers downloads by POSTing to the API server. The CLI (`daisy.py`) can also be used directly for one-off downloads.

### Remote Access

The Daisy API is exposed publicly via a Cloudflare Tunnel. No ports need to be opened on the server firewall. The tunnel creates an outbound-only connection to Cloudflare's edge network.

- **Public URL:** `https://daisy.<your-domain>` (e.g., `https://daisy.jndl.dev`)
- **Auth:** All endpoints except `/health` require the API key via `X-API-Key` header or `?api_key=` query param
- **Service:** `cloudflared.service` (system-level systemd service)
- **Config:** `/etc/cloudflared/config.yml`

See [SETUP.md](SETUP.md) section 8 for tunnel setup instructions.
