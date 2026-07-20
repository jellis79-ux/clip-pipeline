"""
Transcribes a cut clip with faster-whisper (CPU, no GPU needed) and
burns in short, punchy captions (2-4 words per caption, matching the
style that performs best on TikTok/Reels/Shorts) using ffmpeg's
subtitles filter. Also writes a standard SRT file alongside, which
YouTube can use as a real captions track for accessibility/SEO.
"""
from pathlib import Path

from faster_whisper import WhisperModel

_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        # "small" balances speed and accuracy well on a CPU-only runner;
        # bump to "base" if runs are timing out, or "medium" for more accuracy.
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def _chunk_words(words: list, max_words: int = 3) -> list[dict]:
    """Groups word-level timestamps into short caption chunks."""
    chunks = []
    for i in range(0, len(words), max_words):
        group = words[i : i + max_words]
        chunks.append(
            {
                "start": group[0].start,
                "end": group[-1].end,
                "text": " ".join(w.word.strip() for w in group),
            }
        )
    return chunks


def _write_srt(chunks: list[dict], srt_path: Path) -> None:
    def fmt(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        ms = int((s % 1) * 1000)
        return f"{int(h):02}:{int(m):02}:{int(s):02},{ms:03}"

    lines = []
    for i, c in enumerate(chunks, start=1):
        lines.append(str(i))
        lines.append(f"{fmt(c['start'])} --> {fmt(c['end'])}")
        lines.append(c["text"])
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def _write_ass(chunks: list[dict], ass_path: Path) -> None:
    """Writes an ASS file with large, bold, centered captions —
    the style typically used for short-form clip captions."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Alignment, MarginL, MarginR, MarginV, Outline, Shadow
Style: Default,DejaVu Sans,80,&H00FFFFFF,&H00000000,&H00000000,1,2,60,60,300,4,2

[Events]
Format: Layer, Start, End, Style, Text
"""

    def fmt(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        cs = int((s % 1) * 100)
        return f"{int(h)}:{int(m):02}:{int(s):02}.{cs:02}"

    lines = [header]
    for c in chunks:
        text = c["text"].upper().replace("\n", " ")
        lines.append(f"Dialogue: 0,{fmt(c['start'])},{fmt(c['end'])},Default,{text}")
    ass_path.write_text("\n".join(lines), encoding="utf-8")


def transcribe(clip_path: Path) -> tuple[list, str]:
    """Transcribes clip_path once. Returns (words, full_text) — words are
    faster-whisper Word objects (with .start/.end/.word), full_text is
    the plain transcript, useful for feeding pre-cut clips (which have no
    chapter metadata) into caption/title generation."""
    model = _get_model()
    segments, _ = model.transcribe(str(clip_path), word_timestamps=True)

    words = []
    texts = []
    for seg in segments:
        words.extend(seg.words)
        texts.append(seg.text.strip())
    return words, " ".join(texts)


def burn_captions(
    clip_path: Path,
    out_path: Path,
    srt_out_path: Path,
    commentary: str | None = None,
    words: list | None = None,
) -> Path:
    """Burns captions (plus an optional original-commentary text card
    over the first few seconds) into a new file at out_path, and writes
    an SRT to srt_out_path. Returns out_path.

    If `words` isn't provided (from a prior transcribe() call), this
    transcribes clip_path itself.

    The commentary card is the thin layer of added creative value that
    YouTube's reused-content review and TikTok's Creator Rewards
    originality check look for on clipped/reposted source material —
    without it, a pure re-upload with just captions is much less likely
    to clear monetization review on either platform.
    """
    import subprocess

    if words is None:
        words, _ = transcribe(clip_path)

    filters = []
    cleanup_paths = []

    if commentary:
        commentary_txt = out_path.with_suffix(".commentary.txt")
        commentary_txt.write_text(commentary.upper(), encoding="utf-8")
        cleanup_paths.append(commentary_txt)
        filters.append(
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"textfile={commentary_txt}:"
            "fontsize=56:fontcolor=white:"
            "box=1:boxcolor=black@0.65:boxborderw=24:"
            "line_spacing=10:"
            "x=(w-text_w)/2:y=180:"
            "enable='between(t,0,4)'"
        )

    if not words:
        # No speech detected — still apply the commentary card if present,
        # otherwise just pass the clip through untouched.
        if filters:
            cmd = [
                "ffmpeg", "-y", "-i", str(clip_path),
                "-vf", ",".join(filters),
                "-c:a", "copy", str(out_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            out_path.write_bytes(clip_path.read_bytes())
        srt_out_path.write_text("", encoding="utf-8")
        for p in cleanup_paths:
            p.unlink(missing_ok=True)
        return out_path

    chunks = _chunk_words(words, max_words=3)
    _write_srt(chunks, srt_out_path)

    ass_path = out_path.with_suffix(".ass")
    _write_ass(chunks, ass_path)
    filters.insert(0, f"subtitles={ass_path}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(clip_path),
        "-vf", ",".join(filters),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    ass_path.unlink(missing_ok=True)
    for p in cleanup_paths:
        p.unlink(missing_ok=True)
    return out_path
