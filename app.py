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
from shapely.geometry import Polygon as ShpPolygon, MultiPolygon as ShpMultiPolygon, Point as ShpPoint
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
        "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
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
PATHS_FILE = os.path.join(DATA_DIR, 'paths.json')

def _ensure_data_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(REFUGES_FILE):
        with open(REFUGES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"refuges": []}, f)
    if not os.path.exists(PATHS_FILE):
        with open(PATHS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"paths": []}, f)

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


# -----------------------------
# Path persistence utilities
# -----------------------------
def _read_paths() -> List[Dict[str, Any]]:
    _ensure_data_file()
    try:
        with open(PATHS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            paths = data.get('paths', [])
            if isinstance(paths, list):
                return paths
            return []
    except Exception as e:
        logger.error(f"Failed to read paths: {e}")
        return []


def _write_paths(paths: List[Dict[str, Any]]):
    """Write paths atomically to avoid corruption."""
    _ensure_data_file()
    tmp_path = PATHS_FILE + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({"paths": paths}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, PATHS_FILE)
    except Exception as e:
        logger.error(f"Failed to write paths: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _coerce_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _find_refuge_containing_point(lat: float | None, lng: float | None):
    """Return the first refuge whose polygon covers the given lat/lng."""
    lat_val = _coerce_float(lat)
    lng_val = _coerce_float(lng)
    if lat_val is None or lng_val is None:
        return None

    try:
        pt = ShpPoint(lng_val, lat_val)
    except Exception:
        return None

    refuges = _read_refuges()
    for refuge in refuges:
        poly = refuge.get('polygon')
        if not poly or not isinstance(poly, dict):
            continue
        try:
            geom = _make_valid_polygonal(shapely_shape(poly))
        except Exception:
            continue
        try:
            if geom.is_empty:
                continue
            if geom.covers(pt) or geom.contains(pt):
                return refuge
        except Exception:
            try:
                buffered = geom.buffer(0)
                if buffered.covers(pt):
                    return refuge
            except Exception:
                continue
    return None


def _group_paths_by_refuge(paths: List[Dict[str, Any]], refuges: List[Dict[str, Any]]):
    """Group paths by refuge using a set of path names for quick lookup."""
    id_index = {r.get('id'): r for r in refuges if isinstance(r.get('id'), int)}
    name_index = {(r.get('name') or '').strip().lower(): r for r in refuges if isinstance(r.get('name'), str)}
    grouped = {}

    for p in paths:
        rid = p.get('refuge_id')
        rname = (p.get('refuge_name') or '').strip()
        if rid is None and rname:
            match = name_index.get(rname.lower())
            if match:
                rid = match.get('id')
        if rid is None:
            continue
        key = str(rid)
        entry = grouped.setdefault(key, {
            "refuge_id": rid,
            "refuge_name": id_index.get(rid, {}).get('name') or rname,
            "path_names": set()
        })
        name_val = (p.get('name') or '').strip()
        if name_val:
            entry["path_names"].add(name_val)

    # Convert sets to sorted lists for JSON serialization
    for entry in grouped.values():
        entry["path_names"] = sorted(entry["path_names"])
    return list(grouped.values())


@app.route('/api/paths', methods=['GET'])
def list_paths():
    try:
        paths = _read_paths()
        refuges = _read_refuges()
        grouped = _group_paths_by_refuge(paths, refuges)
        return jsonify({"status": "success", "paths": paths, "paths_by_refuge": grouped})
    except Exception as e:
        logger.error(f"Failed to list paths: {e}")
        return jsonify({"status": "error", "message": "Failed to list paths"}), 500


@app.route('/api/paths', methods=['POST'])
def create_path():
    try:
        payload = request.json or {}
        name = str(payload.get('name', '')).strip()
        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        paths = _read_paths()
        next_id = 1
        try:
            if paths:
                next_id = max(int(p.get('id', 0) or 0) for p in paths) + 1
        except Exception:
            next_id = len(paths) + 1

        new_path = {
            "id": next_id,
            "name": name,
            # Default tuple/list container for future coordinates
            "points": [],
            # Inline markers (legacy field)
            "markers": [],
            # Popup posts keyed by point index: { "<i>": {caption,image_url,lat,lng,point_index} }
            "pathname_pups": {},
            # Refuge association for quick grouping/search
            "refuge_id": None,
            "refuge_name": None
        }
        paths.append(new_path)
        _write_paths(paths)
        return jsonify({"status": "success", "path": new_path}), 201
    except Exception as e:
        logger.error(f"Failed to create path: {e}")
        return jsonify({"status": "error", "message": "Failed to create path"}), 500


@app.route('/api/paths/<int:path_id>', methods=['PUT'])
def update_path(path_id: int):
    try:
        payload = request.json or {}
        name = str(payload.get('name', '')).strip()
        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        points = payload.get('points', [])
        markers = payload.get('markers', [])
        pathname_pups = payload.get('pathname_pups', {})
        if points is None:
            points = []
        if markers is None:
            markers = []
        if not isinstance(pathname_pups, dict):
            pathname_pups = {}

        if not isinstance(points, list) or not points:
            return jsonify({"status": "error", "message": "Path must include at least one point"}), 400

        end_point = points[-1] if isinstance(points[-1], dict) else {}
        end_lat = _coerce_float(end_point.get('lat') if isinstance(end_point, dict) else None)
        end_lng = _coerce_float(end_point.get('lng') if isinstance(end_point, dict) else None)
        if end_lat is None or end_lng is None:
            return jsonify({"status": "error", "message": "Endpoint coordinates are missing"}), 400

        matched_refuge = _find_refuge_containing_point(end_lat, end_lng)
        if not matched_refuge:
            return jsonify({"status": "error", "message": "Path endpoint must be inside a refuge area"}), 400

        paths = _read_paths()
        updated = False
        for p in paths:
            if int(p.get('id', 0) or 0) == path_id:
                p['name'] = name
                p['points'] = points
                p['markers'] = markers
                p['pathname_pups'] = pathname_pups
                p['refuge_id'] = matched_refuge.get('id')
                p['refuge_name'] = matched_refuge.get('name')
                updated = True
                break

        if not updated:
            return jsonify({"status": "error", "message": "Path not found"}), 404

        _write_paths(paths)
        return jsonify({"status": "success", "path": next((p for p in paths if int(p.get('id', 0) or 0) == path_id), None)})
    except Exception as e:
        logger.error(f"Failed to update path {path_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to update path"}), 500


@app.route('/api/paths/<int:path_id>/popups', methods=['POST'])
def add_path_popup(path_id: int):
    try:
        payload = request.json or {}
        caption = str(payload.get('caption', '')).strip()
        image_url = str(payload.get('image_url', '')).strip()
        point_index = payload.get('point_index')
        lat = payload.get('lat')
        lng = payload.get('lng')

        if not caption and not image_url:
            return jsonify({"status": "error", "message": "Caption or image required"}), 400

        paths = _read_paths()
        target = None
        for p in paths:
            if int(p.get('id', 0) or 0) == path_id:
                target = p
                break

        if target is None:
            return jsonify({"status": "error", "message": "Path not found"}), 404

        points = target.get('points')
        if not isinstance(points, list) or not points:
            return jsonify({"status": "error", "message": "Path has no points to attach popup"}), 400

        def _coerce_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _nearest_point_idx(points_list, ref_lat, ref_lng):
            if ref_lat is None or ref_lng is None:
                return None
            best_idx = None
            best_dist = None
            for idx, pt in enumerate(points_list):
                if not isinstance(pt, dict):
                    continue
                p_lat = _coerce_float(pt.get('lat'))
                p_lng = _coerce_float(pt.get('lng'))
                if p_lat is None or p_lng is None:
                    continue
                dist = (p_lat - ref_lat) ** 2 + (p_lng - ref_lng) ** 2
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_idx = idx
            return best_idx

        lat_val = _coerce_float(lat)
        lng_val = _coerce_float(lng)

        idx_val = None
        try:
            candidate_idx = int(point_index)
            if 0 <= candidate_idx < len(points):
                idx_val = candidate_idx
        except (TypeError, ValueError):
            idx_val = None

        if idx_val is None:
            idx_val = _nearest_point_idx(points, lat_val, lng_val)

        if idx_val is None:
            return jsonify({"status": "error", "message": "Unable to attach popup to a path point"}), 400

        attach_point = points[idx_val] if 0 <= idx_val < len(points) else {}
        attach_lat = _coerce_float(attach_point.get('lat') if isinstance(attach_point, dict) else None)
        attach_lng = _coerce_float(attach_point.get('lng') if isinstance(attach_point, dict) else None)
        if attach_lat is None or attach_lng is None:
            attach_lat = lat_val
            attach_lng = lng_val

        if attach_lat is None or attach_lng is None:
            return jsonify({"status": "error", "message": "Popup location is missing coordinates"}), 400

        pups = target.get('pathname_pups')
        if not isinstance(pups, dict):
            pups = {}

        key = str(idx_val)
        pups[key] = {
            "caption": caption,
            "image_url": image_url,
            "point_index": idx_val,
            "lat": attach_lat,
            "lng": attach_lng
        }
        target['pathname_pups'] = pups
        _write_paths(paths)
        return jsonify({"status": "success", "popup": pups.get(key), "path": target}), 201
    except Exception as e:
        logger.error(f"Failed to add popup to path {path_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to add popup"}), 500


