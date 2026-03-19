# Daisy -- Full Server Setup Guide

This guide covers setting up Daisy and all its dependencies from scratch on a fresh Ubuntu server. It is written to be followed by a human or handed to an AI agent for automated setup.

## Prerequisites

- Ubuntu 22.04+ server (tested on 24.04)
- One or more storage disks (in addition to the OS disk)
- `sudo` access (passwordless recommended: `echo "USERNAME ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/USERNAME-nopasswd && sudo chmod 440 /etc/sudoers.d/USERNAME-nopasswd`)
- GitHub SSH key configured (for cloning)

## 1. Storage Setup (LVM)

If you have multiple disks to combine into one volume:

```bash
# Identify available disks (exclude the OS disk, usually nvme0n1 or sda)
lsblk -d -o NAME,SIZE,MODEL,TYPE | grep disk

# Wipe, create PVs, VG, LV (replace sdX with your disks)
sudo wipefs -a /dev/sda /dev/sdb /dev/sdc /dev/sdd
sudo pvcreate /dev/sda /dev/sdb /dev/sdc /dev/sdd
sudo vgcreate storage-vg /dev/sda /dev/sdb /dev/sdc /dev/sdd
sudo lvcreate -l 100%FREE -n storage-lv storage-vg

# Format and mount
sudo mkfs.ext4 -L storage /dev/storage-vg/storage-lv
sudo mkdir -p /home/$USER/storage
sudo mount /dev/storage-vg/storage-lv /home/$USER/storage
sudo chown $USER:$USER /home/$USER/storage

# Persist across reboots
echo '/dev/storage-vg/storage-lv /home/'$USER'/storage ext4 defaults 0 2' | sudo tee -a /etc/fstab
```

Create the media directory structure:

```bash
mkdir -p /home/$USER/storage/movies/movies
mkdir -p /home/$USER/storage/movies/temp
mkdir -p /home/$USER/storage/shows/temp
```

Layout:
```
/home/$USER/storage/
├── movies/
│   ├── movies/     ← organized movie files (final destination)
│   └── temp/       ← qBittorrent downloads movies here
└── shows/
    ├── <show_name>/← per-show directories (auto-created)
    └── temp/       ← qBittorrent downloads shows here
```

## 2. Clone Daisy

```bash
mkdir -p ~/repos
git clone git@github.com:xdsai/daisy.git ~/repos/daisy
cd ~/repos/daisy
```

## 3. Python Environment

```bash
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv

cd ~/repos/daisy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install lxml_html_clean   # required by requests_html on newer lxml
```

## 4. qBittorrent (Headless)

```bash
sudo apt-get install -y qbittorrent-nox
```

Create systemd user service:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/qbittorrent-nox.service << 'EOF'
[Unit]
Description=qBittorrent-nox (headless)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/qbittorrent-nox --webui-port=8080
Restart=always
RestartSec=5
KillMode=process
Environment=HOME=/home/USER_PLACEHOLDER

[Install]
WantedBy=default.target
EOF

# Replace placeholder with actual home dir
sed -i "s|USER_PLACEHOLDER|$USER|" ~/.config/systemd/user/qbittorrent-nox.service

# Enable lingering so user services survive logout
loginctl enable-linger $USER

systemctl --user daemon-reload
systemctl --user enable --now qbittorrent-nox.service
```

Wait for it to start, then configure credentials:

```bash
sleep 5

# Get the temporary password from logs
TEMP_PASS=$(journalctl --user -u qbittorrent-nox --no-pager | grep "temporary password" | tail -1 | grep -oP 'session: \K\S+')

# Login and set permanent credentials + default save path
curl -s -c /tmp/qbt-cookie "http://localhost:8080/api/v2/auth/login" --data "username=admin&password=$TEMP_PASS"
curl -s -b /tmp/qbt-cookie "http://localhost:8080/api/v2/app/setPreferences" \
  --data 'json={"web_ui_username":"admin","web_ui_password":"admin","save_path":"/home/'$USER'/storage/shows/temp/"}'
```

## 5. Jellyfin Media Server

```bash
curl -fsSL https://repo.jellyfin.org/install-debuntu.sh | sudo bash
```

Wait for Jellyfin to start, then complete setup:

```bash
sleep 10

