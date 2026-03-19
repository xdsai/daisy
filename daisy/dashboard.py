"""
Daisy Dashboard - localhost-only web interface for managing torrents.
Provides search, download, autodl management, and live qBittorrent tracking.
"""

import json
import logging
import os
import sys
import shutil
import threading
from datetime import datetime

from flask import Flask, render_template, jsonify, request

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from .config import Config
from .torrent_search import search_torrents
from .media_processor import MediaProcessor
from qbittorrent import Client

logging.basicConfig(
    filename=os.path.join(REPO_ROOT, 'logs', 'dashboard.log'),
    filemode='a',
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=os.path.join(REPO_ROOT, 'templates'))

config = Config.load(os.path.join(REPO_ROOT, 'config.json'))

QUERIES_FILE = os.path.join(REPO_ROOT, 'autodl_queries.json')
DOWNLOADED_FILE = os.path.join(REPO_ROOT, 'downloaded.json')

# qBittorrent client
qb = None
media_processor = None


def get_qb():
    """Get or create qBittorrent client."""
    global qb
    try:
        if qb is None:
            qb = Client(config.qbittorrent.url)
            qb.login(config.qbittorrent.username, config.qbittorrent.password)
        # Test connection
        qb.torrents(limit=1)
        return qb
    except Exception:
        try:
            qb = Client(config.qbittorrent.url)
            qb.login(config.qbittorrent.username, config.qbittorrent.password)
            return qb
        except Exception as e:
            logger.error(f"qBittorrent connection failed: {e}")
            return None


def get_processor():
    """Get or create MediaProcessor."""
    global media_processor
    if media_processor is None:
        media_processor = MediaProcessor(config)
        media_processor.connect()
    return media_processor


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def format_size(size_bytes):
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PiB"


def format_speed(speed_bytes):
    if speed_bytes <= 0:
        return "0 B/s"
    for unit in ['B/s', 'KiB/s', 'MiB/s', 'GiB/s']:
        if speed_bytes < 1024.0:
            return f"{speed_bytes:.1f} {unit}"
        speed_bytes /= 1024.0
    return f"{speed_bytes:.1f} TiB/s"


def format_eta(seconds):
    if seconds <= 0 or seconds >= 8640000:
        return "∞"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# --- Routes ---

