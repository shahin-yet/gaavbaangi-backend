from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import logging
import json
from urllib.parse import urlsplit
from typing import List, Dict, Any
from shapely.geometry import shape as shapely_shape, mapping as shapely_mapping
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon as ShpPolygon, MultiPolygon as ShpMultiPolygon
from shapely.ops import unary_union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom dotenv loader with better error handling
def safe_load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        # Try to load using python-dotenv if available
        try:
            from dotenv import load_dotenv
            load_dotenv()
            logger.info("Loaded environment from .env using dotenv package")
            return True
        except ImportError:
            logger.info("python-dotenv not installed, using manual method")
            
        # Manual fallback - read .env file directly
        if os.path.exists(env_path):
            try:
                # Try UTF-8 first
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
                logger.info("Manually loaded environment from .env using UTF-8")
                return True
            except UnicodeDecodeError:
                # Try other encodings
                for encoding in ['latin1', 'utf-16', 'utf-16-le', 'utf-16-be']:
                    try:
                        with open(env_path, 'r', encoding=encoding) as f:
                            for line in f:
                                line = line.strip()
                                if not line or line.startswith('#'):
                                    continue
                                if '=' in line:
                                    key, value = line.split('=', 1)
                                    os.environ[key.strip()] = value.strip()
                        logger.info(f"Manually loaded environment from .env using {encoding}")
                        return True
                    except:
                        continue
                
                # If all encodings fail, manually set environment variables
                logger.warning("Failed to read .env file with various encodings. Setting defaults.")
    except Exception as e:
        logger.error(f"Error loading environment variables: {str(e)}")
    
    # Hard-coded fallback for crucial variables
    if 'FRONTEND_URL' not in os.environ:
        os.environ['FRONTEND_URL'] = 'https://shahin-yet.github.io/gaavbaangi-frontend'
        logger.info("Set FRONTEND_URL from default value")
    
    return False

# Load environment variables
safe_load_dotenv()

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
logger.info(f"Frontend origin set to: {frontend_origin}")

if frontend_origin:
    cors_origins = frontend_origin
else:
    # Fallback for initial bring-up; allows any origin to reach API
    cors_origins = "*"
    logger.warning("No FRONTEND_URL found, CORS set to allow any origin")

