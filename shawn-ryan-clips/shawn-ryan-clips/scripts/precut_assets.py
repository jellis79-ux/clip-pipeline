"""
Shawn Ryan Show provides a public Google Drive folder of pre-cut, raw
vertical reels per episode, linked in the episode description, rather
than requiring clippers to cut their own. These are preferable to
self-cut clips (already vertical, already framed by his team) when
available — this module finds and downloads them, falling back to
self-cutting only when no folder link is present.

Uses the Drive API v3 with a plain API key, which works for files/folders
shared as "Anyone with the link can view" without needing OAuth.
"""
import re
from pathlib import Path

import requests

DRIVE_API = "https://www.googleapis.com/drive/v3"

# Matches drive.google.com/drive/folders/<id> and .../open?id=<id> style links
_FOLDER_URL_RE = re.compile(
    r"drive\.google\.com/(?:drive/folders/|open\?id=|drive/u/\d+/folders/)([a-zA-Z0-9_-]+)"
)


def extract_drive_folder_id(description: str) -> str | None:
    """Returns the first Google Drive folder ID found in the episode
    description, or None if there isn't one."""
    match = _FOLDER_URL_RE.search(description or "")
    return match.group(1) if match else None


def list_folder_videos(folder_id: str, api_key: str) -> list[dict]:
    """Returns [{"id": ..., "name": ...}] for video files in the folder,
    sorted by name (episode folders are typically named/numbered in a
    sensible clip order)."""
    resp = requests.get(
        f"{DRIVE_API}/files",
        params={
            "q": f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false",
            "fields": "files(id,name,mimeType)",
            "key": api_key,
            "pageSize": 100,
        },
        timeout=30,
    )
    resp.raise_for_status()
    files = resp.json().get("files", [])
    return sorted(files, key=lambda f: f["name"])


def download_drive_file(file_id: str, api_key: str, out_path: Path, api_base: str = DRIVE_API) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(
        f"{api_base}/files/{file_id}",
        params={"alt": "media", "key": api_key},
        timeout=300,
        stream=True,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    return out_path
