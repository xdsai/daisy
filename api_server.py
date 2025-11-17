"""
Flask API server for Daisy torrent downloader.
Provides HTTP endpoints for searching and downloading torrents.
"""

import logging
import os
import secrets
import threading
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

from config import Config
from torrent_search import search_torrents
from media_processor import MediaProcessor


# Setup logging
logging.basicConfig(
    filename='api.log',
    filemode='a',
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for iOS Shortcuts

# Load config
config = Config.load()

# API Key for basic security
# Set this in environment variable or config file
API_KEY = os.getenv('DAISY_API_KEY', 'your-secret-key-change-this')

# Global media processor instance
media_processor: Optional[MediaProcessor] = None


def require_api_key(f):
    """Decorator to require API key in requests."""
    def decorated_function(*args, **kwargs):
        # Check for API key in header or query param
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

        if api_key != API_KEY:
            logger.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized - invalid API key'}), 401

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'daisy-api',
        'version': '2.0'
    })


@app.route('/search', methods=['GET', 'POST'])
@require_api_key
def search():
    """
    Search for torrents.

    Query params (GET) or JSON body (POST):
    - q or query: Search query (required)
    - type: Media type (anime, movie, show, auto) - default: auto
    - limit: Max results - default: 20

    Returns:
    - List of torrent results with metadata
    """
    try:
        # Get parameters from either GET or POST
        if request.method == 'POST':
            data = request.get_json() or {}
            query = data.get('q') or data.get('query')
            media_type = data.get('type', 'auto')
            limit = int(data.get('limit', 20))
        else:
            query = request.args.get('q') or request.args.get('query')
            media_type = request.args.get('type', 'auto')
            limit = int(request.args.get('limit', 20))

        if not query:
            return jsonify({'error': 'Missing query parameter'}), 400

        logger.info(f"Search request: query={query}, type={media_type}, limit={limit}")

        # Perform search
        results = search_torrents(query, media_type, limit)

        logger.info(f"Found {len(results)} results for query: {query}")

        return jsonify({
            'success': True,
            'query': query,
            'count': len(results),
            'results': results
        })

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/download', methods=['POST'])
@require_api_key
def download():
    """
    Download a torrent.

    JSON body:
    - magnet: Magnet link (required)
    - name: Show/movie name (required)
    - type: Media type (movie, show, other) - default: other

    Returns:
    - Download status (responds immediately, doesn't wait for completion)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Missing JSON body'}), 400

        magnet = data.get('magnet')
        name = data.get('name')
        media_type = data.get('type', 'other')

        if not magnet:
            return jsonify({'error': 'Missing magnet parameter'}), 400

        if not name:
            return jsonify({'error': 'Missing name parameter'}), 400

        if media_type not in ['movie', 'show', 'other']:
            return jsonify({'error': 'Invalid type (must be movie, show, or other)'}), 400

        logger.info(f"Download request: name={name}, type={media_type}")

        # Initialize processor if needed
        global media_processor
        if media_processor is None:
            media_processor = MediaProcessor(config)
            if not media_processor.connect():
                logger.error("Failed to connect to qBittorrent")
                return jsonify({
                    'success': False,
                    'error': 'Failed to connect to qBittorrent'
                }), 500

        # Start download in background thread - respond immediately
        thread = threading.Thread(
            target=media_processor.process,
            args=(media_type, name, magnet),
            daemon=True
        )
        thread.start()

        logger.info(f"Download thread started for: {name}")

        # Respond immediately - don't wait for download to finish
        return jsonify({
            'success': True,
            'message': f'Download started: {name}',
            'name': name,
            'type': media_type,
            'note': 'Download running in background - check Discord for completion'
        })

    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/quick-download', methods=['POST'])
@require_api_key
def quick_download():
    """
    Search and download in one step.

    JSON body:
    - query: Search query (required)
    - name: Custom name for the download (optional, uses query if not provided)
    - type: Media type (movie, show, other, auto) - default: auto
    - index: Which search result to download (0-based) - default: 0 (best match)

    Returns:
    - Download status with selected torrent info
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Missing JSON body'}), 400

        query = data.get('query')
        name = data.get('name') or query
        media_type = data.get('type', 'auto')
        index = int(data.get('index', 0))

        if not query:
            return jsonify({'error': 'Missing query parameter'}), 400

        logger.info(f"Quick download: query={query}, index={index}")

        # Search for torrents
        results = search_torrents(query, media_type, limit=10)

        if not results:
            return jsonify({
                'success': False,
                'error': 'No torrents found for query'
            }), 404

        if index >= len(results):
            return jsonify({
                'success': False,
                'error': f'Index {index} out of range (found {len(results)} results)'
            }), 400

        # Get selected torrent
        selected = results[index]
        magnet = selected['magnet']

        # Determine media type if auto
        if media_type == 'auto':
            # Use the suggested type from search result
            media_type = selected.get('suggested_type', 'other')

        logger.info(f"Selected torrent: {selected['title']} (type: {media_type})")

        # Initialize processor if needed
        global media_processor
        if media_processor is None:
            media_processor = MediaProcessor(config)
            if not media_processor.connect():
                return jsonify({
                    'success': False,
                    'error': 'Failed to connect to qBittorrent'
                }), 500

        # Start download in background thread - respond immediately
        thread = threading.Thread(
            target=media_processor.process,
            args=(media_type, name, magnet),
            daemon=True
        )
        thread.start()

        logger.info(f"Download thread started for: {name}")

        return jsonify({
            'success': True,
            'message': f'Download started',
            'selected_torrent': selected,
            'name': name,
            'type': media_type,
            'note': 'Download running in background - check Discord for completion'
        })

    except Exception as e:
        logger.error(f"Quick download error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/status', methods=['GET'])
@require_api_key
def status():
    """
    Get download status and system info.

    Returns:
    - Current downloads
    - Storage info
    """
    try:
        global media_processor

        if media_processor is None:
            media_processor = MediaProcessor(config)
            if not media_processor.connect():
                return jsonify({
                    'success': False,
                    'error': 'Failed to connect to qBittorrent'
                }), 500

        # Get torrents from qBittorrent
        torrents = media_processor.download_manager.get_torrents()

        # Get storage info
        storage = media_processor.file_ops.get_storage_report()

        # Format torrent info
        active_downloads = []
        for t in torrents:
            if t.get('state') in ['downloading', 'stalledDL', 'metaDL', 'allocating']:
                active_downloads.append({
                    'name': t.get('name'),
                    'progress': round(t.get('progress', 0) * 100, 1),
                    'state': t.get('state'),
                    'download_speed': t.get('dlspeed', 0),
                    'eta': t.get('eta', 0)
                })

        return jsonify({
            'success': True,
            'active_downloads': active_downloads,
            'storage': storage,
            'total_torrents': len(torrents)
        })

    except Exception as e:
        logger.error(f"Status error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500


def main():
    """Run the Flask server."""
    # Get host and port from environment or use defaults
    host = os.getenv('DAISY_HOST', '0.0.0.0')
    port = int(os.getenv('DAISY_PORT', 5000))
    debug = os.getenv('DAISY_DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting Daisy API server on {host}:{port}")
    logger.info(f"API Key: {API_KEY[:4]}...{API_KEY[-4:]}")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                  Daisy API Server v2.0                   ║
╚══════════════════════════════════════════════════════════╝

Server running on: http://{host}:{port}

Endpoints:
  GET  /health                  - Health check
  GET  /search?q=<query>        - Search torrents
  POST /download                - Download torrent by magnet
  POST /quick-download          - Search and download best match
  GET  /status                  - Get download status

API Key: {API_KEY}

Set environment variable DAISY_API_KEY to change the API key.
""")

    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
