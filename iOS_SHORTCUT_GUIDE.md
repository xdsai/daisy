# iOS Shortcut Setup Guide

This guide shows you how to create an iOS Shortcut to search and download torrents from your phone.

## Prerequisites

1. **API Server Running**: Make sure the Daisy API server is running on your server
2. **API Key**: Know your API key (set via `DAISY_API_KEY` environment variable)
3. **Server IP**: Know your server's IP address

## Starting the API Server

On your server, run:

```bash
cd ~/daisy

# Set your API key (change this!)
export DAISY_API_KEY="your-secret-key-here"

# Start the server
python3 api_server.py
```

The server will run on port 5000 by default. You should see:

```
Server running on: http://0.0.0.0:5000
API Key: your...here
```

### Running as a Background Service (Optional)

Create a systemd service to run it automatically:

```bash
sudo nano /etc/systemd/system/daisy-api.service
```

Add:

```ini
[Unit]
Description=Daisy API Server
After=network.target

[Service]
Type=simple
User=alex
WorkingDirectory=/home/alex/daisy
Environment="DAISY_API_KEY=your-secret-key-here"
ExecStart=/usr/bin/python3 api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable daisy-api
sudo systemctl start daisy-api
```

## iOS Shortcut Setup

### Option 1: Interactive Search & Select (Recommended)

This shortcut lets you search, see results with seeders/size info, and pick which one to download.

**Steps:**

1. Open **Shortcuts** app on iOS
2. Tap **+** to create new shortcut
3. Add these actions:

#### Action 1: Ask for Input
- **Action**: `Ask for Input`
- **Prompt**: "What do you want to download?"
- **Input Type**: Text
- **Store as**: `Query`

#### Action 2: Get Contents of URL (Search)
- **Action**: `Get Contents of URL`
- **URL**: `http://YOUR_SERVER_IP:5000/search`
- **Method**: `GET`
- **Headers**:
  - `X-API-Key`: `your-secret-key-here`
- **Request Body**: None
- **Add to URL**:
  - `q`: `Query` (provided input)
  - `limit`: `10`

#### Action 3: Get Dictionary Value
- **Action**: `Get Dictionary Value`
- **Get**: `results`
- **From**: `Contents of URL`

#### Action 4: Repeat with Each
- **Action**: `Repeat with Each`
- **Each**: `Dictionary Value`

#### Action 5 (inside repeat): Get Dictionary Values
- **Action**: `Get Dictionary Value`
- **Keys to get**:
  - `title`
  - `seeders`
  - `size`
  - `score`

#### Action 6 (inside repeat): Format Text
- **Action**: `Text`
- **Text**:
```
🌱 Repeat Item: title
👥 Repeat Item: seeders seeders | 💾 Repeat Item: size
⭐ Score: Repeat Item: score
```

#### Action 7: Choose from List
- **Action**: `Choose from List`
- **Prompt**: "Select torrent to download"
- **List**: `Formatted Text` (from repeat loop)

#### Action 8: Get Dictionary Value (Magnet)
- **Action**: `Get Dictionary Value`
- **Get**: `magnet`
- **From**: `Chosen Item`

#### Action 9: Get Contents of URL (Download)
- **Action**: `Get Contents of URL`
- **URL**: `http://YOUR_SERVER_IP:5000/download`
- **Method**: `POST`
- **Headers**:
  - `X-API-Key`: `your-secret-key-here`
  - `Content-Type`: `application/json`
- **Request Body**: `JSON`
```json
{
  "magnet": "Dictionary Value",
  "name": "Query",
  "type": "other"
}
```

#### Action 10: Show Notification
- **Action**: `Show Notification`
- **Text**: `Download started: Query`

### Option 2: Quick Download (Best Match)

This shortcut automatically downloads the best result (highest score) without showing a list.

**Steps:**

1. Open **Shortcuts** app
2. Create new shortcut
3. Add these actions:

#### Action 1: Ask for Input
- **Prompt**: "What do you want to download?"
- **Store as**: `Query`

#### Action 2: Get Contents of URL
- **URL**: `http://YOUR_SERVER_IP:5000/quick-download`
- **Method**: `POST`
- **Headers**:
  - `X-API-Key`: `your-secret-key-here`
  - `Content-Type`: `application/json`
- **Request Body**: `JSON`
```json
{
  "query": "Query",
  "type": "auto",
  "index": 0
}
```

#### Action 3: Get Dictionary Value
- **Get**: `message`
- **From**: `Contents of URL`

#### Action 4: Show Notification
- **Text**: `Dictionary Value`

### Option 3: Home Screen Widget