# Give jellyfin user access to storage
sudo usermod -aG $USER jellyfin
sudo chmod 775 /home/$USER/storage /home/$USER/storage/movies /home/$USER/storage/movies/movies /home/$USER/storage/movies/temp /home/$USER/storage/shows /home/$USER/storage/shows/temp

# Complete the startup wizard
curl -s -X POST http://localhost:8096/Startup/Configuration \
  -H "Content-Type: application/json" \
  -d '{"UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"}'

curl -s -X POST http://localhost:8096/Startup/User \
  -H "Content-Type: application/json" \
  -d '{"Name":"admin","Password":"admin"}'

curl -s -X POST http://localhost:8096/Startup/RemoteAccess \
  -H "Content-Type: application/json" \
  -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}'

curl -s -X POST http://localhost:8096/Startup/Complete

# Authenticate
AUTH_RESPONSE=$(curl -s -X POST http://localhost:8096/Users/AuthenticateByName \
  -H "Content-Type: application/json" \
  -H 'X-Emby-Authorization: MediaBrowser Client="Daisy", Device="server", DeviceId="daisy-setup", Version="1.0"' \
  -d '{"Username":"admin","Pw":"admin"}')

JF_TOKEN=$(echo "$AUTH_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessToken'])")

# Create a permanent API key for daisy
curl -s -X POST "http://localhost:8096/Auth/Keys?app=daisy" \
  -H "Authorization: MediaBrowser Token=$JF_TOKEN"

JF_API_KEY=$(curl -s "http://localhost:8096/Auth/Keys" \
  -H "Authorization: MediaBrowser Token=$JF_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['Items'][0]['AccessToken'])")

echo "Jellyfin API key: $JF_API_KEY"

# Create libraries
curl -s -X POST "http://localhost:8096/Library/VirtualFolders?name=Movies&collectionType=movies&paths=/home/$USER/storage/movies/movies&refreshLibrary=true" \
  -H "Authorization: MediaBrowser Token=$JF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"LibraryOptions":{}}'

curl -s -X POST "http://localhost:8096/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=/home/$USER/storage/shows&refreshLibrary=true" \
  -H "Authorization: MediaBrowser Token=$JF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"LibraryOptions":{}}'
```

Restart Jellyfin for group membership to take effect:

```bash
sudo systemctl restart jellyfin
```

## 6. Daisy Configuration

Create `config.json` in the daisy repo directory:

```bash
cat > ~/repos/daisy/config.json << EOF
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
    "api_key": "$JF_API_KEY"
  },
  "discord": {
    "daisy_webhook": "",
    "storage_webhook": ""
  },
  "storage": {
    "movies_path": "/home/$USER/storage/movies",
    "movies_temp_path": "/home/$USER/storage/movies/temp/",
    "movies_docker_path": "/home/$USER/storage/movies/temp/",
    "movies_capacity_gb": 2560,
    "other_path": "/home/$USER/storage/shows",
    "other_temp_path": "/home/$USER/storage/shows/temp/",
    "other_docker_path": "/home/$USER/storage/shows/temp/",
    "other_jellyfin_path": "/home/$USER/storage/shows/",
    "other_capacity_gb": 2560
  }
}
EOF
```

**Note:** `movies_docker_path` and `other_docker_path` should be identical to `movies_temp_path` and `other_temp_path` when running qBittorrent natively (not in Docker). These fields exist for backward compatibility.

Set up autodl queries (edit as needed):

```bash
echo '["jujutsu kaisen", "frieren"]' > ~/repos/daisy/autodl_queries.json
echo '[]' > ~/repos/daisy/downloaded.json
```

## 7. Daisy Systemd Services

Generate an API key (or use your own):

```bash
DAISY_API_KEY="your-api-key-here"
```

Create the API server service:

```bash
cat > ~/.config/systemd/user/daisy-api.service << EOF
[Unit]
Description=Daisy API Server
After=network-online.target qbittorrent-nox.service
Wants=network-online.target

