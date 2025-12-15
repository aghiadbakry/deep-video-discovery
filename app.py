import json
import os, argparse, gradio as gr
import base64
from dvd import config

# Load .env file if it exists (for local development)
# In Render deployments, environment variables are set through Render dashboard
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip (Render uses platform env vars)

# Handle base64-encoded cookies if provided (for Render environment variables)
cookies_b64 = os.environ.get('YOUTUBE_COOKIES_B64')
if cookies_b64:
    cookies_path = '/tmp/youtube_cookies.txt'
    try:
        with open(cookies_path, 'wb') as f:
            f.write(base64.b64decode(cookies_b64))
        os.environ['YOUTUBE_COOKIES'] = cookies_path
        print(f"✅ YouTube cookies loaded from base64")
    except Exception as e:
        print(f"⚠️ Failed to decode cookies: {e}")
from dvd.dvd_core import DVDCoreAgent
from dvd.video_utils import load_video, decode_video_to_frames, download_srt_subtitle
from dvd.frame_caption import process_video, process_video_lite
from dvd.utils import extract_answer

########################################################################
# Helper functions
########################################################################
def get_youtube_thumbnail(video_url: str):
    """Extract YouTube video ID and return thumbnail URL."""
    if not video_url:
        return None
    
    # Extract video ID from YouTube URL
    video_id = None
    if "youtube.com/watch?v=" in video_url:
        video_id = video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        video_id = video_url.split("youtu.be/")[1].split("?")[0]
    
    if video_id:
        # YouTube provides several thumbnail qualities
        # maxresdefault > hqdefault > mqdefault > default
        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    
    return None

