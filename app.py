from flask import Flask, request, jsonify
from flask_cors import CORS
import os
try:
    from dotenv import load_dotenv  # optional in PA WSGI shim
except Exception:
    def load_dotenv(*_args, **_kwargs):
        return False
from urllib.parse import urlsplit
import logging
import json
from typing import List, Dict, Any
 

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure CORS: allow only the configured frontend origin
def _extract_origin(url_value: str | None) -> str | None:
    if not url_value:
        return None
    url_value = url_value.strip()
    try:
        parts = urlsplit(url_value)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
        return url_value.rstrip('/')
    except Exception:
        return url_value.rstrip('/')

frontend_origin = _extract_origin(os.getenv('FRONTEND_URL'))

if frontend_origin:
    cors_origins = frontend_origin
else:
    # Fallback for initial bring-up; allows any origin to reach API
    cors_origins = "*"

CORS(app, resources={
    r"/api/*": {
        "origins": cors_origins,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

 

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

@app.route('/api/init-data', methods=['POST'])
def init_data():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        # Here you can add validation for Telegram WebApp init data
        logger.info("Received init data request")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error processing init data: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400


# -----------------------------
# Refuge persistence utilities
# -----------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
REFUGES_FILE = os.path.join(DATA_DIR, 'refuges.json')

def _ensure_data_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(REFUGES_FILE):
        with open(REFUGES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"refuges": []}, f)

def _read_refuges() -> List[Dict[str, Any]]:
    _ensure_data_file()
    try:
        with open(REFUGES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            refuges = data.get('refuges', [])
            if isinstance(refuges, list):
                return refuges
            return []
    except Exception as e:
        logger.error(f"Failed to read refuges: {e}")
        return []

def _write_refuges(refuges: List[Dict[str, Any]]):
    _ensure_data_file()
    try:
        with open(REFUGES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"refuges": refuges}, f)
    except Exception as e:
        logger.error(f"Failed to write refuges: {e}")


@app.route('/api/refuges', methods=['GET'])
def list_refuges():
    try:
        refuges = _read_refuges()
        return jsonify({"status": "success", "refuges": refuges})
    except Exception as e:
        logger.error(f"Error listing refuges: {e}")
        return jsonify({"status": "error", "message": "Failed to list refuges"}), 500


@app.route('/api/refuges', methods=['POST'])
def create_refuge():
    try:
        payload = request.get_json(force=True) or {}
        # Expected format: { name?: str, polygon: { type: 'Polygon', coordinates: [[[lng,lat],...]] } }
        polygon = payload.get('polygon')
        if not polygon or polygon.get('type') != 'Polygon' or not polygon.get('coordinates'):
            return jsonify({"status": "error", "message": "Invalid polygon"}), 400

        refuges = _read_refuges()
        new_refuge = {
            "id": (refuges[-1]['id'] + 1) if refuges and isinstance(refuges[-1].get('id'), int) else 1,
            "name": payload.get('name') or f"Refuge #{len(refuges) + 1}",
            "polygon": polygon
        }
        refuges.append(new_refuge)
        _write_refuges(refuges)
        return jsonify({"status": "success", "refuge": new_refuge}), 201
    except Exception as e:
        logger.error(f"Error creating refuge: {e}")
        return jsonify({"status": "error", "message": "Failed to create refuge"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

 