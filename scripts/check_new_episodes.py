"""
Checks the channel's YouTube RSS feed for episodes that haven't been
processed yet. RSS is used instead of the YouTube Data API because it
requires no API key/quota and is sufficient for "is there a new video".
"""
import json
import os
from pathlib import Path

import feedparser

STATE_PATH = Path(__file__).parent.parent / "state" / "processed_episodes.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"processed_video_ids": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_new_episodes(channel_id: str) -> list[dict]:
    """Returns a list of {video_id, title, url, published} for videos
    in the channel feed that are not yet in state."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)

    state = load_state()
    processed = set(state.get("processed_video_ids", []))

    new_episodes = []
    for entry in feed.entries:
        video_id = entry.yt_videoid
        if video_id in processed:
            continue
        new_episodes.append(
            {
                "video_id": video_id,
                "title": entry.title,
                "url": entry.link,
                "published": entry.published,
            }
        )
    return new_episodes


def mark_processed(video_id: str) -> None:
    state = load_state()
    ids = set(state.get("processed_video_ids", []))
    ids.add(video_id)
    state["processed_video_ids"] = sorted(ids)
    save_state(state)


if __name__ == "__main__":
    channel_id = os.environ["YOUTUBE_CHANNEL_ID"]
    for ep in get_new_episodes(channel_id):
        print(ep)
