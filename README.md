# Deep Video Discovery - Render Deployment

This is the Render-specific deployment of Deep Video Discovery.

## 🚀 Quick Deploy to Render

1. **Push this directory to GitHub**
2. **Go to Render**: https://render.com
3. **New +** → **Web Service**
4. **Connect your GitHub repository**
5. **Configure:**
   - Build Command: `pip install -r requirements.txt && pip install gradio`
   - Start Command: `python app.py`
6. **Set Environment Variable:**
   - Key: `OPENAI_API_KEY`
   - Value: Your OpenAI API key
7. **Create Web Service**
8. **Done!** Access at `https://your-app.onrender.com`

## ✅ Features

- ✅ Full network access (YouTube downloads work!)
- ✅ Auto-deploy on git push
- ✅ HTTPS enabled automatically
- ✅ Real-time logs
- ✅ Persistent storage available (paid plans)

## 📋 Requirements

- OpenAI API key
- Render account (free tier available)

## 🔧 Configuration

Set these environment variables in Render Dashboard:
- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `VIDEO_DATABASE_FOLDER` - Optional, defaults to `/tmp/video_database/`

## 📚 Documentation

See `../RENDER_DEPLOY.md` for detailed deployment instructions.