CORS(app, resources={
    r"/api/*": {
        "origins": cors_origins,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "env": {
            "frontend_url": os.getenv('FRONTEND_URL'),
            "cors_origin": cors_origins
        }
    })

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
# Allow overriding data directory via environment for persistent disks
DATA_DIR = os.getenv('DATA_DIR') or os.path.join(os.path.dirname(__file__), 'data')
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
    """Write refuges atomically to avoid corruption across restarts.
    Writes to a temporary file in the same directory and then replaces.
    """
    _ensure_data_file()
    tmp_path = REFUGES_FILE + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({"refuges": refuges}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, REFUGES_FILE)
    except Exception as e:
        logger.error(f"Failed to write refuges: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
def _safe_unary_union(geoms: List[BaseGeometry]) -> BaseGeometry:
    try:
        return unary_union([g for g in geoms if g and not g.is_empty])
    except Exception:
        try:
            # Attempt to validify components and union again
            fixed = []
            for g in geoms:
                if not g or g.is_empty:
                    continue
                try:
                    gg = g if g.is_valid else g.buffer(0)
                    fixed.append(gg)
                except Exception:
                    continue
            return unary_union(fixed) if fixed else ShpMultiPolygon([])
        except Exception:
            # Last resort: pick the first geometry
            return geoms[0] if geoms else ShpMultiPolygon([])

def _safe_difference(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    try:
        return a.difference(b)
    except Exception:
        try:
            aa = a if a.is_valid else a.buffer(0)
            bb = b if b.is_valid else b.buffer(0)
            return aa.difference(bb)
        except Exception:
            # Optional overlay fallback on Shapely 2
            try:
                from shapely import overlay
                return overlay(a, b, how='difference')
            except Exception:
                # Give up and return original to allow subsequent checks to fail gracefully
                return a



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
        # Name validation (required and unique, case-insensitive)
        incoming_name = (payload.get('name') or '').strip()
        if not incoming_name:
            return jsonify({"status": "error", "message": "Name is required"}), 400
        lower_incoming = incoming_name.lower()
        if any(isinstance(r.get('name'), str) and r.get('name', '').strip().lower() == lower_incoming for r in refuges):
            return jsonify({"status": "error", "message": "A refuge with this name already exists"}), 409

        # Build new geometry and subtract overlaps with existing refuges
        try:
            new_geom: BaseGeometry = shapely_shape(polygon)
        except Exception:
            return jsonify({"status": "error", "message": "Invalid polygon coordinates"}), 400

        # Make geometry valid (fix self-intersections) and keep only polygonal parts
        def _make_valid_polygonal(geom: BaseGeometry) -> BaseGeometry:
            g = geom
            try:
                # Prefer shapely.make_valid if available; fallback to buffer(0)
                try:
                    from shapely import make_valid as _make_valid  # Shapely >=2
                except Exception:
                    try:
                        from shapely.validation import make_valid as _make_valid  # older
                    except Exception:
                        _make_valid = None
                if not g.is_valid:
                    g = _make_valid(g) if _make_valid else g.buffer(0)
            except Exception:
                try:
                    g = g.buffer(0)
                except Exception:
                    pass

            # Extract only polygonal components if we got a GeometryCollection
            try:
                if g.geom_type in ("Polygon", "MultiPolygon"):
                    return g
                if hasattr(g, 'geoms'):
                    polygon_parts = []
                    for part in g.geoms:
                        if part.geom_type in ("Polygon", "MultiPolygon"):
                            polygon_parts.append(part)
                    if polygon_parts:
                        try:
                            return unary_union(polygon_parts)
                        except Exception:
                            # Last resort: flatten to MultiPolygon
                            flat = []
                            for p in polygon_parts:
                                if p.geom_type == "Polygon":
                                    flat.append(p)
                                elif p.geom_type == "MultiPolygon":
                                    flat.extend(list(p.geoms))
                            if flat:
                                return ShpMultiPolygon(flat)
                return g
            except Exception:
                return g

        new_geom = _make_valid_polygonal(new_geom)

        # Collect existing geometries (support Polygon and MultiPolygon already saved)
        existing_geoms: List[BaseGeometry] = []
        for r in refuges:
            try:
                g = r.get('polygon')
                if g and isinstance(g, dict) and g.get('type') in ("Polygon", "MultiPolygon"):
                    existing_geoms.append(_make_valid_polygonal(shapely_shape(g)))
            except Exception:
                continue

        # Subtract overlaps from the new geometry
        try:
            # Start from original geometry
            result_geom = new_geom
            if existing_geoms:
                # First, try a fast union-based subtraction
                try:
                    existing_union = _safe_unary_union(existing_geoms)
                    result_geom = _safe_difference(result_geom, existing_union)
                except Exception:
                    # If union fails for any reason, continue with sequential subtraction below
                    pass

                # Robust fallback: sequentially subtract each existing geometry as well.
                # This ensures that if the union step above partially failed, all overlaps
                # are still removed.
                for eg in existing_geoms:
                    try:
                        if not result_geom.is_empty:
                            result_geom = _safe_difference(result_geom, eg)
                    except Exception:
                        # _safe_difference already has internal fallbacks; call again to be safe
                        result_geom = _safe_difference(result_geom, eg)
        except Exception:
            return jsonify({"status": "error", "message": "Failed to process geometry"}), 400

        # Ensure the result has area and is of polygonal type
        if result_geom.is_empty or result_geom.area <= 0:
            return jsonify({"status": "error", "message": "Refuge overlaps existing areas completely; nothing to save"}), 400
        # If geometry collection slipped through, keep only polygonal parts
        if result_geom.geom_type not in ("Polygon", "MultiPolygon"):
            result_geom = _make_valid_polygonal(result_geom)
            if result_geom.is_empty or result_geom.geom_type not in ("Polygon", "MultiPolygon"):
                return jsonify({"status": "error", "message": "Resulting geometry is not a polygon"}), 400

        # Convert back to GeoJSON geometry
        result_geojson = shapely_mapping(result_geom)

        new_refuge = {
            "id": (refuges[-1]['id'] + 1) if refuges and isinstance(refuges[-1].get('id'), int) else 1,
            "name": incoming_name,
            "polygon": {
                "type": result_geojson.get("type"),
                "coordinates": result_geojson.get("coordinates")
            }
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
