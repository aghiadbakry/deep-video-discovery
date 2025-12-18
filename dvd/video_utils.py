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
    Downloads an SRT subtitle from a YouTube URL using youtube-transcript-api.
    
    This is a simple and reliable approach that handles all the complexity internally.
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    
    if not _is_youtube_url(video_url):
        raise ValueError("Provided URL is not a valid YouTube link.")

    # Extract video ID from URL
    if 'v=' in video_url:
        video_id = video_url.split('v=')[1].split('&')[0]
    elif 'youtu.be/' in video_url:
        video_id = video_url.split('youtu.be/')[1].split('?')[0]
    else:
        raise ValueError(f"Could not extract video ID from {video_url}")

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # Check for proxy configuration (optional - set via environment variables)
    proxy_username = os.environ.get('YOUTUBE_PROXY_USERNAME', None)
    proxy_password = os.environ.get('YOUTUBE_PROXY_PASSWORD', None)
    
    try:
        # Configure YouTube Transcript API with optional proxy
        if proxy_username and proxy_password:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            print(f"🌐 Using proxy for subtitle download...")
            ytt_api = YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=proxy_username,
                    proxy_password=proxy_password,
                )
            )
        else:
            # No proxy - use default
            ytt_api = YouTubeTranscriptApi()
        
        # Fetch transcript directly (prefer English, but will use any available)
        print(f"🔄 Fetching transcript for video {video_id}...")
        
        # Try English first, then any available language
        transcript_data = None
        try:
            transcript_data = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
            print(f"✅ Found English transcript")
        except:
            # If no English, try any available language
            try:
                transcript_data = ytt_api.fetch(video_id)
                print(f"✅ Found transcript in available language")
            except Exception as fetch_error:
                raise NoTranscriptFound(video_id, None, None, None) from fetch_error
        
        if not transcript_data:
            raise NoTranscriptFound(video_id, None, None, None)
        
        # Convert to SRT format
        srt_content = _convert_transcript_to_srt(transcript_data)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        file_size = os.path.getsize(output_path)
        print(f"✅ Successfully downloaded subtitles to {output_path} ({file_size} bytes)")
        
    except TranscriptsDisabled:
        raise FileNotFoundError(f"Transcripts are disabled for video {video_id}")
    except NoTranscriptFound:
        raise FileNotFoundError(f"No transcript found for video {video_id}")
    except Exception as e:
        raise FileNotFoundError(f"Could not download SRT subtitle for {video_url}: {e}")


def _convert_transcript_to_srt(transcript_data: list) -> str:
    """Convert YouTube transcript API data to SRT format."""
    srt_lines = []
    
    for index, entry in enumerate(transcript_data, start=1):
        start_time = entry['start']
        duration = entry.get('duration', 0)
        end_time = start_time + duration
        text = entry['text'].strip()
        
        # Convert seconds to SRT timestamp format (HH:MM:SS,mmm)
        start_srt = _seconds_to_srt_timestamp(start_time)
        end_srt = _seconds_to_srt_timestamp(end_time)
        
        srt_lines.append(str(index))
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(text)
        srt_lines.append('')  # Blank line between entries
    
    return '\n'.join(srt_lines)


def _seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


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
