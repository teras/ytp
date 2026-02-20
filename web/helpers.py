"""Shared configuration, yt-dlp instances, helper functions, and cleanup registry."""
import logging
import os
import time
from pathlib import Path

import yt_dlp

log = logging.getLogger(__name__)

# Cache directory for subtitle VTT files
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# yt-dlp options
_cookies_browser = os.environ.get('YOUTUBE_COOKIES_BROWSER')
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'remote_components': ['ejs:github'],
}
if _cookies_browser:
    YDL_OPTS['cookiesfrombrowser'] = (_cookies_browser,)

# yt-dlp instance for video info extraction (formats, subtitles, DASH/HLS URLs)
# Search/channel pagination now uses InnerTube directly (see directcalls.py)
ydl_info = yt_dlp.YoutubeDL(YDL_OPTS)


# ── Cleanup registry ─────────────────────────────────────────────────────────

_cleanup_registry: list = []
_last_cleanup: float = 0


def register_cleanup(fn):
    """Register a cleanup function to be called periodically."""
    _cleanup_registry.append(fn)


def maybe_cleanup():
    """Run all registered cleanup functions if 5+ minutes since last run."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < 300:
        return
    _last_cleanup = now
    for fn in _cleanup_registry:
        try:
            fn()
        except Exception as e:
            log.warning(f"Cleanup error: {e}")


def _yt_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _format_duration(seconds) -> str:
    if not seconds:
        return "?"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_number(n):
    if n is None:
        return None
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