[Service]
WorkingDirectory=/home/$USER/repos/daisy
ExecStart=/home/$USER/repos/daisy/.venv/bin/python api_server.py
Restart=always
RestartSec=5
KillMode=process
Environment=HOME=/home/$USER
Environment=DAISY_API_KEY=$DAISY_API_KEY
Environment=DAISY_HOST=0.0.0.0
Environment=DAISY_PORT=5000

[Install]
WantedBy=default.target
EOF
```

Create the autodl daemon service:

```bash
cat > ~/.config/systemd/user/daisy-autodl.service << EOF
[Unit]
Description=Daisy AutoDL Daemon (SubsPlease RSS monitor)
After=network-online.target qbittorrent-nox.service daisy-api.service
Wants=network-online.target

[Service]
WorkingDirectory=/home/$USER/repos/daisy
ExecStart=/home/$USER/repos/daisy/.venv/bin/python autodl.py
Restart=always
RestartSec=30
KillMode=process
Environment=HOME=/home/$USER
Environment=DAISY_API_KEY=$DAISY_API_KEY
Environment=DAISY_PORT=5000

[Install]
WantedBy=default.target
EOF
```

**Note:** The autodl daemon triggers downloads by calling the Daisy API server (POST `/download`), so it needs the same `DAISY_API_KEY` and must start after `daisy-api.service`.

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now daisy-api.service daisy-autodl.service
```

## 8. Cloudflare Tunnel (Remote Access)

Expose the Daisy API publicly via Cloudflare Tunnel. Requires a domain managed by Cloudflare.

```bash
# Install cloudflared
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i /tmp/cloudflared.deb

# Authenticate (opens a browser URL — select your domain)
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create daisy
TUNNEL_ID=$(cloudflared tunnel list -o json | python3 -c "import sys,json; print([t['id'] for t in json.load(sys.stdin) if t['name']=='daisy'][0])")

# Create DNS route (replace with your subdomain)
cloudflared tunnel route dns daisy daisy.yourdomain.dev

# Configure tunnel
sudo mkdir -p /etc/cloudflared
cat > /tmp/cloudflared-config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: /home/$USER/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: daisy.yourdomain.dev
    service: http://localhost:5000
  - service: http_status:404
EOF

sudo cp /tmp/cloudflared-config.yml /etc/cloudflared/config.yml
sudo cp /home/$USER/.cloudflared/$TUNNEL_ID.json /etc/cloudflared/$TUNNEL_ID.json

# Install and start as system service
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Verify:

```bash
curl -s https://daisy.yourdomain.dev/health
```

## 9. Verification

```bash
# Check all services
systemctl --user status qbittorrent-nox daisy-api daisy-autodl
sudo systemctl status jellyfin

# Test daisy API health
curl -s http://localhost:5000/health

# Test a search
curl -s "http://localhost:5000/search?q=test&api_key=$DAISY_API_KEY" | python3 -m json.tool | head -20

# Test Jellyfin
curl -s http://localhost:8096/System/Info/Public | python3 -m json.tool
```

## 10. Discord Webhooks (Optional)

Once you have webhook URLs, update `config.json`:

```json
{
  "discord": {
    "daisy_webhook": "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN",
    "storage_webhook": "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
  }
}
```

Then restart the API service:

```bash
systemctl --user restart daisy-api.service
```

## 11. Network Ports Summary

| Service | Port | Purpose |
|---|---|---|
| qBittorrent WebUI | 8080 | Torrent management |
| Daisy API | 5000 | HTTP API for search/download |
| Jellyfin | 8096 | Media server web UI + API |
| Cloudflare Tunnel | — | Exposes Daisy API at `https://daisy.yourdomain.dev` (no open ports) |

## Troubleshooting

- **qBittorrent won't start:** Check `journalctl --user -u qbittorrent-nox -f`
- **Daisy API crashes on import:** Run `pip install lxml_html_clean` in the venv
- **Jellyfin can't read storage:** Ensure `jellyfin` user is in your group (`sudo usermod -aG $USER jellyfin`) and restart jellyfin
- **Downloads complete but files stay in temp:** Check daisy logs (`tail -f ~/repos/daisy/api.log`) — usually a path mismatch in config.json
- **Base32 infohash errors:** Magnets from nyaa/subsplease use base32 hashes — this is handled automatically since the base32-to-hex fix in `download_manager.py`