def _make_valid_polygonal(geom: BaseGeometry) -> BaseGeometry:
    if geom is None:
        return ShpMultiPolygon([])
    g = geom
    try:
        try:
            from shapely import make_valid as _make_valid
        except Exception:
            try:
                from shapely.validation import make_valid as _make_valid
            except Exception:
                _make_valid = None
        if not g.is_valid:
            g = _make_valid(g) if _make_valid else g.buffer(0)
    except Exception:
        try:
            g = g.buffer(0)
        except Exception:
            pass

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


def _safe_unary_union(geoms: List[BaseGeometry]) -> BaseGeometry:
    cleaned: List[BaseGeometry] = []
    for geom in geoms:
        if not geom:
            continue
        try:
            if geom.is_empty:
                continue
        except Exception:
            continue
        try:
            cleaned_geom = _make_valid_polygonal(geom)
        except Exception:
            cleaned_geom = geom
        if cleaned_geom and not cleaned_geom.is_empty:
            cleaned.append(cleaned_geom)

    if not cleaned:
        return ShpMultiPolygon([])
    if len(cleaned) == 1:
        return cleaned[0]

    try:
        result = unary_union(cleaned)
        if not result.is_valid:
            result = result.buffer(0)
        return _make_valid_polygonal(result)
    except Exception as exc:
        logger.warning(f"unary_union failed; falling back to pairwise union: {exc}")
        result = cleaned[0]
        for geom in cleaned[1:]:
            if not result or result.is_empty:
                result = geom
                continue
            try:
                merged = result.union(geom)
            except Exception:
                try:
                    merged = unary_union([result, geom])
                except Exception as pair_exc:
                    logger.warning(f"Pairwise union failed, skipping overlay: {pair_exc}")
                    continue
            if not merged.is_valid:
                try:
                    merged = merged.buffer(0)
                except Exception:
                    pass
            result = _make_valid_polygonal(merged)
        return result

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


