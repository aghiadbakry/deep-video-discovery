import os
import shutil
import yt_dlp
from typing import Dict
from urllib.parse import urlparse

def _is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube link."""
    parsed_url = urlparse(url)
    return parsed_url.netloc.lower().endswith(('youtube.com', 'youtu.be'))


def load_video(
    video_source: str,
    with_subtitle: bool = False,
    subtitle_source: str | None = None,
) -> str:
    """
    Load video from YouTube URL or local file path.
    Returns the path to the downloaded/loaded video file.
    """
    from dvd import config

    raw_video_dir = os.path.join(config.VIDEO_DATABASE_FOLDER, "raw")
    os.makedirs(raw_video_dir, exist_ok=True)

    # ------------------- YouTube source -------------------
    if video_source.startswith(('http://', 'https://')):
        if not _is_youtube_url(video_source):
            raise ValueError("Provided URL is not a valid YouTube link.")

        # Enhanced yt-dlp options to avoid bot detection
        ydl_opts = {
            'format': (
                f'bestvideo[height<={config.VIDEO_RESOLUTION}][ext=mp4]'
                f'best[height<={config.VIDEO_RESOLUTION}][ext=mp4]'
            ),
            'outtmpl': os.path.join(raw_video_dir, '%(id)s.%(ext)s'),
            'merge_output_format': 'mp4',
            # Anti-bot detection options
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],  # Try android first, fallback to web
                    'player_skip': ['webpage', 'configs'],
                }
            },
            'quiet': False,
            'no_warnings': False,
        }
        if with_subtitle:
            ydl_opts.update({
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'overwritesubtitles': True,
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_source, download=True)
            video_path = ydl.prepare_filename(info)

        # rename subtitle -> "<video_file_name>.srt"
        if with_subtitle:
            video_base = os.path.splitext(video_path)[0]
            for f in os.listdir(raw_video_dir):
                if f.startswith(info["id"]) and f.endswith(".srt"):
                    shutil.move(
                        os.path.join(raw_video_dir, f),
                        f"{video_base}.srt",
                    )
                    break

        return os.path.abspath(video_path)

    # ------------------- Local source -------------------
    elif os.path.isfile(video_source):
        video_id = os.path.splitext(os.path.basename(video_source))[0]
        video_destination = os.path.join(raw_video_dir, f"{video_id}.mp4")
        os.makedirs(os.path.dirname(video_destination), exist_ok=True)
        shutil.copy2(video_source, video_destination)

        if with_subtitle and subtitle_source:
            subtitle_destination = f"{os.path.splitext(video_destination)[0]}.srt"
            os.makedirs(os.path.dirname(subtitle_destination), exist_ok=True)
            shutil.copy2(subtitle_source, subtitle_destination)

        return os.path.abspath(video_destination)
    else:
        raise ValueError(f"Video source '{video_source}' is not a valid URL or file path.")


def download_srt_subtitle(video_url: str, output_path: str):
    """
    Downloads an SRT subtitle from a YouTube URL.
    
    Uses yt-dlp's built-in subtitle download which handles all the complexity
    internally - just like those YouTube downloader websites do!
    """
    import time
    from yt_dlp.utils import DownloadError, ExtractorError
    
    if not _is_youtube_url(video_url):
        raise ValueError("Provided URL is not a valid YouTube link.")

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # Extract video ID from URL
    if 'v=' in video_url:
        video_id = video_url.split('v=')[1].split('&')[0]
    else:
        raise ValueError(f"Could not extract video ID from {video_url}")

    # Check for cookies file (optional - set YOUTUBE_COOKIES env var)
    cookies_file = os.environ.get('YOUTUBE_COOKIES', None)
    if cookies_file:
        cookies_file = os.path.abspath(cookies_file)
        if os.path.exists(cookies_file):
            file_size = os.path.getsize(cookies_file)
            print(f"🍪 Using cookies file: {cookies_file} ({file_size} bytes)")
        else:
            print(f"⚠️ Cookies file not found: {cookies_file}")
            cookies_file = None
    else:
        cookies_file = None
        print("ℹ️ No cookies file specified (YOUTUBE_COOKIES env var not set)")

    # SIMPLIFIED APPROACH: Let yt-dlp do what it does best!
    # This is how YouTube downloader websites work - they use yt-dlp's built-in methods
    max_retries = 3
    
    # When cookies are available, use 'web' client only (cookies don't work with android/ios)
    if cookies_file:
        player_clients = [['web']] * max_retries
    else:
        # Without cookies, try different clients
        player_clients = [
            ['android'],  # Most reliable without cookies
            ['ios'],
            ['web'],
        ]

    for attempt in range(max_retries):
        try:
            print(f"🔄 Attempt {attempt + 1}/{max_retries}: Downloading subtitles...")
            
            # Simple, clean yt-dlp options - let it handle everything!
            ydl_opts = {
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'skip_download': True,  # We only want subtitles, not video
                'writeautomaticsub': True,  # Get auto-generated subtitles too
                'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
                # NO format specification - yt-dlp will handle it since we skip download
                # This is key! Don't specify format when we only need subtitles
                'ignoreerrors': False,
                'no_warnings': False,
                'quiet': False,
            }
            
            # Add cookies if available
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': player_clients[attempt % len(player_clients)],
                    }
                }
            else:
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': player_clients[attempt % len(player_clients)],
                    }
                }
            
            # Let yt-dlp do its magic - it knows how to download subtitles!
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # This will download subtitles and handle all the complexity internally
                ydl.download([video_url])

            # Check for downloaded subtitle file
            # yt-dlp names them as: <video_id>.<lang>.srt (e.g., i2qSxMVeVLI.en.srt)
            downloaded_subtitle_path = None
            for f in os.listdir(output_dir):
                if f.startswith(video_id) and f.endswith(".srt"):
                    downloaded_subtitle_path = os.path.join(output_dir, f)
                    file_size = os.path.getsize(downloaded_subtitle_path)
                    if file_size > 0:  # Make sure it's not empty
                        print(f"✅ Found subtitle file: {f} ({file_size} bytes)")
                        break
            
            if downloaded_subtitle_path:
                # Move to the desired output path
                shutil.move(downloaded_subtitle_path, output_path)
                print(f"✅ Successfully downloaded subtitles to {output_path}")
                return  # Success!
            else:
                raise FileNotFoundError(f"Subtitle file not found after download attempt {attempt + 1}")
                
        except (DownloadError, ExtractorError) as e:
            error_msg = str(e).lower()
            
            # Check if subtitles were downloaded despite the error
            for f in os.listdir(output_dir):
                if f.startswith(video_id) and f.endswith(".srt"):
                    downloaded_subtitle_path = os.path.join(output_dir, f)
                    if os.path.getsize(downloaded_subtitle_path) > 0:
                        shutil.move(downloaded_subtitle_path, output_path)
                        print(f"✅ Subtitles downloaded successfully (error occurred but subtitles are available)")
                        return  # Success!
            
            # Handle specific errors
            if "bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3  # Exponential backoff
                    print(f"⚠️ Bot detection (attempt {attempt + 1}), waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    error_solution = (
                        f"YouTube bot detection after {max_retries} attempts.\n\n"
                        "**Solutions:**\n"
                        "1. Set YOUTUBE_COOKIES_B64 with fresh cookies\n"
                        "2. Wait 5-10 minutes and try again\n"
                        "3. Try a different video URL\n\n"
                        "See DEPLOY.md for cookie setup instructions."
                    )
                    raise Exception(error_solution)
            elif "format" in error_msg or "not available" in error_msg:
                # Format errors shouldn't matter since we skip download
                # But if they do, try with ignoreerrors
                if attempt < max_retries - 1:
                    print(f"⚠️ Format error (unexpected), trying with ignoreerrors...")
                    ydl_opts['ignoreerrors'] = True
                    continue
                else:
                    raise Exception(f"Subtitle download failed: {e}")
            else:
                # Other errors - retry
                if attempt < max_retries - 1:
                    print(f"⚠️ Error occurred, retrying... ({error_msg[:100]})")
                    time.sleep(3)
                    continue
                else:
                    raise
                    
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Unexpected error, retrying... ({str(e)[:100]})")
                time.sleep(3)
                continue
            else:
                raise FileNotFoundError(f"Could not download SRT subtitle for {video_url}: {e}")

    # If we get here, all retries failed
    raise FileNotFoundError(f"Could not find SRT subtitle for {video_url} after {max_retries} attempts")


def decode_video_to_frames(video_path: str) -> str:
    """
    Decode video into frames and save them to disk.
    Returns the path to the frames directory.
    """
    import cv2
    from tqdm import tqdm
    from dvd import config

    video_id = os.path.splitext(os.path.basename(video_path))[0]
    frames_dir = os.path.join(config.VIDEO_DATABASE_FOLDER, video_id, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps / config.VIDEO_FPS)  # Extract frame every N frames

    frame_count = 0
    saved_count = 0

    with tqdm(desc=f"Decoding {video_id}") as pbar:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                frame_filename = os.path.join(
                    frames_dir, f"frame_n{saved_count * frame_interval}.jpg"
                )
                cv2.imwrite(frame_filename, frame)
                saved_count += 1
                pbar.update(1)

            frame_count += 1

    cap.release()
    return frames_dir
