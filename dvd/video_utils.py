import os
import shutil
from urllib.parse import urlparse

import cv2
import yt_dlp

import dvd.config as config


def _is_youtube_url(url: str) -> bool:
    """Checks if a URL is a valid YouTube URL."""
    parsed_url = urlparse(url)
    return parsed_url.netloc.lower().endswith(('youtube.com', 'youtu.be'))


def load_video(
    video_source: str,
    with_subtitle: bool = False,
    subtitle_source: str | None = None,
) -> str:
    """
    Loads a video from YouTube or a local file into the video database.
    Subtitle support is limited to the SRT format only.

    Args:
        video_source: YouTube URL or local video file path.
        with_subtitle: If True, also downloads / copies subtitles (SRT only).
        subtitle_source: Language code for YouTube subtitles (e.g., 'en', 'auto')
                         or local *.srt file path when video_source is local.

    Returns:
        Absolute path to the video file stored in the database.

    Raises:
        ValueError, FileNotFoundError: On invalid inputs.
    """
    raw_video_dir = os.path.join(config.VIDEO_DATABASE_FOLDER, 'raw')
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
    if os.path.exists(video_source):
        if not os.path.isfile(video_source):
            raise ValueError(f"Source path '{video_source}' is a directory, not a file.")

        filename = os.path.basename(video_source)
        destination_path = os.path.join(raw_video_dir, filename)
        shutil.copy2(video_source, destination_path)

        # copy subtitle file if requested (must be *.srt) and rename
        if with_subtitle:
            if not subtitle_source:
                raise ValueError("subtitle_source must be provided for local videos.")
            if not subtitle_source.lower().endswith('.srt'):
                raise ValueError("Only SRT subtitle files are supported for local videos.")
            if not os.path.isfile(subtitle_source):
                raise FileNotFoundError(f"Subtitle file '{subtitle_source}' not found.")

            subtitle_destination = os.path.join(
                raw_video_dir,
                f"{os.path.splitext(filename)[0]}.srt",
            )
            shutil.copy2(subtitle_source, subtitle_destination)

