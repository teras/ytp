"""Cursor-based pagination for search and channel browsing.

Uses InnerTube continuation tokens (~200 bytes each) instead of holding
yt-dlp generators (~3.5 MB each) in memory.
"""

import logging
import secrets
import time
from dataclasses import dataclass, field

from helpers import register_cleanup
from auth import AUTH_SESSIONS
from directcalls import search_first, search_next, channel_first, channel_next

log = logging.getLogger(__name__)

_CURSOR_TTL = 5 * 3600  # 5 hours
_MAX_ENTRIES = 1_000


@dataclass
class CursorState:
    type: str                       # "search" or "channel"
    continuation_token: str | None  # YouTube's InnerTube token (~200 bytes)
    last_access: float = field(default_factory=time.time)
    channel_name: str | None = None
    pulled: int = 0


def create_search(session: dict, query: str) -> tuple[list[dict], str | None]:
    """Search YouTube and return (first_batch, cursor_id)."""
    results, yt_token = search_first(query)

    if not results:
        return [], None

    if not yt_token:
        return results, None

    cursor_id = secrets.token_urlsafe(16)
    session["searches"][cursor_id] = CursorState(
        type="search",
        continuation_token=yt_token,
        pulled=len(results),
    )
    return results, cursor_id


def create_channel(session: dict, channel_id: str) -> tuple[str, list[dict], str | None]:
    """Get channel videos and return (channel_name, first_batch, cursor_id)."""
    channel_name, results, yt_token = channel_first(channel_id)

    if not results:
        return channel_name, [], None

    if not yt_token:
        return channel_name, results, None

    cursor_id = secrets.token_urlsafe(16)
    session["searches"][cursor_id] = CursorState(
        type="channel",
        continuation_token=yt_token,
        channel_name=channel_name,
        pulled=len(results),
    )
    return channel_name, results, cursor_id


def fetch_more(session: dict, cursor_id: str) -> tuple[list[dict], str | None]:
    """Fetch next batch using a cursor ID.

    Returns (results, cursor_id | None). Expired/missing cursor returns ([], None).
    """
    state = session.get("searches", {}).get(cursor_id)
    if not state or not state.continuation_token:
        session.get("searches", {}).pop(cursor_id, None)
        return [], None

    if state.pulled >= _MAX_ENTRIES:
        session["searches"].pop(cursor_id, None)
        return [], None

    state.last_access = time.time()

    if state.type == "search":
        results, yt_token = search_next(state.continuation_token)
    elif state.type == "channel":
        results, yt_token = channel_next(state.continuation_token)
    else:
        session["searches"].pop(cursor_id, None)
        return [], None

    state.pulled += len(results)
    state.continuation_token = yt_token

    if not yt_token or state.pulled >= _MAX_ENTRIES:
        session["searches"].pop(cursor_id, None)
        return results, None

    return results, cursor_id


def _cleanup_cursors():
    """Remove expired cursors from all sessions."""
    now = time.time()
    total = 0
    for session in AUTH_SESSIONS.values():
        searches = session.get("searches", {})
        expired = [k for k, v in searches.items()
                   if now - v.last_access > _CURSOR_TTL]
        for k in expired:
            del searches[k]
        total += len(expired)
    if total:
        log.info(f"Cleaned {total} expired cursor(s)")


register_cleanup(_cleanup_cursors)
