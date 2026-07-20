# Shawn Ryan Show — Auto-Clip Poster

Watches the channel's YouTube feed for new episodes. For each one,
prefers Shawn Ryan Show's own pre-cut vertical reels (linked in the
episode description) when available, and only falls back to cutting
clips itself when they aren't. Writes captions with Claude, burns in
captions + a short original-commentary card, and posts to multiple
social platforms via Ayrshare — always with the required tag and link
back to the full episode. Runs entirely on GitHub Actions' free tier;
no server or Make.com/Zapier needed.

## How it works

1. **Detect** — `scripts/check_new_episodes.py` reads the channel's
   public YouTube RSS feed and diffs it against `state/processed_episodes.json`.
2. **Check for Shawn's own pre-cut reels first** — `scripts/precut_assets.py`
   scans the episode description for a Google Drive folder link (Shawn Ryan
   Show provides pre-cut, raw vertical reels per episode) and, if found,
   downloads up to `CLIPS_PER_EPISODE` of them directly — no need to
   download the full episode or cut anything.
3. **Fallback: self-cut** — if no folder link is found (or it's empty),
   `cut_clips.py` downloads the full episode with `yt-dlp` (which also
   parses chapter markers) and `scripts/generate_caption.py` has Claude
   pick the best chapters, expanding each window to at least
   `MIN_CLIP_DURATION` seconds.
4. **Write captions** — Claude writes a hook, a search-optimized YouTube
   title, and a one-line original commentary take for each clip. The
   `@shawnryanshow`/`@shawnryan762` tag AND the link-back are appended
   by the script itself from a template — never left to the model — so
   neither can be dropped, per Shawn Ryan Show's stated reposting terms.
5. **Burn in** — `scripts/burn_captions.py` transcribes the clip with
   `faster-whisper` and burns in short phrase-level captions plus the
   commentary text card over the first ~4 seconds. On the pre-cut path,
   this transcript is also fed back into caption generation, since
   pre-cut reels have no chapter metadata to describe their own content.
6. **Publish** — `scripts/post_clips.py` uploads the finished clip (and
   its SRT) as GitHub Release assets and calls Ayrshare's `/api/post` to
   fan out to every configured platform in one call.
7. State is committed back to the repo so the next run knows what's
   already been posted.

## One-time setup

1. **Create a public GitHub repo** and push this project to it (release
   assets need to be publicly fetchable by Ayrshare; if you want the repo
   private, you'll need a different media host — see "Notes" below).

2. **Get an Ayrshare API key** at ayrshare.com and link the target social
   accounts (Instagram, TikTok, X, YouTube, etc.) in the Ayrshare dashboard.
   - X/Twitter posting requires your own X Developer App key/secret as of
     March 2026 — Ayrshare's dashboard will walk you through linking it.

3. **Get an Anthropic API key** at console.anthropic.com.

4. **Find the channel ID** for Shawn Ryan Show (starts with `UC...`) —
   visible in the channel's page source or via any channel-ID lookup tool.

5. **Add repo secrets** (Settings → Secrets and variables → Actions → New
   repository secret):
   - `YOUTUBE_CHANNEL_ID`
   - `ANTHROPIC_API_KEY`
   - `AYRSHARE_API_KEY`
   - `TARGET_PLATFORMS` — start with `tiktok` only for testing (see
     "Testing phase" below), then widen to e.g. `instagram,tiktok,x,youtube`
     once clip quality is validated
   - `SHOW_LINK_BACK` — e.g. `Full episode: https://www.youtube.com/@ShawnRyanShow`
   - `SHOW_TAG` — e.g. `@shawnryanshow` (required tag per Shawn Ryan Show's reposting terms)
   - `CLIPS_PER_EPISODE` — e.g. `2`
   - `GOOGLE_API_KEY` — optional but recommended; a Google Cloud API key
     with the Drive API enabled (no OAuth needed). Lets the pipeline use
     Shawn's own pre-cut reels instead of self-cutting. Get one at
     console.cloud.google.com → APIs & Services → Credentials → Create
     API Key, after enabling "Google Drive API" for the project.

   (`GITHUB_TOKEN` is provided automatically — no need to add it.)

6. The workflow runs daily at 13:00 UTC (`.github/workflows/post-clips.yml`)
   and can also be triggered manually from the Actions tab.

## Testing phase: start with TikTok only

Before posting everywhere, set `TARGET_PLATFORMS=tiktok` and run against
a single new handle. Reasons to start here specifically:

- **Simplest signup** — just email/phone, no channel verification or
  Google account tie-in like YouTube requires.
- **Matches the pipeline's existing tuning** — clip length (60-90s) and
  the originality commentary card were both built with TikTok's Creator
  Rewards Program requirements in mind.
- **Simpler debugging** — isolates whether clip-picking, pre-cut asset
  detection, captions, and the commentary card are all working, without
  three platforms' worth of variables at once.

Note: TikTok's Creator Rewards Program itself (their monetization) needs
10,000+ followers and 100,000+ views in the last 30 days before it pays
anything — so this phase is purely about validating clip quality, not
early revenue. That comes later once you're posting more broadly.

Once ~5-10 episodes come out consistently good (dry run first, then a
few real posts), widen `TARGET_PLATFORMS` to include Instagram, X, and
YouTube.

## Dry run mode (test before going live)

Trigger the workflow manually from the Actions tab ("Run workflow") and
check the **dry_run** box. In dry run:

- Clips are generated, captioned, and uploaded as GitHub Release assets
  (tagged `<video_id>-dryrun`) so you can download and watch them.
- **Nothing is posted** to any social platform — the Ayrshare call is
  skipped entirely.
- The episode is **not** marked as processed, so once you're happy with
  the output, an ordinary (non-dry-run) run will pick that same episode
  up and actually post it.
- Logs print exactly what would have been posted: the platforms, the
  caption, and the YouTube title — check these against the downloaded
  clip before flipping dry run off.

Recommended: run dry run against the most recent 1-2 episodes first,
review the clip picks/captions/caption timing, then do a real run.

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
export $(cat .env | xargs)
export GITHUB_REPOSITORY="your-username/your-repo"
python main.py
```

## Notes / things to double check

- **Copyright/attribution**: this posts derivative clips of another
  creator's content. You mentioned Shawn's team is fine with this as
  long as a link back is included — that's baked into every caption
  here, but it's worth confirming the exact wording/placement he wants
  once, since some creators want it in a specific spot (e.g. first line
  vs. bio link) rather than just "included somewhere."
- **Repo visibility**: release assets on a private repo aren't publicly
  fetchable, which will break the Ayrshare upload step. If you'd rather
  keep the repo private, swap `upload_release_asset()` for an upload to
  something like Cloudinary or S3 instead.
- **Chapter quality**: this relies on the episode having chapter markers
  (native YouTube chapters or timestamps in the description). Shawn Ryan
  Show episodes typically do, but if one doesn't, that episode is marked
  processed and skipped with a log line rather than failing the run.
- **Runtime limits**: GitHub Actions jobs have a 6-hour max and Ubuntu
  runners have ~14GB free disk — fine for a few episodes/day, but long
  episodes (3+ hours) + multiple clips could push disk usage; the script
  deletes the source download and each clip right after it's posted to
  keep this in check.
- **Whisper model size**: `burn_captions.py` uses the `small` faster-whisper
  model as a speed/accuracy balance on a CPU-only runner. If runs are
  timing out, drop to `base`; if caption accuracy is off, try `medium`
  (slower).

## Monetization-oriented changes

This pipeline is tuned toward the two most realistic revenue paths for
clipped content — TikTok's Creator Rewards Program and YouTube Shorts
ad revenue — plus keeps the door open for affiliate/brand-deal work,
which doesn't depend on either platform's approval process:

- **Clip length (60-90s)**: TikTok's Creator Rewards Program pays $0 on
  videos under 60 seconds, full stop. `expand_to_min_duration()` in
  `cut_clips.py` widens the cut window to hit at least `MIN_CLIP_DURATION`
  (default 60s) whenever the chapter and surrounding footage allow it,
  capped at `MAX_CLIP_DURATION` (default 90s).
- **Original commentary card**: both YouTube's reused-content review and
  TikTok's Creator Rewards originality check specifically penalize
  clips with nothing added beyond the source material. Claude now also
  writes a one-line original take/reaction per clip, burned in as a text
  card over the first ~4 seconds (`scripts/burn_captions.py`). This is a
  minimal version of "added value" — likely not enough on its own to
  pass a human monetization review. If you're serious about YPP/Creator
  Rewards approval, the strongest lever beyond this pipeline is adding a
  real voiceover reaction or on-camera intro/outro segment, which this
  pipeline doesn't attempt to automate.

**What this doesn't solve, and can't be coded around:**
- **Monetization consent**: Shawn's team agreeing to a link-back doesn't
  automatically mean they're fine with you earning ad revenue off his
  content. Worth confirming explicitly before this starts generating
  real money, not after.
- **Platform approval is manual/algorithmic on their end**: YPP and
  Creator Rewards applications go through their own review; nothing in
  this repo can guarantee approval.
- **Affiliate/TikTok Shop/brand deals**: these don't require platform
  monetization approval and are probably the fastest realistic revenue
  path, but they're a business-development task (negotiating deals,
  tagging products), not something this pipeline automates.

## Config reference (new)

| Env var | Default | Purpose |
|---|---|---|
| `MIN_CLIP_DURATION` | `60` | Minimum clip length in seconds (TikTok Creator Rewards floor) |
| `MAX_CLIP_DURATION` | `90` | Maximum clip length in seconds |
| `SHOW_TAG` | `@shawnryanshow` | Handle tagged on every post, per Shawn Ryan Show's stated terms |
| `GOOGLE_API_KEY` | *(none)* | Enables the pre-cut-reel path; falls back to self-cutting if unset or if no folder link is found |

## A note on the pre-cut asset path

Shawn Ryan Show explicitly permits editing, publishing, and fully
monetizing their pre-cut reels, and reserves the right to reshare good
fan edits on their own accounts — subject to two conditions this
pipeline now enforces automatically on every post: tagging
`@shawnryanshow`/`@shawnryan762`, and linking back to the full episode.

The Drive folder link is embedded per-episode in the YouTube description
rather than at a single fixed URL, which is why `precut_assets.py` parses
each new episode's description at run time rather than using a hardcoded
folder ID.
