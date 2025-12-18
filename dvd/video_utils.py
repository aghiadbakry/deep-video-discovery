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
    
    Uses a hybrid approach:
    1. First tries yt-dlp's built-in subtitle download
    2. If format processing fails, extracts subtitle URLs without processing formats
    3. Downloads subtitles directly using requests (bypasses format validation)
    """
    import time
    import requests
    from yt_dlp.utils import DownloadError, ExtractorError
    from http.cookiejar import MozillaCookieJar
    
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

    # METHOD 1: Try yt-dlp's built-in subtitle download first
    for attempt in range(max_retries):
        try:
            print(f"🔄 Attempt {attempt + 1}/{max_retries}: Trying yt-dlp subtitle download...")
            
            ydl_opts = {
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'skip_download': True,
                'writeautomaticsub': True,
                'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
                'ignoreerrors': False,
                'no_warnings': False,
                'quiet': False,
            }
            
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
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Check for downloaded subtitle file
            downloaded_subtitle_path = None
            for f in os.listdir(output_dir):
                if f.startswith(video_id) and f.endswith(".srt"):
                    downloaded_subtitle_path = os.path.join(output_dir, f)
                    file_size = os.path.getsize(downloaded_subtitle_path)
                    if file_size > 0:
                        print(f"✅ Found subtitle file: {f} ({file_size} bytes)")
                        shutil.move(downloaded_subtitle_path, output_path)
                        print(f"✅ Successfully downloaded subtitles to {output_path}")
                        return  # Success!
            
            # If no file found, continue to alternative method
            print(f"⚠️ No subtitle file found, trying alternative method...")
            break
                
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
            
            # If format error, try alternative method immediately
            if "format" in error_msg or "not available" in error_msg:
                print(f"⚠️ Format error detected, switching to alternative method...")
                break
            elif "bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3
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
            else:
                if attempt < max_retries - 1:
                    print(f"⚠️ Error occurred, retrying... ({error_msg[:100]})")
                    time.sleep(3)
                    continue
                else:
                    # Try alternative method
                    break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Unexpected error, retrying... ({str(e)[:100]})")
                time.sleep(3)
                continue
            else:
                # Try alternative method
                break

    # METHOD 2: Extract subtitle URLs WITHOUT format processing, then download directly
    print(f"🔄 Trying alternative method: Extract subtitle URLs without format processing...")
    
    for attempt in range(max_retries):
        try:
            # Extract info WITHOUT processing formats (this avoids format errors)
            info_opts = {
                'quiet': False,
                'no_warnings': False,
                'skip_download': True,
            }
            
            if cookies_file:
                info_opts['cookiefile'] = cookies_file
                info_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': player_clients[attempt % len(player_clients)],
                    }
                }
            else:
                info_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': player_clients[attempt % len(player_clients)],
                    }
                }
            
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                # Extract info WITHOUT processing formats - this gets subtitle URLs without format validation
                info = ydl.extract_info(video_url, download=False, process=False)
            
            # Extract subtitle URLs from info dict
            subtitles = info.get('subtitles', {})
            automatic_captions = info.get('automatic_captions', {})
            
            # Combine both subtitle sources
            all_subtitles = {}
            all_subtitles.update(subtitles)
            all_subtitles.update(automatic_captions)
            
            if not all_subtitles:
                raise ValueError("No subtitles found in video info")
            
            # Prefer English, but use any available language
            preferred_langs = ['en', 'en-US', 'en-GB']
            subtitle_url = None
            subtitle_lang = None
            
            for lang in preferred_langs:
                if lang in all_subtitles:
                    # Get the first subtitle URL (usually SRT or VTT)
                    subtitle_list = all_subtitles[lang]
                    if subtitle_list and len(subtitle_list) > 0:
                        subtitle_url = subtitle_list[0].get('url')
                        subtitle_lang = lang
                        break
            
            # If no preferred language, use the first available
            if not subtitle_url:
                for lang, subtitle_list in all_subtitles.items():
                    if subtitle_list and len(subtitle_list) > 0:
                        subtitle_url = subtitle_list[0].get('url')
                        subtitle_lang = lang
                        break
            
            if not subtitle_url:
                raise ValueError("No subtitle URL found in video info")
            
            print(f"✅ Found subtitle URL for language: {subtitle_lang}")
            
            # Download subtitle directly using requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.youtube.com/',
            }
            
            # Load cookies if available
            session = requests.Session()
            if cookies_file:
                try:
                    jar = MozillaCookieJar(cookies_file)
                    jar.load(ignore_discard=True, ignore_expires=True)
                    session.cookies = jar
                    print(f"🍪 Using cookies for subtitle download ({len(session.cookies)} cookies)")
                except Exception as cookie_error:
                    print(f"⚠️ Could not load cookies: {cookie_error}")
            
            # Download subtitle content
            response = session.get(subtitle_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            subtitle_content = response.text
            if not subtitle_content or len(subtitle_content.strip()) == 0:
                raise ValueError("Subtitle content is empty")
            
            # Check if it's VTT format and convert to SRT if needed
            if subtitle_url.endswith('.vtt') or 'fmt=vtt' in subtitle_url or subtitle_content.strip().startswith('WEBVTT'):
                print(f"🔄 Converting VTT to SRT format...")
                subtitle_content = _convert_vtt_to_srt(subtitle_content)
            
            # Write subtitle file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(subtitle_content)
            
            file_size = os.path.getsize(output_path)
            print(f"✅ Successfully downloaded subtitles to {output_path} ({file_size} bytes)")
            return  # Success!
            
        except Exception as e:
            error_msg = str(e).lower()
            if attempt < max_retries - 1:
                print(f"⚠️ Alternative method failed (attempt {attempt + 1}), retrying... ({str(e)[:100]})")
                time.sleep(3)
                continue
            else:
                raise FileNotFoundError(f"Could not download SRT subtitle for {video_url}: {e}")

    # If we get here, all methods failed
    raise FileNotFoundError(f"Could not find SRT subtitle for {video_url} after {max_retries} attempts")


def _convert_vtt_to_srt(vtt_content: str) -> str:
    """Convert WebVTT format to SRT format."""
    lines = vtt_content.strip().split('\n')
    srt_lines = []
    subtitle_index = 1
    i = 0
    
    # Skip WebVTT header and metadata
    while i < len(lines):
        line = lines[i].strip()
        if line == 'WEBVTT' or line.startswith('WEBVTT'):
            i += 1
            # Skip metadata lines (until we hit a blank line)
            while i < len(lines) and lines[i].strip() != '':
                i += 1
            i += 1  # Skip blank line
            break
        i += 1
    
    # Parse subtitle entries
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check if this is a timestamp line
        if '-->' in line:
            # This is a timestamp line
            # Convert VTT timestamp to SRT format (replace . with ,)
            timestamp = line.replace('.', ',')
            
            # Get the subtitle text (next non-empty lines until blank line)
            subtitle_text = []
            i += 1
            while i < len(lines) and lines[i].strip() != '':
                text_line = lines[i].strip()
                # Remove VTT cue settings (like position, align, etc.)
                if not text_line.startswith(('<', '&')):
                    subtitle_text.append(text_line)
                i += 1
            
            if subtitle_text:
                # Write SRT entry
                srt_lines.append(str(subtitle_index))
                srt_lines.append(timestamp)
                srt_lines.append('\n'.join(subtitle_text))
                srt_lines.append('')  # Blank line between entries
                subtitle_index += 1
        else:
            i += 1
    
    return '\n'.join(srt_lines)


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