def _count_components(geom: BaseGeometry) -> int:
    """Return the number of polygonal components in a geometry."""
    if geom is None:
        return 0
    try:
        if geom.is_empty:
            return 0
    except Exception:
        return 0

    geom_type = getattr(geom, "geom_type", None)
    if geom_type == "Polygon":
        return 1
    if geom_type == "MultiPolygon":
        try:
            return sum(1 for g in geom.geoms if g and not g.is_empty)
        except Exception:
            geoms = getattr(geom, "geoms", []) or []
            return len(geoms)
    if geom_type == "GeometryCollection":
        count = 0
        try:
            for g in geom.geoms:
                count += _count_components(g)
        except Exception:
            pass
        return count
    return 0


def _subtract_overlay_from_other_refuges(
    refuges: List[Dict[str, Any]],
    target_id: int,
    overlay_geom: BaseGeometry
) -> tuple[List[Dict[str, Any]], List[int]]:
    """Subtract overlay geometry from all non-target refuges."""
    if overlay_geom is None:
        return refuges, []

    try:
        overlay_geom = _make_valid_polygonal(overlay_geom)
    except Exception:
        pass

    if overlay_geom is None or overlay_geom.is_empty:
        return refuges, []

    updated_refuges: List[Dict[str, Any]] = []
    removed_ids: List[int] = []

    for refuge in refuges:
        if not isinstance(refuge, dict):
            updated_refuges.append(refuge)
            continue

        refuge_id = refuge.get('id')
        if refuge_id == target_id:
            updated_refuges.append(refuge)
            continue

        polygon = refuge.get('polygon')
        if not polygon or polygon.get('type') not in ('Polygon', 'MultiPolygon'):
            updated_refuges.append(refuge)
            continue

        try:
            geom = _make_valid_polygonal(shapely_shape(polygon))
        except Exception as exc:
            logger.warning(f"Skipping refuge {refuge_id} during overlap subtraction: invalid geometry ({exc})")
            updated_refuges.append(refuge)
            continue

        if geom.is_empty or not geom.intersects(overlay_geom):
            updated_refuges.append(refuge)
            continue

        try:
            new_geom = _safe_difference(geom, overlay_geom)
            new_geom = _make_valid_polygonal(new_geom)
        except Exception as exc:
            logger.warning(f"Failed to subtract overlay from refuge {refuge_id}: {exc}")
            updated_refuges.append(refuge)
            continue

        if new_geom.is_empty or (hasattr(new_geom, 'area') and new_geom.area <= 0):
            if refuge_id is not None:
                removed_ids.append(refuge_id)
                logger.info(f"Overlay subtraction removed refuge {refuge_id} entirely; deleting refuge.")
            continue

        if new_geom.geom_type not in ("Polygon", "MultiPolygon"):
            logger.warning(f"Overlay subtraction for refuge {refuge_id} produced {new_geom.geom_type}; skipping update.")
            updated_refuges.append(refuge)
            continue

        try:
            geojson = shapely_mapping(new_geom)
        except Exception as exc:
            logger.warning(f"Failed to serialize geometry for refuge {refuge_id}: {exc}")
            updated_refuges.append(refuge)
            continue

        refuge['polygon'] = {
            "type": geojson.get("type"),
            "coordinates": geojson.get("coordinates")
        }
        updated_refuges.append(refuge)

    return updated_refuges, removed_ids



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
        new_geom = _make_valid_polygonal(new_geom)

        # Collect existing geometries (support Polygon and MultiPolygon already saved)
        existing_geoms: List[BaseGeometry] = []
        contained_geoms: List[BaseGeometry] = []
        for r in refuges:
            try:
                g = r.get('polygon')
                if g and isinstance(g, dict) and g.get('type') in ("Polygon", "MultiPolygon"):
                    existing_geom = _make_valid_polygonal(shapely_shape(g))
                    try:
                        if existing_geom is None or existing_geom.is_empty:
                            continue
                    except Exception:
                        continue

                    existing_geoms.append(existing_geom)

                    # Detect refuges that are fully inside the newly drawn refuge so we can carve holes
                    try:
                        if new_geom.covers(existing_geom):
                            contained_geoms.append(existing_geom)
                        else:
                            # Retry with a validity buffer to avoid precision edge cases
                            buffered_new = new_geom.buffer(0)
                            if buffered_new.covers(existing_geom):
                                contained_geoms.append(existing_geom)
                    except Exception:
                        try:
                            buffered_new = new_geom.buffer(0)
                            if buffered_new.covers(existing_geom):
                                contained_geoms.append(existing_geom)
                        except Exception:
                            pass
            except Exception:
                continue

        # Subtract overlaps from the new geometry
        try:
            # Start from original geometry
            result_geom = new_geom
            # First carve out any existing refuges that are fully contained so those areas remain untouched
            if contained_geoms:
                try:
                    contained_union = _safe_unary_union(contained_geoms)
                    if contained_union and not contained_union.is_empty:
                        result_geom = _safe_difference(result_geom, contained_union)
                        logger.info(f"New refuge minus {len(contained_geoms)} contained refuges.")
                except Exception as exc:
                    logger.warning(f"Failed contained-refuge subtraction via union: {exc}")
                    for cg in contained_geoms:
                        try:
                            if result_geom.is_empty:
                                break
                            result_geom = _safe_difference(result_geom, cg)
                        except Exception:
                            continue
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

        # If subtraction resulted in MultiPolygon, keep only the part containing the first vertex
        if result_geom.geom_type == "MultiPolygon":
            try:
                # Get the first vertex from the original polygon
                first_coords = polygon['coordinates'][0][0]  # [lng, lat]
                from shapely.geometry import Point
                first_point = Point(first_coords[0], first_coords[1])
                
                # Find which polygon contains the first vertex
                kept_polygon = None
                for poly in result_geom.geoms:
                    if poly.contains(first_point) or poly.boundary.distance(first_point) < 1e-9:
                        kept_polygon = poly
                        break
                
                # If no polygon contains the first point exactly, find the nearest one
                if kept_polygon is None:
                    min_distance = float('inf')
                    for poly in result_geom.geoms:
                        dist = poly.distance(first_point)
                        if dist < min_distance:
                            min_distance = dist
                            kept_polygon = poly
                
                if kept_polygon and not kept_polygon.is_empty:
                    result_geom = kept_polygon
                    logger.info(f"MultiPolygon result after subtraction: kept only polygon containing first vertex")
                else:
                    return jsonify({"status": "error", "message": "Could not determine which part to keep after subtraction"}), 400
            except Exception as e:
                logger.warning(f"Failed to filter MultiPolygon by first vertex: {e}")
                # Continue with the full MultiPolygon if filtering fails

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


