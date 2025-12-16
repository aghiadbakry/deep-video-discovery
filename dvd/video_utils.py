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
    """Downloads an SRT subtitle from a YouTube URL with anti-bot detection.
    
    Uses direct subtitle URL extraction to avoid format validation issues.
    """
    import time
    import requests
    from yt_dlp.utils import DownloadError, ExtractorError
    
    if not _is_youtube_url(video_url):
        raise ValueError("Provided URL is not a valid YouTube link.")

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

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

    # IMPORTANT: When cookies are available, use 'web' client only
    # Android/iOS clients don't support cookies!
    if cookies_file:
        # With cookies, only use web client (cookies don't work with android/ios)
        max_retries = 3
        player_clients = [
            ['web'],  # Web client supports cookies
            ['web'],  # Retry with web
            ['web'],  # Final retry with web
        ]
    else:
        # Without cookies, try different clients
        max_retries = 5
        player_clients = [
            ['android'],  # First try: android only (most reliable)
            ['ios'],  # Second try: ios
            ['web'],  # Third try: web
            ['android', 'web'],  # Fourth try: android + web
            ['ios', 'android', 'web'],  # Fifth try: all clients
        ]

    for attempt in range(max_retries):
        try:
            # Enhanced yt-dlp options to avoid bot detection
            # Since we only need subtitles (skip_download=True), we don't need to specify format
            # Try without format first, then with format if needed
            ydl_opts = {
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'skip_download': True,
                'writeautomaticsub': True,
                'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
                # Since we only need subtitles, use a format that always exists
                # 'worst' format is always available, and we skip download anyway
                'format': 'worst',  # Use worst format (we don't download it anyway)
                'ignoreerrors': False,
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
                print(f"🍪 Attempt {attempt + 1}: Using cookies for authentication")
            else:
                print(f"🔄 Attempt {attempt + 1}: No cookies available, using default method")

            # ALTERNATIVE APPROACH: Extract subtitles directly from info WITHOUT format processing
            # This completely bypasses format validation issues
            try:
                # Create minimal options just for info extraction (no format processing)
                info_opts = {
                    'quiet': False,
                    'no_warnings': False,
                    'skip_download': True,  # We don't need to download video
                }
                if cookies_file:
                    info_opts['cookiefile'] = cookies_file
                    info_opts['extractor_args'] = {
                        'youtube': {
                            'player_client': ['web'],  # Web client supports cookies
                        }
                    }
                
                print(f"🔍 Attempting direct subtitle extraction (bypassing format validation)...")
                
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    # Extract info WITHOUT processing formats - this is key!
                    # process=False means we don't validate formats, just get metadata
                    info = ydl.extract_info(video_url, download=False, process=False)
                    video_id = info.get('id') or info.get('display_id')
                    
                    if not video_id:
                        # Fallback: extract from URL
                        if 'v=' in video_url:
                            video_id = video_url.split('v=')[1].split('&')[0]
                    
                    print(f"📹 Video ID: {video_id}")
                    
                    # Now manually extract subtitle URLs from the raw info
                    # yt-dlp stores subtitles in different places depending on extractor
                    subtitles = {}
                    auto_captions = {}
                    
                    # Try to get subtitles from various possible locations in info dict
                    if 'subtitles' in info:
                        subtitles = info['subtitles']
                    if 'automatic_captions' in info:
                        auto_captions = info['automatic_captions']
                    
                    # Also check in player_response if available
                    if 'player_response' in info:
                        player_resp = info['player_response']
                        if 'captions' in player_resp:
                            captions = player_resp['captions']
                            if 'playerCaptionsTracklistRenderer' in captions:
                                tracks = captions['playerCaptionsTracklistRenderer'].get('captionTracks', [])
                                for track in tracks:
                                    lang = track.get('languageCode', 'unknown')
                                    base_url = track.get('baseUrl')
                                    if base_url:
                                        if lang not in subtitles:
                                            subtitles[lang] = []
                                        subtitles[lang].append({'url': base_url, 'ext': 'vtt'})
                    
                    print(f"📝 Found {len(subtitles)} subtitle languages, {len(auto_captions)} auto-caption languages")
                    
                    # Try to get English subtitles first
                    subtitle_url = None
                    subtitle_ext = 'srt'
                    
                    if 'en' in subtitles and subtitles['en']:
                        subtitle_info = subtitles['en'][0] if isinstance(subtitles['en'], list) else subtitles['en']
                        subtitle_url = subtitle_info.get('url') if isinstance(subtitle_info, dict) else None
                        if subtitle_url and isinstance(subtitle_info, dict):
                            subtitle_ext = subtitle_info.get('ext', 'vtt')
                    elif 'en' in auto_captions and auto_captions['en']:
                        subtitle_info = auto_captions['en'][0] if isinstance(auto_captions['en'], list) else auto_captions['en']
                        subtitle_url = subtitle_info.get('url') if isinstance(subtitle_info, dict) else None
                        if subtitle_url and isinstance(subtitle_info, dict):
                            subtitle_ext = subtitle_info.get('ext', 'vtt')
                    elif subtitles:
                        # Get first available subtitle
                        first_lang = list(subtitles.keys())[0]
                        subtitle_info = subtitles[first_lang][0] if isinstance(subtitles[first_lang], list) else subtitles[first_lang]
                        subtitle_url = subtitle_info.get('url') if isinstance(subtitle_info, dict) else None
                        if subtitle_url and isinstance(subtitle_info, dict):
                            subtitle_ext = subtitle_info.get('ext', 'vtt')
                    elif auto_captions:
                        first_lang = list(auto_captions.keys())[0]
                        subtitle_info = auto_captions[first_lang][0] if isinstance(auto_captions[first_lang], list) else auto_captions[first_lang]
                        subtitle_url = subtitle_info.get('url') if isinstance(subtitle_info, dict) else None
                        if subtitle_url and isinstance(subtitle_info, dict):
                            subtitle_ext = subtitle_info.get('ext', 'vtt')
                    
                    if subtitle_url:
                        print(f"✅ Found subtitle URL: {subtitle_url[:80]}...")
                        # Download subtitle directly from URL
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'Accept': 'text/vtt, text/srt, */*',
                        }
                        response = requests.get(subtitle_url, headers=headers, timeout=30)
                        if response.status_code == 200:
                            content = response.text
                            
                            # Convert VTT to SRT if needed
                            if subtitle_ext == 'vtt' or 'WEBVTT' in content:
                                print(f"🔄 Converting VTT to SRT format...")
                                # Simple VTT to SRT conversion
                                lines = content.split('\n')
                                srt_lines = []
                                counter = 1
                                i = 0
                                while i < len(lines):
                                    line = lines[i].strip()
                                    if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.startswith('Kind:'):
                                        i += 1
                                        continue
                                    if '-->' in line:
                                        # This is a timestamp line
                                        srt_lines.append(str(counter))
                                        counter += 1
                                        srt_lines.append(line)
                                        i += 1
                                        # Next line(s) are the subtitle text
                                        text_lines = []
                                        while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                                            text_lines.append(lines[i].strip())
                                            i += 1
                                        srt_lines.append('\n'.join(text_lines))
                                        srt_lines.append('')  # Empty line between entries
                                    else:
                                        i += 1
                                content = '\n'.join(srt_lines)
                            
                            with open(output_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            print(f"✅ Successfully downloaded and saved subtitles to {output_path}")
                            return  # Success!
                        else:
                            print(f"⚠️ Failed to download subtitle: HTTP {response.status_code}")
                    else:
                        print(f"⚠️ No subtitle URL found in video info")
                        
            except Exception as direct_error:
                print(f"⚠️ Direct subtitle extraction failed: {direct_error}")
                import traceback
                print(traceback.format_exc())
                # Continue to fallback method
                
                # Download subtitles - even if format error occurs, subtitles may have been downloaded
                try:
                    ydl.download([video_url])
                except Exception as download_error:
                    # IMPORTANT: Check if subtitles were downloaded BEFORE the error
                    # Sometimes yt-dlp downloads subtitles but then fails on format validation
                    # yt-dlp names subtitle files as: <video_id>.<lang>.srt (e.g., i2qSxMVeVLI.en.srt)
                    downloaded_subtitle_path = None
                    
                    # List all files for debugging
                    all_files = os.listdir(output_dir)
                    print(f"🔍 Checking for subtitle files in {output_dir}")
                    print(f"📁 Files found: {all_files}")
                    
                    # Look for subtitle files - yt-dlp uses pattern: <video_id>.<lang>.srt
                    for f in all_files:
                        if f.startswith(video_id) and f.endswith(".srt"):
                            downloaded_subtitle_path = os.path.join(output_dir, f)
                            print(f"✅ Found subtitle file: {f}")
                            break
                    
                    if downloaded_subtitle_path:
                        # Subtitles were downloaded! Move them and return success
                        shutil.move(downloaded_subtitle_path, output_path)
                        print(f"✅ Subtitles downloaded successfully (format error occurred but subtitles are available)")
                        return  # Success!
                    
                    # If subtitles weren't downloaded, check if it's a format error
                    error_str = str(download_error).lower()
                    if "format" in error_str or "not available" in error_str:
                        print(f"⚠️ Format error during download, trying with ignoreerrors...")
                        # Try with ignoreerrors to skip format validation
                        ydl_opts_ignore = ydl_opts.copy()
                        ydl_opts_ignore['ignoreerrors'] = True
                        ydl_opts_ignore.pop('format', None)  # Remove format
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts_ignore) as ydl2:
                                ydl2.download([video_url])
                            
                            # Check again after ignoreerrors attempt
                            for f in os.listdir(output_dir):
                                if f.startswith(video_id) and f.endswith(".srt"):
                                    downloaded_subtitle_path = os.path.join(output_dir, f)
                                    break
                            
                            if downloaded_subtitle_path:
                                shutil.move(downloaded_subtitle_path, output_path)
                                print(f"✅ Subtitles downloaded with ignoreerrors")
                                return
                        except:
                            pass  # Continue to outer exception handler
                    else:
                        # Re-raise non-format errors
                        raise

            # Locate the downloaded subtitle file (yt-dlp names them as <id>.<lang>.srt)
            # List files for debugging
            all_files = os.listdir(output_dir)
            print(f"🔍 After download, checking for subtitle files in {output_dir}")
            print(f"📁 Files found: {all_files}")
            
            downloaded_subtitle_path = None
            for f in all_files:
                if f.startswith(video_id) and f.endswith(".srt"):
                    downloaded_subtitle_path = os.path.join(output_dir, f)
                    print(f"✅ Found subtitle file: {f}")
                    break

            if downloaded_subtitle_path:
                shutil.move(downloaded_subtitle_path, output_path)
                print(f"✅ Successfully moved subtitle file to {output_path}")
                return  # Success!
            else:
                # List what files actually exist for debugging
                print(f"❌ No subtitle file found. Video ID: {video_id}")
                print(f"📁 All files in {output_dir}: {os.listdir(output_dir)}")
                raise FileNotFoundError(f"Could not find SRT subtitle for {video_url}")
                
        except (DownloadError, ExtractorError) as e:
            error_msg = str(e).lower()
            
            # IMPORTANT: Check if subtitles were downloaded despite the error
            # Logs show "[info] Downloading subtitles: en" - they might be there!
            potential_video_id = None
            if 'v=' in video_url:
                potential_video_id = video_url.split('v=')[1].split('&')[0]
            
            if potential_video_id:
                for f in os.listdir(output_dir):
                    if f.startswith(potential_video_id) and f.endswith(".srt"):
                        downloaded_subtitle_path = os.path.join(output_dir, f)
                        shutil.move(downloaded_subtitle_path, output_path)
                        print(f"✅ Subtitles were downloaded successfully (format error ignored)")
                        return  # Success! Subtitles exist despite format error
            
            # Handle format errors - try without format specification
            if "format is not available" in error_msg or "requested format" in error_msg:
                if attempt < max_retries - 1:
                    # Try without format specification (let yt-dlp choose)
                    try:
                        ydl_opts_no_format = ydl_opts.copy()
                        # Remove format requirement entirely
                        ydl_opts_no_format.pop('format', None)
                        
                        print(f"🔄 Retrying without format specification (attempt {attempt + 2})")
                        
                        with yt_dlp.YoutubeDL(ydl_opts_no_format) as ydl:
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
                            print(f"✅ Successfully downloaded subtitles without format specification")
                            return  # Success!
                    except Exception as format_fix_error:
                        # Format fix didn't work, continue to normal error handling
                        print(f"⚠️ Format fix attempt failed: {format_fix_error}")
                        pass
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
                    # Check if cookies were used but expired
                    if cookies_file:
                        error_solution = (
                            f"YouTube bot detection after {max_retries} attempts.\n\n"
                            "**⚠️ Your cookies appear to be expired or invalid.**\n\n"
                            "**The logs show:** 'The provided YouTube account cookies are no longer valid. "
                            "They have likely been rotated in the browser as a security measure.'\n\n"
                            "**Solution: Refresh Your Cookies**\n\n"
                            "1. **Sign in to YouTube** in your browser (fresh login)\n"
                            "2. **Export cookies immediately** using browser extension\n"
                            "3. **Convert to base64** and update `YOUTUBE_COOKIES_B64` in Render\n"
                            "4. **Redeploy** your service\n\n"
                            "**Important:**\n"
                            "- Export cookies RIGHT AFTER signing in (don't wait!)\n"
                            "- Cookies expire quickly - YouTube rotates them for security\n"
                            "- See `REFRESH_COOKIES.md` for detailed instructions\n\n"
                            "**Alternative:** Wait 10-15 minutes and try again (YouTube rate limiting)"
                        )
                    else:
                        error_solution = (
                            f"YouTube bot detection after {max_retries} attempts.\n\n"
                            "**This is a known issue with YouTube's anti-bot measures.**\n\n"
                            "**Immediate Solutions:**\n"
                            "1. Wait 5-10 minutes and try again (YouTube rate limiting)\n"
                            "2. Try a different video URL\n"
                            "3. The video may have restricted access\n\n"
                            "**Recommended Solution:**\n"
                            "Use YouTube cookies to authenticate:\n"
                            "1. Export cookies from your browser (see: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)\n"
                            "2. Convert to base64 and set `YOUTUBE_COOKIES_B64` in Render\n"
                            "3. Redeploy your service\n\n"
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