def download_srt_subtitle(video_url: str, output_path: str):
    """Downloads an SRT subtitle from a YouTube URL with anti-bot detection."""
    import time
    from yt_dlp.utils import DownloadError, ExtractorError
    
    if not _is_youtube_url(video_url):
        raise ValueError("Provided URL is not a valid YouTube link.")

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    max_retries = 5
    player_clients = [
        ['android'],  # First try: android only (most reliable)
        ['ios'],  # Second try: ios
        ['web'],  # Third try: web
        ['android', 'web'],  # Fourth try: android + web
        ['ios', 'android', 'web'],  # Fifth try: all clients
    ]

    # Check for cookies file (optional - set YOUTUBE_COOKIES env var)
    cookies_file = os.environ.get('YOUTUBE_COOKIES', None)
    if cookies_file and os.path.exists(cookies_file):
        cookies_file = os.path.abspath(cookies_file)
    else:
        cookies_file = None

    for attempt in range(max_retries):
        try:
            # Enhanced yt-dlp options to avoid bot detection
            # Since we only need subtitles, we skip video format selection entirely
            ydl_opts = {
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'skip_download': True,
                'writeautomaticsub': True,
                'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
                # Use flexible format selection - any available format since we skip download
                'format': 'bestaudio/best/worst',  # Try best audio, then best, then worst
                # Anti-bot detection options
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'extractor_args': {
                    'youtube': {
                        'player_client': player_clients[attempt % len(player_clients)],
                        'player_skip': ['webpage', 'configs'],
                    }
                },
                'quiet': False,
                'no_warnings': False,
            }
            
            # Add cookies if available
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get info without processing formats (we only need subtitles)
                try:
                    info = ydl.extract_info(video_url, download=False, process=False)
                    video_id = info.get('id') or info.get('display_id')
                except:
                    # Fallback: extract video ID from URL
                    if 'v=' in video_url:
                        video_id = video_url.split('v=')[1].split('&')[0]
                    else:
                        raise ValueError(f"Could not extract video ID from {video_url}")
                
                # Now download subtitles (this will process formats but we skip download)
                ydl.download([video_url])

            # Locate the downloaded subtitle file (yt-dlp names them as <id>.<lang>.srt)
            downloaded_subtitle_path = None
            for f in os.listdir(output_dir):
                if f.startswith(video_id) and f.endswith(".srt"):
                    downloaded_subtitle_path = os.path.join(output_dir, f)
                    break

            if downloaded_subtitle_path:
                shutil.move(downloaded_subtitle_path, output_path)
                return  # Success!
            else:
                raise FileNotFoundError(f"Could not find SRT subtitle for {video_url}")
                
        except (DownloadError, ExtractorError) as e:
            error_msg = str(e).lower()
            # Handle format errors - try with more flexible format
            if "format is not available" in error_msg or "requested format" in error_msg:
                if attempt < max_retries - 1:
                    # Try with more permissive format
                    try:
                        ydl_opts_flexible = ydl_opts.copy()
                        # Use very permissive format selection
                        ydl_opts_flexible['format'] = 'best[height<=480]/best/worst'
                        
                        with yt_dlp.YoutubeDL(ydl_opts_flexible) as ydl:
                            try:
                                info = ydl.extract_info(video_url, download=False, process=False)
                                video_id = info.get('id') or info.get('display_id')
                            except:
                                if 'v=' in video_url:
                                    video_id = video_url.split('v=')[1].split('&')[0]
                                else:
                                    raise
                            ydl.download([video_url])
                        
                        # Check for subtitle file
                        downloaded_subtitle_path = None
                        for f in os.listdir(output_dir):
                            if f.startswith(video_id) and f.endswith(".srt"):
                                downloaded_subtitle_path = os.path.join(output_dir, f)
                                break
                        
                        if downloaded_subtitle_path:
                            shutil.move(downloaded_subtitle_path, output_path)
                            return  # Success with flexible format!
                    except:
                        pass  # Continue to normal error handling
            if "bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg:
                if attempt < max_retries - 1:
                    # Remove format requirement and try again
                    try:
                        ydl_opts_no_format = ydl_opts.copy()
                        ydl_opts_no_format.pop('format', None)
                        ydl_opts_no_format['format'] = 'bestaudio/best'  # More flexible format
                        
                        with yt_dlp.YoutubeDL(ydl_opts_no_format) as ydl:
                            info = ydl.extract_info(video_url, download=False, process=False)
                            video_id = info.get('id') or info.get('display_id')
                            if not video_id and 'v=' in video_url:
                                video_id = video_url.split('v=')[1].split('&')[0]
                            ydl.download([video_url])
                        
                        # Check for subtitle file
                        downloaded_subtitle_path = None
                        for f in os.listdir(output_dir):
                            if f.startswith(video_id) and f.endswith(".srt"):
                                downloaded_subtitle_path = os.path.join(output_dir, f)
                                break
                        
                        if downloaded_subtitle_path:
                            shutil.move(downloaded_subtitle_path, output_path)
                            return  # Success!
                    except:
                        pass  # Fall through to bot detection check
                # If format fix didn't work, continue to bot detection handling
            if "bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3  # Exponential backoff: 3s, 6s, 9s, 12s
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed - provide helpful error message
                    error_solution = (
                        f"YouTube bot detection after {max_retries} attempts.\n\n"
                        "**This is a known issue with YouTube's anti-bot measures.**\n\n"
                        "**Immediate Solutions:**\n"
                        "1. Wait 5-10 minutes and try again (YouTube rate limiting)\n"
                        "2. Try a different video URL\n"
                        "3. The video may have restricted access\n\n"
                        "**Advanced Solution (Recommended for Production):**\n"
                        "Use YouTube cookies to authenticate:\n"
                        "1. Export cookies from your browser (see: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)\n"
                        "2. Upload cookies file to Render\n"
                        "3. Set environment variable: YOUTUBE_COOKIES=/path/to/cookies.txt\n\n"
                        "**Note:** YouTube frequently updates their bot detection. "
                        "This may require periodic updates to yt-dlp or using cookies."
                    )
                    raise Exception(error_solution)
            else:
                # Re-raise other errors immediately
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                raise


def decode_video_to_frames(video_path: str) -> str:
    """
    Decodes a video into JPEG frames at the frame rate specified by config.VIDEO_FPS.
    Frames are saved in config.VIDEO_DATABASE_PATH/video_names/frames/.

    Args:
        video_path: The absolute path to the video file.

    Returns:
        The absolute path to the directory containing the extracted frames.

    Raises:
        FileNotFoundError: If the video file does not exist.
        Exception: If frame extraction fails.
    """

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file '{video_path}' does not exist.")

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    frames_dir = os.path.join(config.VIDEO_DATABASE_FOLDER, video_name, 'frames')
    os.makedirs(frames_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Failed to open video file '{video_path}'.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    target_fps = getattr(config, 'VIDEO_FPS', fps)
    frame_interval = int(round(fps / target_fps)) if target_fps < fps else 1

    frame_count = 0
    saved_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            frame_filename = os.path.join(frames_dir, f"frame_n{saved_count:06d}.jpg")
            cv2.imwrite(frame_filename, frame)
            saved_count += 1
        frame_count += 1

    cap.release()
    return os.path.abspath(frames_dir)

if __name__ == "__main__":
    download_srt_subtitle("https://www.youtube.com/watch?v=PQFQ-3d2J-8", "./video_database/PQFQ-3d2J-8/subtitles.srt")