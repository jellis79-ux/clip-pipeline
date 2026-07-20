"""
Downloads a YouTube episode with yt-dlp (which also parses chapter
markers straight out of the description/native chapters), then cuts
selected chapter time-ranges into vertical (9:16) clips with ffmpeg.

Metadata fetching is split from the actual video download so the
pipeline can check the episode description for a pre-cut asset link
(see precut_assets.py) before committing to a full episode download —
Shawn Ryan Show provides pre-cut vertical reels per episode, which are
higher quality and cheaper to process than self-cutting full episodes.
"""
import subprocess
from pathlib import Path

import yt_dlp

WORKDIR = Path("/tmp/clip_work")


def get_episode_metadata(video_url: str) -> dict:
    """Fetches episode metadata WITHOUT downloading the video — title,
    description (used to look for a pre-cut asset folder link), chapters,
    and duration."""
    ydl_opts = {"quiet": True, "noprogress": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    return {
        "title": info.get("title", ""),
        "description": info.get("description", "") or "",
        "chapters": info.get("chapters") or [],
        "duration": float(info.get("duration") or 0),
    }


def download_video(video_url: str) -> Path:
    """Downloads the full episode video. Only called when no pre-cut
    asset link was found in the description — this is the expensive path."""
    WORKDIR.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(WORKDIR / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
    return Path(ydl.prepare_filename(info)).with_suffix(".mp4")


def expand_to_min_duration(
    start: float, end: float, total_duration: float, min_duration: float, max_duration: float
) -> tuple[float, float]:
    """Widens a [start, end] window so it meets min_duration (needed for
    TikTok's Creator Rewards Program, which pays $0 on anything under 60s),
    capped at max_duration and the video's actual bounds. Expands forward
    first (keeps the hook at the front), then backward if still short."""
    duration = end - start
    if duration >= min_duration:
        return start, min(end, start + max_duration)

    needed = min(min_duration, max_duration) - duration
    new_end = min(end + needed, total_duration) if total_duration else end + needed
    gained_forward = new_end - end
    remaining = needed - gained_forward
    new_start = max(start - remaining, 0) if remaining > 0 else start
    return new_start, new_end


def cut_vertical_clip(
    source: Path, start: float, end: float, out_path: Path, max_duration: float = 90.0
) -> Path:
    """Cuts [start, end] from source and center-crops to 9:16 for
    Shorts/Reels/TikTok. Caps clip length at max_duration as a final
    safety net (the caller should already have sized the window with
    expand_to_min_duration)."""
    duration = min(end - start, max_duration)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Center-crop to 9:16: crop width to match 9:16 of the height, centered.
    vf = "crop=ih*9/16:ih,scale=1080:1920"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(source),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def cleanup(source: Path) -> None:
    """Removes the large source download once clips are cut, so the
    GitHub Actions runner doesn't fill up on disk."""
    if source.exists():
        source.unlink()
