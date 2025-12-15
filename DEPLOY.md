# Render Deployment Guide

## Step-by-Step Instructions

### 1. Push to GitHub
```bash
cd render
git init
git add .
git commit -m "Initial commit for Render"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Deploy to Render

1. Go to https://render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select the repository
5. Configure:
   - **Name**: `dvd-app`
   - **Build Command**: `pip install -r requirements.txt && pip install gradio`
   - **Start Command**: `python app.py`
6. **Environment Variables**:
   - Add `OPENAI_API_KEY` = Your API key
7. Click **"Create Web Service"**
8. Wait 3-5 minutes for deployment
9. Access at `https://your-app.onrender.com`

## ✅ What's Configured

- ✅ App uses Render's `PORT` environment variable
- ✅ Server binds to `0.0.0.0` for external access
- ✅ Full network access (YouTube works!)
- ✅ Auto-deploy on git push

## 🔧 Troubleshooting

- **Build fails**: Check build logs, verify all dependencies in requirements.txt
- **Service crashes**: Check runtime logs, verify API key is set
- **Network issues**: Render has full network access, should work fine

See `../RENDER_DEPLOY.md` for more details.