@app.route('/api/refuges/<int:refuge_id>', methods=['PUT'])
def update_refuge(refuge_id: int):
    """Update an existing refuge's name. Only name updates are supported for now."""
    try:
        payload = request.get_json(force=True) or {}
        new_name = (payload.get('name') or '').strip()
        if not new_name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        refuges = _read_refuges()
        # Find target refuge
        target = None
        for r in refuges:
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                target = r
                break
        if not target:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404

        # Ensure unique name (case-insensitive) across other refuges
        lower_name = new_name.lower()
        for r in refuges:
            if r is target:
                continue
            if isinstance(r.get('name'), str) and r.get('name', '').strip().lower() == lower_name:
                return jsonify({"status": "error", "message": "A refuge with this name already exists"}), 409

        target['name'] = new_name
        _write_refuges(refuges)
        return jsonify({"status": "success", "refuge": target})
    except Exception as e:
        logger.error(f"Error updating refuge: {e}")
        return jsonify({"status": "error", "message": "Failed to update refuge"}), 500


@app.route('/api/refuges/<int:refuge_id>', methods=['DELETE'])
def delete_refuge(refuge_id: int):
    """Delete a refuge by id."""
    try:
        refuges = _read_refuges()
        idx = None
        for i, r in enumerate(refuges):
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                idx = i
                break
        if idx is None:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404

        removed = refuges.pop(idx)
        _write_refuges(refuges)
        return jsonify({"status": "success", "deleted": removed})
    except Exception as e:
        logger.error(f"Error deleting refuge: {e}")
        return jsonify({"status": "error", "message": "Failed to delete refuge"}), 500


