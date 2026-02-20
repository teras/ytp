"""Browse routes: search, channel, related videos, cursor pagination."""
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, Depends

from auth import require_auth, get_session
from iterators import create_search, create_channel, fetch_more
from directcalls import fetch_related

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_COOKIE_MAX_AGE = 10 * 365 * 86400  # 10 years


def _json_with_cookie(data: dict, token: str, request: Request) -> Response:
    """Return a JSON response, setting session cookie if needed."""
    resp = Response(content=json.dumps(data), media_type='application/json')
    if request.cookies.get("ytp_session") != token:
        resp.set_cookie(
            key="ytp_session",
            value=token,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax"
        )
    return resp


@router.get("/search")
async def search(request: Request, q: str = Query(..., min_length=1), auth: bool = Depends(require_auth)):
    """Search YouTube. Returns first batch + cursor for pagination."""
    token, session = get_session(request)

    try:
        results, cursor = await create_search(token, q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _json_with_cookie({'results': results, 'cursor': cursor}, token, request)


@router.get("/more")
async def more(request: Request, cursor: str = Query(..., min_length=1), auth: bool = Depends(require_auth)):
    """Fetch next batch using cursor. Expired/invalid cursor returns empty results."""
    token, session = get_session(request)

    try:
        results, next_cursor = await fetch_more(token, cursor)
    except Exception:
        results, next_cursor = [], None

    return _json_with_cookie({'results': results, 'cursor': next_cursor}, token, request)


@router.get("/related/{video_id}")
async def get_related_videos(video_id: str, auth: bool = Depends(require_auth)):
    """Get related videos for a video."""
    results = await fetch_related(video_id)
    return {"results": results}


@router.get("/channel/{channel_id}")
async def get_channel_videos(
    request: Request,
    channel_id: str,
    auth: bool = Depends(require_auth)
):
    """Get videos from a channel. Returns first batch + cursor for pagination."""
    token, session = get_session(request)

    try:
        channel_name, results, cursor = await create_channel(token, channel_id)
    except Exception as e:
        log.error(f"Channel videos error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return _json_with_cookie({
        'channel': channel_name,
        'channel_id': channel_id,
        'results': results,
        'cursor': cursor
    }, token, request)
