"""
Orchestrates the full pipeline for each new episode:
  detect -> check description for Shawn's pre-cut Drive reels ->
    [pre-cut path]  download his reels -> caption from transcript
    [fallback path] download full episode -> pick chapters -> cut
  -> burn captions/commentary -> upload as release asset -> post to
  socials -> mark processed
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from check_new_episodes import get_new_episodes, mark_processed  # noqa: E402
from cut_clips import (  # noqa: E402
    get_episode_metadata,
    download_video,
    cut_vertical_clip,
    expand_to_min_duration,
    cleanup,
)
from precut_assets import extract_drive_folder_id, list_folder_videos, download_drive_file  # noqa: E402
from burn_captions import burn_captions, transcribe  # noqa: E402
from generate_caption import pick_clips_and_captions, write_caption_for_transcript  # noqa: E402
from post_clips import upload_release_asset, post_to_socials  # noqa: E402

CLIP_DIR = Path("/tmp/clip_work/clips")


def process_precut_clip(
    file_info: dict,
    ep: dict,
    link_back: str,
    show_tag: str,
    google_api_key: str,
) -> dict | None:
    """Downloads one of Shawn's pre-cut reels and writes its caption
    from the clip's own transcript. Returns a clip dict compatible with
    the rest of the pipeline, or None on failure."""
    raw_path = CLIP_DIR / f"{ep['video_id']}_{file_info['id']}_raw.mp4"
    try:
        download_drive_file(file_info["id"], google_api_key, raw_path)
    except Exception as e:
        print(f"    Failed to download pre-cut asset {file_info['name']}: {e}")
        return None

    words, transcript_text = transcribe(raw_path)
    caption_data = write_caption_for_transcript(file_info["name"], transcript_text, link_back, show_tag)

    return {
        "raw_path": raw_path,
        "words": words,
        "caption": caption_data["caption"],
        "youtube_title": caption_data["youtube_title"],
        "commentary": caption_data["commentary"],
        "needs_crop": False,  # Shawn's reels are already vertical
    }


def main() -> None:
    channel_id = os.environ["YOUTUBE_CHANNEL_ID"]
    link_back = os.environ["SHOW_LINK_BACK"]
    show_tag = os.environ.get("SHOW_TAG", "@shawnryanshow")
    google_api_key = os.environ.get("GOOGLE_API_KEY", "")
    clips_per_episode = int(os.environ.get("CLIPS_PER_EPISODE", "2"))
    min_clip_duration = float(os.environ.get("MIN_CLIP_DURATION", "60"))
    max_clip_duration = float(os.environ.get("MAX_CLIP_DURATION", "90"))
    platforms = [p.strip() for p in os.environ["TARGET_PLATFORMS"].split(",")]
    repo = os.environ["GITHUB_REPOSITORY"]  # provided automatically in Actions, e.g. "user/repo"
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    if dry_run:
        print("=== DRY RUN: clips will be generated and uploaded as release assets, "
              "but NOT posted to social platforms, and episodes will NOT be marked "
              "processed (so a real run afterward will still pick them up). ===")

    episodes = get_new_episodes(channel_id)
    if not episodes:
        print("No new episodes found.")
        return

    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    for ep in episodes:
        print(f"Processing: {ep['title']} ({ep['video_id']})")
        try:
            meta = get_episode_metadata(ep["url"])
        except Exception as e:
            print(f"  Failed to fetch metadata for {ep['video_id']}: {e}")
            continue

        release_tag = f"{ep['video_id']}-dryrun" if dry_run else ep["video_id"]
        clips_to_process = []  # list of clip dicts, either pre-cut or self-cut
        source_video_path = None  # only set/cleaned up on the self-cut path

        folder_id = extract_drive_folder_id(meta["description"]) if google_api_key else None

        if folder_id:
            print(f"  Found pre-cut asset folder ({folder_id}) — using Shawn's own reels.")
            try:
                files = list_folder_videos(folder_id, google_api_key)[:clips_per_episode]
            except Exception as e:
                print(f"  Failed to list Drive folder, falling back to self-cut: {e}")
                files = []

            for file_info in files:
                clip = process_precut_clip(file_info, ep, link_back, show_tag, google_api_key)
                if clip:
                    clips_to_process.append(clip)

        if not clips_to_process:
            if folder_id:
                print("  No usable pre-cut assets found, falling back to self-cut.")
            if not meta["chapters"]:
                print(f"  No chapters found for {ep['video_id']}, skipping (nothing to clip from).")
                if not dry_run:
                    mark_processed(ep["video_id"])
                continue

            picked = pick_clips_and_captions(
                meta["title"], meta["chapters"], clips_per_episode, link_back, show_tag,
                min_duration=min_clip_duration,
            )
            if not picked:
                print(f"  Claude returned no clip picks for {ep['video_id']}, skipping.")
                if not dry_run:
                    mark_processed(ep["video_id"])
                continue

            try:
                source_video_path = download_video(ep["url"])
            except Exception as e:
                print(f"  Failed to download episode {ep['video_id']}: {e}")
                continue

            for i, pick in enumerate(picked):
                start, end = expand_to_min_duration(
                    pick["start_time"], pick["end_time"], meta["duration"],
                    min_clip_duration, max_clip_duration,
                )
                raw_path = CLIP_DIR / f"{ep['video_id']}_clip{i}_raw.mp4"
                cut_vertical_clip(source_video_path, start, end, raw_path, max_duration=max_clip_duration)
                clips_to_process.append(
                    {
                        "raw_path": raw_path,
                        "words": None,  # burn_captions will transcribe it fresh
                        "caption": pick["caption"],
                        "youtube_title": pick["youtube_title"],
                        "commentary": pick["commentary"],
                        "needs_crop": False,  # already cropped by cut_vertical_clip
                    }
                )

        for i, clip in enumerate(clips_to_process):
            raw_path = clip["raw_path"]
            captioned_path = CLIP_DIR / f"{ep['video_id']}_out{i}.mp4"
            srt_path = CLIP_DIR / f"{ep['video_id']}_out{i}.srt"
            try:
                burn_captions(
                    raw_path, captioned_path, srt_path,
                    commentary=clip.get("commentary"), words=clip.get("words"),
                )

                media_url = upload_release_asset(repo, release_tag, captioned_path)
                subtitle_url = None
                if srt_path.exists() and srt_path.stat().st_size > 0:
                    subtitle_url = upload_release_asset(repo, release_tag, srt_path)

                if dry_run:
                    print(f"  [DRY RUN] Clip {i} uploaded for preview: {media_url}")
                    print(f"  [DRY RUN] Would post to platforms: {platforms}")
                    print(f"  [DRY RUN] Caption:\n{clip['caption']}")
                    print(f"  [DRY RUN] YouTube title: {clip.get('youtube_title')}")
                else:
                    result = post_to_socials(
                        media_url,
                        clip["caption"],
                        platforms,
                        youtube_title=clip.get("youtube_title"),
                        subtitle_url=subtitle_url,
                    )
                    print(f"  Posted clip {i}: {result}")
            except Exception as e:
                print(f"  Failed on clip {i} for {ep['video_id']}: {e}")
            finally:
                for p in (raw_path, captioned_path, srt_path):
                    if p.exists():
                        p.unlink()

        if source_video_path:
            cleanup(source_video_path)

        if not dry_run:
            mark_processed(ep["video_id"])
        else:
            print(f"  [DRY RUN] {ep['video_id']} NOT marked processed — a real run will still pick it up.")


if __name__ == "__main__":
    main()
