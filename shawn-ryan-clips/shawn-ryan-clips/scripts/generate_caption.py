"""
Uses the Anthropic API to:
  1. Pick the N most clip-worthy chapters from an episode's chapter list
     (self-cut fallback path), OR write captions directly from a
     transcript for Shawn Ryan Show's own pre-cut reels (preferred path,
     see precut_assets.py)
  2. Write a hook/caption for each — the required link-back AND the
     @shawnryanshow/@shawnryan762 tag are appended by this script from a
     template, never left to the model, so neither can be dropped or
     reworded away. Both are required by Shawn Ryan Show's stated terms
     for reposting/monetizing clips.
  3. Write a short original commentary line for each — this is the thin
     layer of added creative value platforms look for before they'll
     approve monetization on clipped/reposted content (YouTube's reused-
     content review and TikTok's Creator Rewards originality check both
     penalize pure re-uploads with nothing added).
"""
import json
import os

import anthropic

MODEL = "claude-sonnet-4-6"


def _build_caption(hook: str, show_tag: str, link_back: str) -> str:
    """Every caption must carry both the tag and the link-back per
    Shawn Ryan Show's stated reposting/monetization terms — built here
    from a template rather than left to the model."""
    return f"{hook}\n\n{show_tag}\n{link_back}"


def pick_clips_and_captions(
    episode_title: str,
    chapters: list[dict],
    clips_per_episode: int,
    link_back: str,
    show_tag: str,
    min_duration: float = 60.0,
) -> list[dict]:
    """Returns a list of {start_time, end_time, title, caption,
    youtube_title, commentary} dicts, chosen from `chapters`."""
    if not chapters:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    chapter_list_str = "\n".join(
        f"{i}: \"{c['title']}\" ({c['start_time']:.0f}s-{c['end_time']:.0f}s, "
        f"{c['end_time'] - c['start_time']:.0f}s long)"
        for i, c in enumerate(chapters)
    )

    prompt = f"""You are picking short-form video clips from a long podcast episode
for social media (Instagram Reels, TikTok, YouTube Shorts).

Episode title: {episode_title}

Chapters (index: "title" (start-end in seconds, length)):
{chapter_list_str}

Pick the {clips_per_episode} chapters most likely to work as standalone,
attention-grabbing short clips (surprising claims, strong emotion, a
concrete story beat, or a clear payoff) rather than intros, sponsor
reads, or scene-setting. The hook must land in the first sentence —
completion rate in the opening 1-2 seconds is the single biggest driver
of distribution on every platform.

Prefer chapters that are already close to {min_duration:.0f}-90 seconds
long, or ones where the surrounding chapters would extend well, since
clips shorter than {min_duration:.0f}s don't qualify for TikTok's paid
Creator Rewards Program at all.

For each pick, provide three different pieces of text:
- "hook": a short, punchy line for TikTok/Instagram/X captions (under
  200 characters, no hashtags, no link — just the hook)
- "youtube_title": a keyword-rich, search-optimized title for YouTube
  Shorts (under 100 characters) — YouTube indexes titles for search and
  content can surface for months, so phrase it like a headline someone
  would search for, not a caption
- "commentary": a one-sentence original take, reaction, or framing on
  this specific moment (e.g. "This is the part most people get wrong
  about ___" or "Worth sitting with this for a second") — displayed as
  a text card over the first few seconds of the clip. This must be your
  own observation, not a repeat of the hook or chapter title, since it's
  what platforms look for as evidence of added creative value on top of
  the source material.

Respond ONLY with a JSON array, no other text, no markdown fences:
[
  {{"chapter_index": <int>, "hook": "<short punchy caption line>", "youtube_title": "<search-optimized title>", "commentary": "<one-sentence original take>"}}
]
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        picks = json.loads(text)
    except json.JSONDecodeError:
        return []

    clips = []
    for pick in picks:
        idx = pick.get("chapter_index")
        if idx is None or idx >= len(chapters):
            continue
        chapter = chapters[idx]
        clips.append(
            {
                "start_time": chapter["start_time"],
                "end_time": chapter["end_time"],
                "title": chapter["title"],
                "caption": _build_caption(pick["hook"], show_tag, link_back),
                "youtube_title": pick.get("youtube_title", chapter["title"])[:100],
                "commentary": pick.get("commentary", ""),
            }
        )
    return clips


def write_caption_for_transcript(
    filename: str, transcript_text: str, link_back: str, show_tag: str
) -> dict:
    """For Shawn Ryan Show's own pre-cut reels: there's no chapter
    metadata to pick from (the clip is already chosen/framed by his
    team), so this writes the hook/title/commentary directly from the
    clip's own transcript. Returns {caption, youtube_title, commentary}."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""This is a transcript of a short pre-cut clip from The Shawn Ryan Show,
provided by the show itself for creators to repost. The clip is already
selected and framed — your job is only to write the accompanying text.

Filename: {filename}
Transcript: {transcript_text[:3000]}

Provide three pieces of text:
- "hook": a short, punchy caption line for TikTok/Instagram/X (under 200
  characters, no hashtags, no link)
- "youtube_title": a keyword-rich, search-optimized title for YouTube
  Shorts (under 100 characters)
- "commentary": a one-sentence original take or reaction to this specific
  moment, in your own words — not a restatement of the transcript. This
  is the added creative value platforms look for before approving
  monetization on reposted content.

Respond ONLY with a JSON object, no other text, no markdown fences:
{{"hook": "...", "youtube_title": "...", "commentary": "..."}}
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        pick = json.loads(text)
    except json.JSONDecodeError:
        pick = {"hook": filename, "youtube_title": filename[:100], "commentary": ""}

    return {
        "caption": _build_caption(pick.get("hook", filename), show_tag, link_back),
        "youtube_title": pick.get("youtube_title", filename)[:100],
        "commentary": pick.get("commentary", ""),
    }