def _prepare_video_assets(video_url: str):
    """Download / decode / caption the video exactly as in local_run.py,
       returning (video_id, caption_file, video_db_path)."""
    # --- reuse logic from local_run.py (trimmed for brevity) -------------
    if "v=" in video_url:                         # YouTube URL
        video_id = video_url.split("v=")[1]
    else:                                         # local file or misc.
        video_id = os.path.splitext(os.path.basename(video_url))[0]

    video_path   = os.path.join(config.VIDEO_DATABASE_FOLDER, "raw", f"{video_id}.mp4")
    frames_dir   = os.path.join(config.VIDEO_DATABASE_FOLDER, video_id, "frames")
    captions_dir = os.path.join(config.VIDEO_DATABASE_FOLDER, video_id, "captions")
    video_db_path= os.path.join(config.VIDEO_DATABASE_FOLDER, video_id, "database.json")
    srt_path     = os.path.join(config.VIDEO_DATABASE_FOLDER, video_id, "subtitles.srt")
    os.makedirs(os.path.join(config.VIDEO_DATABASE_FOLDER, "raw"), exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(captions_dir, exist_ok=True)

    if config.LITE_MODE:
        if not os.path.exists(srt_path):
            download_srt_subtitle(video_url, srt_path)
        process_video_lite(captions_dir, srt_path)
        caption_file = os.path.join(captions_dir, "captions.json")
    else:
        if not os.path.exists(video_path):
            load_video(video_url, video_path)
        if not os.path.exists(frames_dir) or not os.listdir(frames_dir):
            decode_video_to_frames(video_path)
        caption_file = os.path.join(captions_dir, "captions.json")
        if not os.path.exists(caption_file):
            process_video(frames_dir, captions_dir)

    return video_id, caption_file, video_db_path

def solve(video_url: str, question: str):
    """Streamed inference function used by Gradio."""
    if not video_url or not question:
        yield "❗ Please provide both a video URL and a question."
        return

    try:
        yield "🔄 **Processing video...**"
        _, caption_file, video_db_path = _prepare_video_assets(video_url)
        
        yield "🤖 **Initializing DVD agent...**"
        agent = DVDCoreAgent(video_db_path, caption_file, config.MAX_ITERATIONS)

        accumulated_text = "### 🎯 Analysis Process:\n"
        final_answer = None
        
        for msg in agent.stream_run(question):
            # Only process messages with a role attribute
            if not isinstance(msg, dict) or "role" not in msg:
                continue
                
            # Show assistant's thinking process
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content:
                    accumulated_text += f"\n\n**🤔 Assistant Thinking:**\n{content}"
                    yield accumulated_text
                    
                # Check if assistant called the finish function
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if tc.get("function", {}).get("name") == "finish":
                        try:
                            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            final_answer = args.get("answer", "")
                        except:
                            pass
            
            # Show when a tool is being called
            elif msg.get("role") == "tool_call":
                tool_name = msg.get("name", "unknown")
                tool_args = msg.get("arguments", "{}")
                try:
                    args_dict = json.loads(tool_args)
                    args_dict.pop("database", None)
                    # Format arguments nicely
                    args_str = json.dumps(args_dict, indent=2)
                except:
                    args_str = tool_args
                if tool_name != "finish":
                    accumulated_text += f"\n\n**🔄 Calling Tool:** `{tool_name}`\n```json\n{args_str}\n```"
                yield accumulated_text
                            
            # Show tool observations
            elif msg.get("role") == "tool":
                tool_name = msg.get("name", "unknown")
                tool_result = msg.get("content", "")
                
                # Truncate long results for display
                if len(tool_result) > 2000:
                    tool_result = tool_result[:2000] + "..."
                    
                accumulated_text += f"\n\n**✅ Tool Result `{tool_name}`:**\n```\n{tool_result}\n```"
                yield accumulated_text
        
        # Add final answer if found
        if final_answer:
            accumulated_text += f"\n### 📃✅ **Final Answer:**\n\n{final_answer}"
        else:
            accumulated_text += "\n\n---\n### ✅ **Analysis Complete!**"
            
        yield accumulated_text
                
    except Exception as e:
        import traceback
        yield f"### ⚠️ Error Occurred\n\n```\n{e}\n```\n\nDetails:\n```\n{traceback.format_exc()}\n```"

########################################################################
# Gradio UI
########################################################################
def launch(args):
    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        font-family: 'Inter', sans-serif;
    }
    .markdown-text {
        font-size: 16px;
    }
    #answer-box {
        border: 2px solid #e5e7eb;
        border-radius: 8px;
        padding: 20px;
        background-color: #f9fafb;
        min-height: 400px;
        max-height: 600px;
        overflow-y: auto;
    }
    .button-primary {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        font-size: 18px;
        padding: 12px 24px;
    }
    #video-thumbnail {
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    """
    
    with gr.Blocks(title="DVD Video Q&A Demo", css=custom_css, theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # 🎬 Deep Video Discovery: Agentic Search with Tool Use for Long-form Video Understanding
            
            <p style="font-size: 18px; color: #6b7280;">
            Provide a YouTube URL, then ask any question about the video content. 
            The system will analyze the video and provide detailed answers.
            </p>
            """
        )
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📹 Video Input")
                video_url = gr.Textbox(
                    label="Video URL / Path",
                    placeholder="e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    lines=1,
                    info="Support YouTube URLs or local video paths"
                )
                
                # Add video thumbnail
                video_thumbnail = gr.Image(
                    label="Video Thumbnail",
                    elem_id="video-thumbnail",
                    height=200,
                    visible=False,
                    interactive=False
                )
                
                gr.Markdown("### ❓ Your Question")
                question = gr.Textbox(
                    label="Question about the video",
                    placeholder="What happens in this video? Who are the main characters?",
                    lines=3,
                    info="Ask anything about the video content"
                )
                
                with gr.Row():
                    run_btn = gr.Button("🔍 Analyze Video", variant="primary", elem_classes=["button-primary"])
                    clear_btn = gr.ClearButton([video_url, question, video_thumbnail], value="🗑️ Clear")
                
                gr.Markdown("### 💡 Example Questions")
                examples = gr.Examples(
                    examples=[
                        ["https://www.youtube.com/watch?v=i2qSxMVeVLI", "What is the main topic discussed in this video?"],
                        ["https://www.youtube.com/watch?v=nOxKexn3iBo", "Who are the speakers and what are their key points?"],
                    ],
                    inputs=[video_url, question],
                    label=""
                )
                
            with gr.Column(scale=2):
                gr.Markdown("### 📊 Analysis Results")
                answer_box = gr.Markdown(
                    value="*Results will appear here after clicking 'Analyze Video'...*",
                    elem_id="answer-box",
                    label=""
                )
        
        gr.Markdown(
            """
            ---
            <p style="text-align: center; color: #9ca3af; font-size: 14px;">
            DVD: Powered by advanced video understanding and language models | 
            Deployed on <a href="https://render.com" style="color: #6366f1;">Render</a>
            </p>
            """
        )
        
        # Event handlers
        def update_thumbnail(url):
            """Update thumbnail when URL changes."""
            thumbnail_url = get_youtube_thumbnail(url)
            if thumbnail_url:
                return gr.update(value=thumbnail_url, visible=True)
            else:
                return gr.update(value=None, visible=False)
        
        video_url.change(
            fn=update_thumbnail,
            inputs=[video_url],
            outputs=[video_thumbnail]
        )
        
        import inspect
        click_kwargs = dict(fn=solve, inputs=[video_url, question], outputs=answer_box)
        if "stream" in inspect.signature(gr.Button.click).parameters:
            click_kwargs["stream"] = True
        run_btn.click(**click_kwargs)

    # Render-specific configuration
    # Render automatically sets PORT environment variable
    render_port = int(os.environ.get("PORT", "10000"))
    demo.launch(server_name="0.0.0.0", server_port=render_port, share=False)

########################################################################
# CLI entry-point
########################################################################
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="Gradio share flag (ignored on Render)")
    args = parser.parse_args()
    launch(args)

