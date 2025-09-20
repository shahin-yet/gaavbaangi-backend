"""
PythonAnywhere deployment helper

NOTE: This file is used ONLY for PythonAnywhere deployment via CI/CD.
It uploads minimal backend files and triggers a webapp reload.
"""

import os
import sys
import pathlib
from urllib.parse import quote

import requests


# Required environment variables (to be set as GitHub Actions secrets)
PA_USERNAME = os.environ.get("PA_USERNAME")
PA_API_TOKEN = os.environ.get("PA_API_TOKEN")
PA_WEBAPP_DOMAIN = os.environ.get("PA_WEBAPP_DOMAIN")  # e.g. "shahinyet.pythonanywhere.com"
PA_TARGET_DIR = os.environ.get("PA_TARGET_DIR")        # optional; default: /home/<username>/mysite
PA_API_BASE_URL = os.environ.get("PA_API_BASE_URL", "https://www.pythonanywhere.com")  # EU: https://eu.pythonanywhere.com


def _require_env():
    required = {
        "PA_USERNAME": PA_USERNAME,
        "PA_API_TOKEN": PA_API_TOKEN,
        "PA_WEBAPP_DOMAIN": PA_WEBAPP_DOMAIN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _headers():
    return {"Authorization": f"Token {PA_API_TOKEN}"}


def api_file_put(abs_target_path: str, data: bytes):
    url = f"{PA_API_BASE_URL}/api/v0/user/{PA_USERNAME}/files/path/{quote(abs_target_path)}"
    r = requests.put(url, headers=_headers(), data=data)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed for {abs_target_path}: {r.status_code} {r.text}")


def api_reload():
    domain = PA_WEBAPP_DOMAIN
    if domain.startswith("https://"):
        domain = domain.replace("https://", "").strip("/")
    url = f"{PA_API_BASE_URL}/api/v0/user/{PA_USERNAME}/webapps/{quote(domain)}/reload/"
    r = requests.post(url, headers=_headers())
    if r.status_code != 200:
        raise RuntimeError(f"Reload failed: {r.status_code} {r.text}")


def main():
    _require_env()

    # Default target to the standard PythonAnywhere Flask folder for first-time deploys
    target_dir = PA_TARGET_DIR or f"/home/{PA_USERNAME}/mysite"

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    backend_dir = pathlib.Path(__file__).resolve().parent

    # Collect uploads
    uploads: list[tuple[str, bytes]] = []

    # app.py (required)
    app_py = backend_dir / "app.py"
    if app_py.exists():
        uploads.append(("app.py", app_py.read_bytes()))

    # requirements.txt (optional)
    req = backend_dir / "requirements.txt"
    if req.exists():
        uploads.append(("requirements.txt", req.read_bytes()))

    # .env: prefer .env; else use env and rename to .env
    dot_env = backend_dir / ".env"
    env_template = backend_dir / "env"
    if dot_env.exists():
        uploads.append((".env", dot_env.read_bytes()))
    elif env_template.exists():
        uploads.append((".env", env_template.read_bytes()))

    # Generate flask_app.py wrapper for default PA Flask app
    flask_app_py = (
        "from dotenv import load_dotenv\n"
        "load_dotenv()\n"
        "from app import app as application\n"
    ).encode("utf-8")
    uploads.append(("flask_app.py", flask_app_py))

    if not uploads:
        print("No backend files found to upload.")
        sys.exit(0)

    print(f"Uploading {len(uploads)} files to {target_dir} ...")
    for name, data in uploads:
        dest = os.path.join(target_dir, name)
        api_file_put(dest, data)
        print(f"  uploaded: {name}")

    print("Triggering webapp reload ...")
    api_reload()
    print("Deployment completed.")


if __name__ == "__main__":
    main()