You can also create widgets for frequently downloaded shows:

1. Create a shortcut using Option 2
2. Instead of "Ask for Input", use **Text** action with the show name
3. Add to Home Screen as widget

## API Endpoints Reference

### GET/POST /search

Search for torrents.

**Parameters:**
- `q` or `query` (required): Search query
- `type` (optional): `anime`, `movie`, `show`, or `auto` (default)
- `limit` (optional): Max results (default: 20)
- `api_key` (required): Your API key

**Example:**
```
GET http://192.168.0.101:5000/search?q=Chainsaw+Man+05&api_key=your-key
```

**Response:**
```json
{
  "success": true,
  "query": "Chainsaw Man 05",
  "count": 5,
  "results": [
    {
      "title": "[SubsPlease] Chainsaw Man - 05 (1080p)",
      "magnet": "magnet:?xt=...",
      "size": "1.4 GiB",
      "seeders": 234,
      "leechers": 12,
      "source": "nyaa.si",
      "uploader": "SubsPlease",
      "quality": "1080p",
      "score": 2390
    }
  ]
}
```

### POST /download

Download a specific torrent.

**Body (JSON):**
```json
{
  "magnet": "magnet:?xt=...",
  "name": "Chainsaw Man",
  "type": "other"
}
```

**Headers:**
- `X-API-Key`: Your API key
- `Content-Type`: application/json

**Response:**
```json
{
  "success": true,
  "message": "Download started: Chainsaw Man",
  "name": "Chainsaw Man",
  "type": "other"
}
```

### POST /quick-download

Search and download in one step.

**Body (JSON):**
```json
{
  "query": "Chainsaw Man 05",
  "type": "auto",
  "index": 0
}
```

**Parameters:**
- `query` (required): Search query
- `type` (optional): Media type or `auto`
- `index` (optional): Which result to download (0 = best, 1 = second best, etc.)

**Response:**
```json
{
  "success": true,
  "message": "Download started",
  "selected_torrent": {
    "title": "[SubsPlease] Chainsaw Man - 05 (1080p)",
    "seeders": 234,
    "size": "1.4 GiB"
  }
}
```

### GET /status

Get download status and storage info.

**Response:**
```json
{
  "success": true,
  "active_downloads": [
    {
      "name": "Chainsaw Man - 05",
      "progress": 45.2,
      "state": "downloading",
      "download_speed": 5242880,
      "eta": 120
    }
  ],
  "storage": {
    "movies": {"free_gb": 234.5, "capacity_gb": 465},
    "other": {"free_gb": 567.8, "capacity_gb": 931}
  }
}
```

## Security Notes

1. **API Key**: Keep your API key secret! Don't share your shortcuts publicly
2. **Network**: The API runs on your local network by default
3. **Firewall**: If accessing from outside, use a VPN or set up proper firewall rules
4. **HTTPS**: For external access, consider setting up nginx with SSL

## Troubleshooting

### "Unauthorized" Error
- Check that your API key in the shortcut matches `DAISY_API_KEY`
- Make sure you're including the `X-API-Key` header

### "Connection Failed"
- Verify server IP and port
- Check that API server is running: `systemctl status daisy-api`
- Check firewall: `sudo ufw status`

### "No Results Found"
- Try a different search query
- Check API logs: `tail -f ~/daisy/api.log`

### Downloads Not Starting
- Check qBittorrent is running
- Verify credentials in config
- Check main logs: `tail -f ~/daisy/dlog`

## Advanced: Siri Integration

Once you have a shortcut set up, you can add it to Siri:

1. Open your shortcut
2. Tap the settings icon
3. Tap "Add to Siri"
4. Record a phrase like "Download Chainsaw Man"

Now you can just say "Hey Siri, download Chainsaw Man" and it will run!

## Example Queries

Good search queries:
- "Chainsaw Man 05" - Specific episode
- "The Matrix 1080p" - Movie with quality
- "Breaking Bad S05E16" - TV show episode
- "SubsPlease Mob Psycho" - By release group

The search will automatically:
- Prioritize results with more seeders
- Prefer 1080p quality
- Rank trusted uploaders higher
- Filter out dead torrents (0 seeders)

## Migration from SSH Method

If you were using the old SSH-based method:

**Old way:**
1. SSH to server
2. Run shell script
3. Paste magnet link

**New way:**
1. Open shortcut
2. Type what you want
3. Pick from list
4. Done!

The API method is:
- ✅ Faster (no SSH overhead)
- ✅ More user-friendly (interactive search)
- ✅ Works from anywhere (not just local network if you set up port forwarding)
- ✅ Better security (API key instead of SSH password)
