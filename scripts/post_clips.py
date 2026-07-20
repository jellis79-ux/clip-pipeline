"""
Two steps:
  1. Upload the cut clip as a GitHub Release asset so it has a stable
     public URL (Ayrshare needs a fetchable mediaUrl, not a raw file).
  2. Call Ayrshare's /api/post endpoint to publish that URL + caption
     to every configured platform in one call.

Requires the repo to be public (or Ayrshare/viewers to have access),
since release assets on a private repo aren't publicly fetchable.
"""
import os
import subprocess
from pathlib import Path

import requests

AYRSHARE_ENDPOINT = "https://api.ayrshare.com/api/post"


def upload_release_asset(repo: str, tag: str, file_path: Path) -> str:
    """Creates (or reuses) a release tagged `tag` and uploads file_path
    as an asset. Returns the public download URL."""
    # Create the release if it doesn't already exist (ignore failure if it does).
    subprocess.run(
        ["gh", "release", "create", tag, "--title", tag, "--notes", "Auto-generated clip release"],
        capture_output=True,
    )
    subprocess.run(
        ["gh", "release", "upload", tag, str(file_path), "--clobber"],
        check=True,
        capture_output=True,
    )
    filename = file_path.name
    return f"https://github.com/{repo}/releases/download/{tag}/{filename}"


def post_to_socials(
    media_url: str,
    caption: str,
    platforms: list[str],
    youtube_title: str | None = None,
    subtitle_url: str | None = None,
) -> dict:
    api_key = os.environ["AYRSHARE_API_KEY"]
    payload = {
        "post": caption,
        "platforms": platforms,
        "mediaUrls": [media_url],
        "isVideo": True,
    }

    if "youtube" in platforms:
        # youTubeOptions.title is required by Ayrshare when youtube is a target platform.
        youtube_options = {
            "title": (youtube_title or caption)[:100],
            "shorts": True,  # marks it as a YouTube Short rather than a long-form upload
        }
        if subtitle_url:
            youtube_options["subTitleUrl"] = subtitle_url
            youtube_options["subTitleLanguage"] = "en"
        payload["youTubeOptions"] = youtube_options

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(AYRSHARE_ENDPOINT, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()
