const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const Replicate = require('replicate');
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('ffmpeg-static');
const { v4: uuidv4 } = require('uuid');

// Set FFmpeg path
ffmpeg.setFfmpegPath(ffmpegPath);
const { analyzeSnowboardingVideoAdvanced } = require('./replicate-models');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5001;

// Initialize Replicate
const replicate = new Replicate({
  auth: process.env.REPLICATE_API_TOKEN,
});

// Test Replicate connection
console.log('Replicate API Token:', process.env.REPLICATE_API_TOKEN ? 'Set' : 'Not set');

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('uploads'));

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadDir = 'uploads';
    if (!fs.existsSync(uploadDir)) {
      fs.mkdirSync(uploadDir, { recursive: true });
    }
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueName = `${uuidv4()}-${file.originalname}`;
    cb(null, uniqueName);
  }
});

const upload = multer({
  storage: storage,
  limits: {
    fileSize: parseInt(process.env.MAX_FILE_SIZE) || 50000000 // 50MB default
  },
  fileFilter: (req, file, cb) => {
    console.log('File filter - mimetype:', file.mimetype, 'originalname:', file.originalname);
    if (file.mimetype.startsWith('video/') || file.originalname.match(/\.(mp4|mov|avi|webm)$/i)) {
      cb(null, true);
    } else {
      cb(new Error('Only video files are allowed!'), false);
    }
  }
});

// Extract frames from video
const extractFrames = (videoPath, outputDir) => {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    ffmpeg(videoPath)
      .screenshots({
        timestamps: ['5%', '15%', '25%', '35%', '45%', '55%', '65%', '75%', '85%', '95%'], // Extract 10 frames for better analysis
        filename: 'frame-%i.png',
        folder: outputDir,
        size: '640x480'
      })
      .on('end', () => {
        console.log('Frames extracted successfully');
        resolve();
      })
      .on('error', (err) => {
        console.error('Error extracting frames:', err);
        reject(err);
      });
  });
};

// Convert image to base64
const imageToBase64 = (imagePath) => {
  const imageBuffer = fs.readFileSync(imagePath);
  return imageBuffer.toString('base64');
};


// Routes
app.post('/api/upload', upload.single('video'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No video file uploaded' });
    }

    const videoPath = req.file.path;
    const frameDir = path.join('uploads', 'frames', req.file.filename);
    
    // Extract frames from video
    await extractFrames(videoPath, frameDir);
    
    // Get frame files
    const frameFiles = fs.readdirSync(frameDir)
      .filter(file => file.endsWith('.png'))
      .map(file => path.join(frameDir, file))
      .sort();

    // Analyze frames with Replicate (Advanced: Pose + Image + Text)
    console.log('Starting Replicate analysis...');
    console.log('Frame files:', frameFiles.length);
    
    let analysis;
    try {
      // Use multi-frame analysis for better results
      const { analyzeSnowboardingVideoMultiFrame } = require('./replicate-models');
      analysis = await analyzeSnowboardingVideoMultiFrame(frameFiles);
      console.log('Multi-frame analysis completed successfully');
    } catch (error) {
      console.error('Multi-frame analysis failed, trying single frame:', error);
      // Fallback to single frame analysis
      analysis = await analyzeSnowboardingVideoAdvanced(frameFiles);
      console.log('Single frame analysis completed successfully');
    }

    // Clean up temporary files
    fs.unlinkSync(videoPath);
    frameFiles.forEach(frameFile => fs.unlinkSync(frameFile));
    fs.rmdirSync(frameDir);

    res.json({
      success: true,
      analysis: analysis,
      message: 'Video analyzed successfully'
    });

  } catch (error) {
    console.error('Upload error:', error);
    console.error('Error stack:', error.stack);
    res.status(500).json({ 
      error: 'Failed to process video',
      details: error.message 
    });
  }
});

app.get('/api/health', (req, res) => {
  res.json({ status: 'Server is running', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/api/health`);
});