@app.route('/api/refuges/<int:refuge_id>/adjoin', methods=['POST'])
def adjoin_overlays(refuge_id: int):
    """Adjoin (union) overlay polygons to an existing refuge."""
    try:
        payload = request.get_json(force=True) or {}
        overlays = payload.get('overlays', [])
        
        if not overlays or not isinstance(overlays, list):
            return jsonify({"status": "error", "message": "No overlays provided"}), 400
        
        refuges = _read_refuges()
        
        # Find target refuge
        target = None
        target_idx = None
        for i, r in enumerate(refuges):
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                target = r
                target_idx = i
                break
        
        if not target:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404
        
        # Get current refuge geometry
        try:
            current_geom = shapely_shape(target['polygon'])
        except Exception:
            return jsonify({"status": "error", "message": "Stored refuge geometry is invalid"}), 500
        current_geom = _make_valid_polygonal(current_geom)
        if current_geom.is_empty:
            return jsonify({"status": "error", "message": "Stored refuge geometry is empty"}), 500
        
        # Convert overlays to Shapely geometries
        overlay_geoms = []
        for overlay in overlays:
            try:
                if overlay.get('type') == 'Polygon' and overlay.get('coordinates'):
                    geom = shapely_shape(overlay)
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    overlay_geoms.append(geom)
            except Exception as e:
                logger.warning(f"Failed to parse overlay: {e}")
                continue
        
        if not overlay_geoms:
            return jsonify({"status": "error", "message": "No valid overlays to adjoin"}), 400
        
        # Before processing overlays, subtract overlapping unrelated refuges from them
        # Collect all unrelated refuge geometries
        unrelated_refuge_geoms: List[BaseGeometry] = []
        for r in refuges:
            if isinstance(r.get('id'), int) and r.get('id') != refuge_id:
                try:
                    g = r.get('polygon')
                    if g and isinstance(g, dict) and g.get('type') in ("Polygon", "MultiPolygon"):
                        unrelated_geom = _make_valid_polygonal(shapely_shape(g))
                        if not unrelated_geom.is_empty:
                            unrelated_refuge_geoms.append(unrelated_geom)
                except Exception:
                    continue
        
        # Subtract unrelated refuges from each overlay
        if unrelated_refuge_geoms:
            try:
                unrelated_union = _safe_unary_union(unrelated_refuge_geoms)
                if not unrelated_union.is_empty:
                    cleaned_overlay_geoms = []
                    for overlay_geom in overlay_geoms:
                        try:
                            # Subtract unrelated refuges from this overlay
                            cleaned_geom = _safe_difference(overlay_geom, unrelated_union)
                            cleaned_geom = _make_valid_polygonal(cleaned_geom)
                            if not cleaned_geom.is_empty and cleaned_geom.area > 0:
                                cleaned_overlay_geoms.append(cleaned_geom)
                            else:
                                logger.info(f"Overlay completely overlapped with unrelated refuges; skipping.")
                        except Exception as exc:
                            logger.warning(f"Failed to subtract unrelated refuges from overlay: {exc}")
                            # Keep the original overlay if subtraction fails
                            cleaned_overlay_geoms.append(overlay_geom)
                    overlay_geoms = cleaned_overlay_geoms
            except Exception as exc:
                logger.warning(f"Failed to create union of unrelated refuges: {exc}")
        
        if not overlay_geoms:
            return jsonify({"status": "error", "message": "All overlays completely overlap with other refuges"}), 400
        
        # Union all geometries together
        try:
            all_geoms = [current_geom] + overlay_geoms
            result_geom = _safe_unary_union(all_geoms)
            
            # Ensure result is valid
            if not result_geom.is_valid:
                result_geom = result_geom.buffer(0)
            
            if result_geom.is_empty or result_geom.area <= 0:
                return jsonify({"status": "error", "message": "Resulting geometry is empty"}), 400
        except Exception as e:
            logger.error(f"Error adjoining geometries: {e}")
            return jsonify({"status": "error", "message": "Failed to adjoin geometries"}), 500
        
        # Convert back to GeoJSON
        result_geojson = shapely_mapping(result_geom)
        
        # Update refuge with new geometry
        target['polygon'] = {
            "type": result_geojson.get("type"),
            "coordinates": result_geojson.get("coordinates")
        }
        
        refuges[target_idx] = target
        
        # Now subtract the adjoined overlays from other refuges
        # Create union of the overlay geometries that were actually applied
        try:
            overlays_union = _safe_unary_union(overlay_geoms)
            overlays_union = _make_valid_polygonal(overlays_union)
            if not overlays_union.is_empty:
                refuges, removed_refuge_ids = _subtract_overlay_from_other_refuges(
                    refuges,
                    target.get('id'),
                    overlays_union
                )
                if removed_refuge_ids:
                    logger.info(f"Removed refuges after cross-refuge subtraction in adjoin: {removed_refuge_ids}")
                
                # Re-find target index after potential removals
                target_idx = None
                for idx, refuge in enumerate(refuges):
                    if isinstance(refuge, dict) and refuge.get('id') == target.get('id'):
                        target_idx = idx
                        break
                if target_idx is None:
                    refuges.append(target)
                    target_idx = len(refuges) - 1
                
                refuges[target_idx] = target
        except Exception as exc:
            logger.warning(f"Failed to subtract overlays from other refuges: {exc}")
        
        _write_refuges(refuges)
        
        return jsonify({"status": "success", "refuge": target})
    except Exception as e:
        logger.error(f"Error adjoining overlays: {e}")
        return jsonify({"status": "error", "message": "Failed to adjoin overlays"}), 500