@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    media_type = request.args.get('type', 'auto')
    limit = int(request.args.get('limit', 30))
    if not query:
        return jsonify({'error': 'Missing query'}), 400
    try:
        results = search_torrents(query, media_type, limit)
        return jsonify({'results': results, 'count': len(results)})
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    magnet = data.get('magnet')
    name = data.get('name', 'Unknown')
    media_type = data.get('type', 'other')
    if not magnet:
        return jsonify({'error': 'Missing magnet'}), 400
    try:
        proc = get_processor()
        if not proc:
            return jsonify({'error': 'Cannot connect to qBittorrent'}), 500
        thread = threading.Thread(
            target=proc.process,
            args=(media_type, name, magnet),
            daemon=True
        )
        thread.start()
        return jsonify({'success': True, 'message': f'Download started: {name}'})
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/torrents')
def api_torrents():
    client = get_qb()
    if not client:
        return jsonify({'error': 'Cannot connect to qBittorrent'}), 500
    try:
        torrents = client.torrents()
        result = []
        for t in torrents:
            state = t.get('state', 'unknown')
            progress = t.get('progress', 0)
            result.append({
                'hash': t.get('hash', t.get('infohash_v1', '')),
                'name': t.get('name', 'Unknown'),
                'state': state,
                'progress': round(progress * 100, 1),
                'size': format_size(t.get('size', 0)),
                'size_bytes': t.get('size', 0),
                'downloaded': format_size(t.get('completed', 0)),
                'dl_speed': format_speed(t.get('dlspeed', 0)),
                'dl_speed_raw': t.get('dlspeed', 0),
                'up_speed': format_speed(t.get('upspeed', 0)),
                'up_speed_raw': t.get('upspeed', 0),
                'eta': format_eta(t.get('eta', 0)),
                'eta_raw': t.get('eta', 0),
                'seeds': t.get('num_seeds', 0),
                'peers': t.get('num_leechs', 0),
                'ratio': round(t.get('ratio', 0), 2),
                'added': t.get('added_on', 0),
                'category': t.get('category', ''),
                'save_path': t.get('save_path', ''),
            })
        # Sort: downloading first, then by added time desc
        downloading_states = {'downloading', 'stalledDL', 'metaDL', 'allocating', 'queuedDL'}
        result.sort(key=lambda x: (
            0 if x['state'] in downloading_states else 1,
            -x['added']
        ))
        return jsonify({'torrents': result})
    except Exception as e:
        logger.error(f"Torrents error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/torrents/<torrent_hash>/pause', methods=['POST'])
def api_pause(torrent_hash):
    client = get_qb()
    if not client:
        return jsonify({'error': 'Not connected'}), 500
    try:
        client.pause(torrent_hash)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/torrents/<torrent_hash>/resume', methods=['POST'])
def api_resume(torrent_hash):
    client = get_qb()
    if not client:
        return jsonify({'error': 'Not connected'}), 500
    try:
        client.resume(torrent_hash)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/torrents/<torrent_hash>', methods=['DELETE'])
def api_delete_torrent(torrent_hash):
    client = get_qb()
    if not client:
        return jsonify({'error': 'Not connected'}), 500
    try:
        delete_files = request.args.get('files', 'false') == 'true'
        if delete_files:
            client.delete_permanently(torrent_hash)
        else:
            client.delete(torrent_hash)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/autodl')
def api_autodl_list():
    queries = load_json(QUERIES_FILE, [])
    return jsonify({'queries': queries})


@app.route('/api/autodl', methods=['POST'])
def api_autodl_add():
    data = request.get_json()
    if not data or not data.get('query'):
        return jsonify({'error': 'Missing query'}), 400
    query = data['query'].strip()
    queries = load_json(QUERIES_FILE, [])
    if query in queries:
        return jsonify({'error': 'Query already exists'}), 409
    queries.append(query)
    save_json(QUERIES_FILE, queries)
    return jsonify({'success': True, 'queries': queries})


@app.route('/api/autodl', methods=['DELETE'])
def api_autodl_remove():
    data = request.get_json()
    if not data or not data.get('query'):
        return jsonify({'error': 'Missing query'}), 400
    query = data['query'].strip()
    queries = load_json(QUERIES_FILE, [])
    if query not in queries:
        return jsonify({'error': 'Query not found'}), 404
    queries.remove(query)
    save_json(QUERIES_FILE, queries)
    return jsonify({'success': True, 'queries': queries})


@app.route('/api/downloaded')
def api_downloaded():
    downloaded = load_json(DOWNLOADED_FILE, [])
    return jsonify({'items': downloaded})


@app.route('/api/downloaded/clear', methods=['POST'])
def api_downloaded_clear():
    save_json(DOWNLOADED_FILE, [])
    return jsonify({'success': True})


@app.route('/api/storage')
def api_storage():
    paths = {
        'Movies': config.storage.movies_path,
        'Shows': config.storage.other_path,
    }
    result = {}
    for label, path in paths.items():
        try:
            usage = shutil.disk_usage(path)
            result[label] = {
                'total': format_size(usage.total),
                'used': format_size(usage.used),
                'free': format_size(usage.free),
                'percent': round(usage.used / usage.total * 100, 1),
            }
        except Exception:
            result[label] = {'error': f'Cannot access {path}'}
    return jsonify(result)


if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════╗
    ║         Daisy Dashboard v1.0          ║
    ╚═══════════════════════════════════════╝

    → http://0.0.0.0:8888
    """)
    app.run(host='0.0.0.0', port=8888, debug=False)
