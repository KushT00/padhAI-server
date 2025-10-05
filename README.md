# 🎓 PadhAI RAG API

A FastAPI-based backend for intelligent document Q&A using Retrieval-Augmented Generation (RAG). Students can upload PDFs, create FAISS indexes, and chat with their study materials using AI.

## 🚀 Features

- **PDF Document Processing**: Upload and index PDF study materials
- **RAG-Powered Q&A**: Ask questions and get accurate answers from your documents
- **User Authentication**: JWT-based authentication with Supabase
- **Vector Search**: FAISS for fast similarity search
- **AI Models**: 
  - Google Gemini for embeddings
  - Groq DeepSeek R1 for question answering

## 📋 Tech Stack

- **Framework**: FastAPI
- **AI/ML**: LangChain, FAISS, Google Generative AI, Groq
- **Database**: Supabase (PostgreSQL + Storage)
- **Authentication**: JWT tokens
- **Document Processing**: PyPDF, RecursiveCharacterTextSplitter

## 🛠️ Local Development Setup

### Prerequisites

- Python 3.11+
- Git
- Supabase account
- API keys for Google AI and Groq

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/KushT00/padhAI-server.git
cd padhAI-server
```

2. **Create virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your actual API keys
```

5. **Run the server**
```bash
uvicorn server:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## 🌐 Deploy to Render (Free Tier)

### Step 1: Prepare Your Repository

Your repository is already configured with:
- ✅ `requirements.txt`
- ✅ `Procfile`
- ✅ `runtime.txt`
- ✅ `.gitignore`

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with your GitHub account
3. No credit card required!

### Step 3: Deploy Web Service

1. **Click "New +"** → **"Web Service"**

2. **Connect your repository**: `KushT00/padhAI-server`

3. **Configure the service**:
   - **Name**: `padhai-server` (or your choice)
   - **Region**: Choose closest to you
   - **Branch**: `master`
   - **Root Directory**: Leave blank
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`

4. **Select Free Instance Type**: `Free` (512 MB RAM, auto-sleep after 15 min)

5. **Add Environment Variables** (click "Advanced" → "Add Environment Variable"):
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   SUPABASE_JWT_SECRET=your-jwt-secret
   GOOGLE_API_KEY=your-google-api-key
   GROQ_API_KEY=your-groq-api-key
   LANGCHAIN_TRACING_V2=false
   ```

6. **Click "Create Web Service"**

### Step 4: Wait for Deployment

- First build takes ~3-5 minutes
- Watch the logs for any errors
- Once deployed, you'll get a URL like: `https://padhai-server.onrender.com`

### Step 5: Update CORS in Your Frontend

Update your frontend to use the new Render URL:
```javascript
const API_URL = "https://padhai-server.onrender.com";
```

Also, add your frontend URL to `server.py` CORS settings (already configured for Vercel).

## 📡 API Endpoints

### Health Check
```bash
GET /
```

### Get User Folders
```bash
GET /folders
Headers: Authorization: Bearer <token>
```

### Index Folder
```bash
POST /index_folder
Headers: Authorization: Bearer <token>
Body: { "folder_name": "my-notes" }
```

### Chat with Documents
```bash
POST /chat
Headers: Authorization: Bearer <token>
Body: { "folder_name": "my-notes", "query": "Explain photosynthesis" }
```

### Debug Storage
```bash
GET /debug/list_storage/{folder_name}
Headers: Authorization: Bearer <token>
```

## 🔧 Configuration Files

### Procfile
Tells Render how to start the app:
```
web: uvicorn server:app --host 0.0.0.0 --port $PORT
```

### runtime.txt
Specifies Python version:
```
python-3.11.7
```

### requirements.txt
Lists all Python dependencies (auto-installed during deployment)

## ⚠️ Important Notes

### Free Tier Limitations

- **Auto-sleep**: Service sleeps after 15 minutes of inactivity
- **Cold starts**: First request after sleep takes ~30-60 seconds
- **750 hours/month**: Enough for 24/7 uptime on one service
- **No persistent disk**: FAISS indexes are stored in-memory (lost on restart)
  - Solution: Re-index folders after cold start, or use persistent storage (paid tier)

### Data Persistence Strategy

Since free tier has **no persistent disk**:
1. PDFs are stored in **Supabase Storage** (persistent)
2. FAISS indexes are created **on-demand** from Supabase
3. Users may need to **re-index** after long inactivity

To improve this:
- Add caching logic to check if index exists
- Automatically re-index on first chat request
- Or upgrade to Render paid tier ($7/month) for persistent disk

## 🔒 Security Best Practices

- ✅ Never commit `.env` file (already in `.gitignore`)
- ✅ Use Supabase Service Role Key only on backend
- ✅ Validate JWT tokens on every request
- ✅ Enable CORS only for trusted domains
- ✅ Store sensitive data in Render environment variables

## 🐛 Troubleshooting

### Build Fails
- Check `requirements.txt` for typos
- Verify Python version matches `runtime.txt`
- Check Render build logs for specific errors

### Cold Start Issues
- First request takes ~30-60s after sleep
- Consider keeping service awake with a cron job (external ping service)

### Authentication Errors
- Verify all Supabase environment variables are set correctly
- Check JWT token format: `Bearer <token>`
- Ensure `SUPABASE_JWT_SECRET` matches your Supabase project

### FAISS Index Not Found
- Re-run `/index_folder` endpoint
- Check Supabase Storage has PDFs in correct path: `{user_id}/{folder_name}/`

## 📊 Monitoring

Enable LangSmith tracing (optional):
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key
LANGCHAIN_PROJECT=PadhAI-RAG
```

## 🚀 Production Recommendations

For production deployment:
1. **Upgrade to paid tier** ($7/month) for:
   - Persistent disk storage
   - No auto-sleep
   - Better performance
2. **Add health check endpoint** monitoring
3. **Set up logging** (Sentry, LogRocket)
4. **Add rate limiting** (SlowAPI)
5. **Implement caching** (Redis)

## 📝 License

MIT License - Feel free to use for your projects!

## 🤝 Contributing

Pull requests welcome! For major changes, please open an issue first.

## 📧 Support

For issues, open a GitHub issue or contact the maintainer.

---

**Built with ❤️ for students by students**