@app.route('/api/refuges/<int:refuge_id>/subtract', methods=['POST'])
def subtract_overlays(refuge_id: int):
    """Subtract overlay polygons from an existing refuge."""
    try:
        payload = request.get_json(force=True) or {}
        overlays = payload.get('overlays', [])
        
        if not overlays or not isinstance(overlays, list):
            return jsonify({"status": "error", "message": "No overlays provided"}), 400
        
        refuges = _read_refuges()
        
        # Find target refuge
        target = None
        target_idx = None
        for i, r in enumerate(refuges):
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                target = r
                target_idx = i
                break
        
        if not target:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404
        
        # Get current refuge geometry
        try:
            current_geom = shapely_shape(target['polygon'])
        except Exception:
            return jsonify({"status": "error", "message": "Stored refuge geometry is invalid"}), 500
        current_geom = _make_valid_polygonal(current_geom)
        if current_geom.is_empty:
            return jsonify({"status": "error", "message": "Stored refuge geometry is empty"}), 500
        
        # Convert overlays to Shapely geometries
        overlay_geoms = []
        for overlay in overlays:
            try:
                if overlay.get('type') == 'Polygon' and overlay.get('coordinates'):
                    geom = shapely_shape(overlay)
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    overlay_geoms.append(geom)
            except Exception as e:
                logger.warning(f"Failed to parse overlay: {e}")
                continue
        
        if not overlay_geoms:
            return jsonify({"status": "error", "message": "No valid overlays to subtract"}), 400
        
        # Subtract all overlay geometries from current geometry
        try:
            result_geom = current_geom
            for overlay_geom in overlay_geoms:
                result_geom = _safe_difference(result_geom, overlay_geom)
            
            # Ensure result is valid
            if not result_geom.is_valid:
                result_geom = result_geom.buffer(0)
            
            if result_geom.is_empty or result_geom.area <= 0:
                return jsonify({"status": "error", "message": "Subtraction would remove entire refuge"}), 400
        except Exception as e:
            logger.error(f"Error subtracting geometries: {e}")
            return jsonify({"status": "error", "message": "Failed to subtract geometries"}), 500
        
        # Convert back to GeoJSON
        result_geojson = shapely_mapping(result_geom)
        
        # Update refuge with new geometry
        target['polygon'] = {
            "type": result_geojson.get("type"),
            "coordinates": result_geojson.get("coordinates")
        }
        
        refuges[target_idx] = target
        _write_refuges(refuges)
        
        return jsonify({"status": "success", "refuge": target})
    except Exception as e:
        logger.error(f"Error subtracting overlays: {e}")
        return jsonify({"status": "error", "message": "Failed to subtract overlays"}), 500


@app.route('/api/refuges/<int:refuge_id>/validate-overlay', methods=['POST'])
def validate_overlay_operation(refuge_id: int):
    """Validate an overlay before applying it during editing."""
    try:
        payload = request.get_json(force=True) or {}
        overlay_payload = payload.get('overlay')
        operation = (payload.get('operation') or '').strip().lower()

        if operation != 'subtract':
            return jsonify({"status": "error", "message": "Unsupported operation"}), 400

        if not overlay_payload or overlay_payload.get('type') not in ('Polygon', 'MultiPolygon'):
            return jsonify({"status": "error", "message": "Invalid overlay geometry"}), 400

        refuges = _read_refuges()
        target = None
        for r in refuges:
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                target = r
                break

        if not target:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404

        try:
            current_geom = shapely_shape(target['polygon'])
        except Exception:
            return jsonify({"status": "error", "message": "Stored refuge geometry is invalid"}), 500
        current_geom = _make_valid_polygonal(current_geom)
        if current_geom.is_empty:
            return jsonify({"status": "error", "message": "Stored refuge geometry is empty"}), 500

        try:
            overlay_geom = shapely_shape(overlay_payload)
        except Exception:
            return jsonify({"status": "error", "message": "Invalid overlay geometry"}), 400
        overlay_geom = _make_valid_polygonal(overlay_geom)
        if overlay_geom.is_empty:
            return jsonify({"status": "error", "message": "Overlay has no area"}), 400

        result_geom = _safe_difference(current_geom, overlay_geom)
        result_geom = _make_valid_polygonal(result_geom)
        if not result_geom.is_valid:
            result_geom = result_geom.buffer(0)
        if result_geom.is_empty or result_geom.area <= 0:
            return jsonify({"status": "error", "message": "Overlay subtraction would remove entire refuge"}), 400

        if _count_components(result_geom) > 1:
            return jsonify({
                "status": "error",
                "code": "REFUGE_FRAGMENTATION",
                "message": "Overlay subtraction would fragment the refuge"
            }), 400

        return jsonify({"status": "success", "fragmenting": False})
    except Exception as e:
        logger.error(f"Error validating overlay: {e}")
        return jsonify({"status": "error", "message": "Failed to validate overlay"}), 500


