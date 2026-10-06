# 🏂 Snowboard Coach AI

An AI-powered snowboarding coaching platform that analyzes your snowboarding videos and provides personalized coaching advice using Replicate's advanced AI models.

The repository is evolving into a **Snowboard Vision Data Platform**. Milestone 1 adds a FastAPI media service, a separate worker, persistent video/job/frame records, real FFmpeg extraction, and a browser progress view without removing the existing coaching workflow. See [the media service guide](media_service/README.md) and [architecture](docs/media-architecture.md).

Milestone 2 adds persisted annotation tasks and a browser workspace for normalized bounding boxes and pose keypoints. It includes frame navigation, drag/resize editing, keyboard shortcuts, save-before-navigation, and per-frame annotation timing. See [the annotation workflow](docs/annotation-workflow.md).

Milestone 3 adds asynchronous detection and pose runs, immutable versioned predictions, Accept/Correct/Reject decisions, and measured model-assistance metrics. See [the model-assisted labeling workflow](docs/model-assisted-labeling.md).

The real-video benchmark exercises the full FFmpeg and Ultralytics path on licensed YouTube
snowboarding footage and records temporal and semantic failure modes. See
[the evaluation report](docs/real-video-evaluation.md) and
[the Milestone 4 plan](docs/milestone-4-plan.md).

Milestone 4A adds automatic quality routing, random audits, review events, multi-annotator IoU/PCK
agreement, and a dataset-health dashboard. See
[the review and dataset-health workflow](docs/review-and-dataset-health.md).

## ✨ Features

- **Video Upload**: Drag and drop or click to upload snowboarding videos
- **AI Analysis**: Advanced video analysis using Replicate's LLaVA and LLaMA models
- **Real-time Chat**: Interactive chatbot for personalized coaching advice
- **Technical Analysis**: Detailed feedback on:
  - Body position and posture
  - Edge control and board angle
  - Balance and weight distribution
  - Arm and shoulder positioning
  - Overall technique and areas for improvement

## 🚀 Quick Start

### Prerequisites

- Node.js (v16 or higher)
- Replicate API token
- FFmpeg (for video processing)

### Installation

1. **Clone and install dependencies:**
   ```bash
   git clone <your-repo-url>
   cd SkateboardCoaching
   npm run install-all
   ```

2. **Set up environment variables:**
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` and add your Replicate API token:
   ```
   REPLICATE_API_TOKEN=your_replicate_api_token_here
   ```

3. **Install FFmpeg:**
   
   **macOS:**
   ```bash
   brew install ffmpeg
   ```
   
   **Windows:**
   Download from [FFmpeg website](https://ffmpeg.org/download.html)
   
   **Linux:**
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```

4. **Start the application:**
   ```bash
   npm run dev
   ```

   This will start both the backend server (port 5001) and React frontend (port 3000).

### Run the asynchronous media pipeline

The media pipeline can run with local SQLite storage:

```bash
cd media_service
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Start the worker in a second terminal:

```bash
cd media_service
.venv/bin/python -m app.worker
```

Alternatively, `docker compose up --build` starts the API, worker, and PostgreSQL together.

## 🛠️ Technology Stack

### Backend
- **Node.js** with Express
- **Replicate API** for AI video analysis
- **LLaVA** for image understanding
- **LLaMA** for text synthesis
- **FFmpeg** for video processing and frame extraction
- **Multer** for file uploads
- **CORS** for cross-origin requests

### Frontend
- **React** with TypeScript
- **Material-UI** for modern UI components
- **Axios** for API calls

## 📁 Project Structure

```
SkateboardCoaching/
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── App.tsx         # Main app component
│   │   └── index.tsx       # Entry point
│   └── package.json
├── server/                 # Node.js backend
│   └── index.js           # Express server
├── uploads/               # Temporary video storage
├── package.json           # Root package.json
└── README.md
```

## 🔧 API Endpoints

- `POST /api/upload` - Upload and analyze video
- `GET /api/health` - Health check

## 🎯 How It Works

1. **Video Upload**: User uploads a snowboarding video
2. **Frame Extraction**: FFmpeg extracts key frames from the video
3. **AI Analysis**: Frames are analyzed using Replicate's LLaVA model
4. **Coaching Advice**: AI analyzes technique and provides detailed feedback
5. **Interactive Chat**: User can ask follow-up questions

## 🔑 Getting Replicate API Token

1. Visit [Replicate Platform](https://replicate.com/)
2. Sign up or log in to your account
3. Go to your account settings
4. Create a new API token
5. Add it to your `.env` file

## 🚨 Important Notes

- **File Size Limit**: Videos are limited to 50MB
- **Supported Formats**: MP4, MOV, AVI, WebM
- **Processing Time**: Analysis typically takes 10-30 seconds
- **API Costs**: Replicate charges per second of compute - very affordable!

## 🛡️ Security

- Video files are temporarily stored and automatically deleted after processing
- No permanent storage of user videos
- API keys should be kept secure and not committed to version control

## 🚀 Deployment

### Environment Variables for Production
```env
REPLICATE_API_TOKEN=your_production_api_token
PORT=5000
NODE_ENV=production
MAX_FILE_SIZE=50000000
```

### Deploy to Heroku
1. Create a Heroku app
2. Set environment variables
3. Deploy the backend
4. Deploy the frontend to Netlify or Vercel

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

If you encounter any issues:
1. Check that FFmpeg is installed
2. Verify your Replicate API token is correct
3. Ensure you have sufficient Replicate credits
4. Check the console for error messages

## 🔮 Future Enhancements

- [ ] User authentication and profiles
- [ ] Video history and progress tracking
- [ ] Advanced pose detection with MediaPipe
- [ ] Real-time video analysis
- [ ] Mobile app version
- [ ] Social features and sharing
- [ ] Integration with fitness trackers
