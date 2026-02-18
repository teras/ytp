"""YouTube Web App - FastAPI Backend with progressive download"""
import os
import asyncio
import logging
import yt_dlp
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('ytd.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

app = FastAPI(title="YouTube Web App")

# Downloads directory
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Track active downloads: video_id -> {"status": str, "progress": float, ...}
active_downloads = {}

# yt-dlp instances (reused)
ydl_search = yt_dlp.YoutubeDL({
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,  # Fast search
})

ydl_info = yt_dlp.YoutubeDL({
    'quiet': True,
    'no_warnings': True,
})

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/search")
async def search(q: str = Query(..., min_length=1), count: int = Query(default=10, ge=1, le=50)):
    """Search YouTube"""
    try:
        result = ydl_search.extract_info(f"ytsearch{count}:{q}", download=False)

        videos = []
        for entry in result.get('entries', []):
            if not entry:
                continue

            video_id = entry.get('id', '')
            duration = entry.get('duration') or 0

            if duration:
                duration = int(duration)
                hours, remainder = divmod(duration, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
            else:
                duration_str = "?"

            videos.append({
                'id': video_id,
                'title': entry.get('title', 'Unknown'),
                'duration': duration,
                'duration_str': duration_str,
                'channel': entry.get('channel') or entry.get('uploader', 'Unknown'),
                'thumbnail': f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
            })

        return {'results': videos}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/play/{video_id}")
async def play_video(video_id: str):
    """Start download and return stream URL"""
    video_path = DOWNLOADS_DIR / f"{video_id}.mp4"

    # Already fully downloaded?
    if video_path.exists() and video_id not in active_downloads:
        return {"status": "ready", "url": f"/api/stream/{video_id}"}

    # Already downloading?
    if video_id in active_downloads:
        dl = active_downloads[video_id]
        return {
            "status": dl.get('status', 'downloading'),
            "progress": dl.get('progress', 0),
            "message": dl.get('message', ''),
            "url": f"/api/stream/{video_id}"
        }

    # Start new download
    active_downloads[video_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Starting...",
    }

    async def download_parallel():
        """Download audio first, then pipe video through ffmpeg for immediate playback"""
        audio_file = DOWNLOADS_DIR / f"{video_id}.audio.m4a"

        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            log.info(f"Starting download for {video_id}")

            # Step 1: Download audio (small, fast)
            active_downloads[video_id]['status'] = 'audio'
            active_downloads[video_id]['message'] = 'Downloading audio...'

            audio_proc = await asyncio.create_subprocess_exec(
                'yt-dlp', '-f', 'bestaudio[ext=m4a]/bestaudio',
                '-o', str(audio_file), '--no-warnings', '-q', url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await audio_proc.wait()

            if not audio_file.exists():
                raise Exception("Audio download failed")

            log.info(f"Audio done ({audio_file.stat().st_size} bytes), starting video pipe")

            # Step 2: Pipe video through ffmpeg (streams full video, no throttle)
            active_downloads[video_id]['status'] = 'video'
            active_downloads[video_id]['message'] = 'Downloading video...'
            active_downloads[video_id]['progress'] = 0

            # yt-dlp pipes video to ffmpeg, which merges with audio and outputs fragmented MP4
            # Format: best https video (not m3u8/HLS), fallback to format 18 (360p combined)
            cmd = (
                f'yt-dlp -f "bestvideo[protocol=https]/bestvideo[protocol=http]/18" -o - --no-warnings -q "{url}" | '
                f'ffmpeg -y -i "{audio_file}" -i pipe:0 '
                f'-c:v copy -c:a aac '
                f'-movflags frag_keyframe+empty_moov '
                f'-f mp4 "{video_path}"'
            )

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            # Monitor progress
            while process.returncode is None:
                await asyncio.sleep(0.3)

                if video_path.exists():
                    size_mb = video_path.stat().st_size / (1024 * 1024)
                    active_downloads[video_id]['progress'] = min(95, size_mb * 2)
                    active_downloads[video_id]['message'] = f'{size_mb:.1f} MB'

                try:
                    await asyncio.wait_for(process.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

            await process.wait()

            if process.returncode == 0 and video_path.exists():
                log.info(f"Complete: {video_id} ({video_path.stat().st_size} bytes)")
                active_downloads[video_id]['status'] = 'finished'
                active_downloads[video_id]['progress'] = 100
                active_downloads[video_id]['message'] = 'Complete'
                audio_file.unlink(missing_ok=True)
            else:
                stderr = await process.stderr.read()
                log.error(f"FFmpeg failed: {stderr.decode()[:500]}")
                raise Exception("Video processing failed")

        except Exception as e:
            log.error(f"Download error for {video_id}: {e}")
            active_downloads[video_id]['status'] = 'error'
            active_downloads[video_id]['message'] = str(e)[:100]
            audio_file.unlink(missing_ok=True)
        finally:
            await asyncio.sleep(60)
            active_downloads.pop(video_id, None)

    asyncio.create_task(download_parallel())

    # Wait a bit for download to start
    await asyncio.sleep(0.5)

    return {
        "status": "downloading",
        "progress": 0,
        "message": "Starting...",
        "url": f"/api/stream/{video_id}"
    }


def format_number(n):
    """Format large numbers: 1500000 -> 1.5M"""
    if n is None:
        return None
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


@app.get("/api/info/{video_id}")
async def get_video_info(video_id: str):
    """Get video info including upload date, views, etc."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        info = await asyncio.to_thread(ydl_info.extract_info, url, download=False)

        upload_date = info.get('upload_date', '')
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[6:8]}/{upload_date[4:6]}/{upload_date[0:4]}"

        return {
            'title': info.get('title', 'Unknown'),
            'channel': info.get('channel') or info.get('uploader', 'Unknown'),
            'upload_date': upload_date,
            'duration': info.get('duration', 0),
            'views': format_number(info.get('view_count')),
            'likes': format_number(info.get('like_count')),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/progress/{video_id}")
async def get_progress(video_id: str):
    """Get download progress"""
    video_path = DOWNLOADS_DIR / f"{video_id}.mp4"

    if video_id in active_downloads:
        dl = active_downloads[video_id]
        return {
            "status": dl.get('status', 'unknown'),
            "progress": dl.get('progress', 0),
            "message": dl.get('message', ''),
        }
    elif video_path.exists():
        return {"status": "ready", "progress": 100, "message": "Ready"}
    else:
        return {"status": "not_found", "progress": 0, "message": "Not found"}


@app.get("/api/stream/{video_id}")
async def stream_video(video_id: str, request: Request):
    """Stream video file (even while downloading)"""
    video_path = DOWNLOADS_DIR / f"{video_id}.mp4"

    # Wait for file to exist and have some data
    for _ in range(150):  # Max 15 seconds
        if video_path.exists() and video_path.stat().st_size > 100_000:
            break
        await asyncio.sleep(0.1)

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    is_downloading = video_id in active_downloads and active_downloads[video_id].get('status') != 'finished'

    # For completed downloads, use FileResponse
    if not is_downloading:
        return FileResponse(
            video_path,
            media_type='video/mp4',
            filename=f'{video_id}.mp4'
        )

    # For in-progress downloads, stream the fragmented MP4
    async def generate():
        pos = 0
        stall_count = 0

        while True:
            try:
                current_size = video_path.stat().st_size
            except:
                await asyncio.sleep(0.1)
                continue

            if pos < current_size:
                stall_count = 0
                with open(video_path, 'rb') as f:
                    f.seek(pos)
                    chunk = f.read(65536)
                    if chunk:
                        pos += len(chunk)
                        yield chunk
            else:
                stall_count += 1
                # Check if download finished
                if video_id not in active_downloads or active_downloads[video_id].get('status') == 'finished':
                    # Read any remaining data
                    try:
                        final_size = video_path.stat().st_size
                        if pos < final_size:
                            with open(video_path, 'rb') as f:
                                f.seek(pos)
                                remaining = f.read()
                                if remaining:
                                    yield remaining
                    except:
                        pass
                    break

                # Timeout after too many stalls
                if stall_count > 100:  # 10 seconds of no data
                    break

                await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        status_code=200,
        headers={
            'Content-Type': 'video/mp4',
            'Cache-Control': 'no-cache',
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