@app.route('/api/refuges/<int:refuge_id>/apply-overlays', methods=['POST'])
def apply_overlay_changes(refuge_id: int):
    """Apply both adjoin and subtract overlay polygons to an existing refuge in a single transaction."""
    try:
        payload = request.get_json(force=True) or {}
        adjoin_payload = payload.get('adjoin') or []
        subtract_payload = payload.get('subtract') or []

        if not isinstance(adjoin_payload, list) or not isinstance(subtract_payload, list):
            return jsonify({"status": "error", "message": "Invalid overlays payload"}), 400

        if not adjoin_payload and not subtract_payload:
            return jsonify({"status": "error", "message": "No overlays provided"}), 400

        refuges = _read_refuges()
        target = None
        target_idx = None
        for i, r in enumerate(refuges):
            if isinstance(r.get('id'), int) and r.get('id') == refuge_id:
                target = r
                target_idx = i
                break

        if not target or target_idx is None:
            return jsonify({"status": "error", "message": "Refuge not found"}), 404

        try:
            current_geom = shapely_shape(target['polygon'])
        except Exception:
            return jsonify({"status": "error", "message": "Stored refuge geometry is invalid"}), 500
        current_geom = _make_valid_polygonal(current_geom)
        if current_geom.is_empty:
            return jsonify({"status": "error", "message": "Stored refuge geometry is empty"}), 500

        def _to_geometries(items: List[Any]) -> List[BaseGeometry]:
            geoms: List[BaseGeometry] = []
            for overlay in items:
                try:
                    if isinstance(overlay, dict) and overlay.get('type') in ('Polygon', 'MultiPolygon') and overlay.get('coordinates'):
                        geom = shapely_shape(overlay)
                        geom = _make_valid_polygonal(geom)
                        if not geom.is_empty and geom.geom_type in ("Polygon", "MultiPolygon"):
                            geoms.append(geom)
                except Exception as exc:
                    logger.warning(f"Failed to parse overlay during apply-overlays: {exc}")
            return geoms

        adjoin_geoms = _to_geometries(adjoin_payload)
        subtract_geoms = _to_geometries(subtract_payload)

        # Before processing adjoin overlays, subtract overlapping unrelated refuges from them
        if adjoin_geoms:
            # Collect all unrelated refuge geometries
            unrelated_refuge_geoms: List[BaseGeometry] = []
            for r in refuges:
                if isinstance(r.get('id'), int) and r.get('id') != refuge_id:
                    try:
                        g = r.get('polygon')
                        if g and isinstance(g, dict) and g.get('type') in ("Polygon", "MultiPolygon"):
                            unrelated_geom = _make_valid_polygonal(shapely_shape(g))
                            if not unrelated_geom.is_empty:
                                unrelated_refuge_geoms.append(unrelated_geom)
                    except Exception:
                        continue
            
            # Subtract unrelated refuges from each adjoin overlay
            if unrelated_refuge_geoms:
                try:
                    unrelated_union = _safe_unary_union(unrelated_refuge_geoms)
                    if not unrelated_union.is_empty:
                        cleaned_adjoin_geoms = []
                        for adjoin_geom in adjoin_geoms:
                            try:
                                # Subtract unrelated refuges from this overlay
                                cleaned_geom = _safe_difference(adjoin_geom, unrelated_union)
                                cleaned_geom = _make_valid_polygonal(cleaned_geom)
                                if not cleaned_geom.is_empty and cleaned_geom.area > 0:
                                    cleaned_adjoin_geoms.append(cleaned_geom)
                                else:
                                    logger.info(f"Adjoin overlay completely overlapped with unrelated refuges; skipping.")
                            except Exception as exc:
                                logger.warning(f"Failed to subtract unrelated refuges from adjoin overlay: {exc}")
                                # Keep the original overlay if subtraction fails
                                cleaned_adjoin_geoms.append(adjoin_geom)
                        adjoin_geoms = cleaned_adjoin_geoms
                except Exception as exc:
                    logger.warning(f"Failed to create union of unrelated refuges: {exc}")

        adjoin_union_for_others: BaseGeometry | None = None
        if adjoin_geoms:
            try:
                adjoin_union_for_others = _safe_unary_union(adjoin_geoms)
                adjoin_union_for_others = _make_valid_polygonal(adjoin_union_for_others)
                if adjoin_union_for_others.is_empty:
                    adjoin_union_for_others = None
            except Exception as exc:
                logger.warning(
                    f"Failed to prepare adjoin overlay union for cross-refuge subtraction: {exc}"
                )
                adjoin_union_for_others = None

        result_geom = current_geom

        if adjoin_geoms:
            try:
                result_geom = _safe_unary_union([result_geom] + adjoin_geoms)
                if not result_geom.is_valid:
                    result_geom = result_geom.buffer(0)
                if result_geom.is_empty or result_geom.area <= 0:
                    return jsonify({"status": "error", "message": "Resulting geometry is empty after adjoin"}), 400

                # After adjoining, drop any pieces that are no longer directly connected
                # to the original refuge area. This prevents "split" islands from being kept.
                if result_geom.geom_type == "MultiPolygon":
                    connected_parts: list[BaseGeometry] = []
                    for poly in result_geom.geoms:
                        try:
                            if poly.is_empty:
                                continue
                            # Consider a part connected if it intersects or touches the original refuge.
                            if poly.intersects(current_geom) or poly.touches(current_geom):
                                connected_parts.append(poly)
                        except Exception:
                            continue

                    if connected_parts:
                        if len(connected_parts) == 1:
                            result_geom = connected_parts[0]
                        else:
                            result_geom = _safe_unary_union(connected_parts)
                        # Re-validate after filtering
                        result_geom = _make_valid_polygonal(result_geom)
                        if result_geom.is_empty or result_geom.area <= 0:
                            return jsonify(
                                {"status": "error", "message": "Resulting geometry became empty after filtering disconnected parts"}
                            ), 400
                    else:
                        # No part of the adjoined result is connected to the original refuge;
                        # discard adjoin effects and keep the original geometry.
                        logger.info(
                            "All adjoin overlay parts are disconnected from original refuge; "
                            "discarding adjoin changes for this operation."
                        )
                        result_geom = current_geom
            except Exception as exc:
                logger.error(f"Error adjoining geometries in apply-overlays: {exc}")
                return jsonify({"status": "error", "message": "Failed to adjoin overlays"}), 500
        if subtract_geoms:
            try:
                for overlay_geom in subtract_geoms:
                    result_geom = _safe_difference(result_geom, overlay_geom)
                result_geom = _make_valid_polygonal(result_geom)
                if not result_geom.is_valid:
                    result_geom = result_geom.buffer(0)
                if result_geom.is_empty or result_geom.area <= 0:
                    return jsonify({"status": "error", "message": "Overlay subtraction would remove entire refuge"}), 400

                if _count_components(result_geom) > 1:
                    return jsonify({
                        "status": "error",
                        "code": "REFUGE_FRAGMENTATION",
                        "message": "Overlay subtraction would fragment the refuge"
                    }), 400

            except Exception as exc:
                logger.error(f"Error subtracting geometries in apply-overlays: {exc}")
                return jsonify({"status": "error", "message": "Failed to subtract overlays"}), 500

        result_geom = _make_valid_polygonal(result_geom)
        if result_geom.is_empty or result_geom.geom_type not in ("Polygon", "MultiPolygon"):
            return jsonify({"status": "error", "message": "Resulting geometry is not a polygon"}), 400

        result_geojson = shapely_mapping(result_geom)
        target['polygon'] = {
            "type": result_geojson.get("type"),
            "coordinates": result_geojson.get("coordinates")
        }

        refuges[target_idx] = target

        if adjoin_union_for_others is not None:
            refuges, removed_refuge_ids = _subtract_overlay_from_other_refuges(
                refuges,
                target.get('id'),
                adjoin_union_for_others
            )
            if removed_refuge_ids:
                logger.info(f"Removed refuges after cross-refuge subtraction: {removed_refuge_ids}")

            target_idx = None
            for idx, refuge in enumerate(refuges):
                if isinstance(refuge, dict) and refuge.get('id') == target.get('id'):
                    target_idx = idx
                    break
            if target_idx is None:
                refuges.append(target)
                target_idx = len(refuges) - 1

            refuges[target_idx] = target

        _write_refuges(refuges)

        return jsonify({"status": "success", "refuge": target})
    except Exception as e:
        logger.error(f"Error applying overlay changes: {e}")
        return jsonify({"status": "error", "message": "Failed to apply overlay changes"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500
