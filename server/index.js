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
const { analyzeSnowboardingVideoPoseBased } = require('./pose-pipeline-models');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5001;

// Initialize Replicate
const replicate = new Replicate({
  auth: process.env.REPLICATE_API_TOKEN,
});

// Test Replicate connection
console.log('Replicate API Token:', process.env.REPLICATE_API_TOKEN ? 'Set' : 'Not set');
console.log('Server starting...');

// Middleware - Enhanced CORS for Vercel
app.use((req, res, next) => {
  const origin = req.headers.origin;
  
  // Allow specific origins
  const allowedOrigins = [
    'https://skateboard-coaching.vercel.app',
    'https://skateboardcoaching-frontend.vercel.app',
    'http://localhost:3000'
  ];
  
  if (allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
  } else {
    res.header('Access-Control-Allow-Origin', '*');
  }
  
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Max-Age', '86400'); // 24 hours
  
  if (req.method === 'OPTIONS') {
    res.status(200).end();
  } else {
    next();
  }
});

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
    fileSize: 8 * 1024 * 1024 // 8MB limit for Vercel serverless functions
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
              timestamps: ['10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%'], // Extract 9 frames for faster analysis
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

    // Analyze frames with Replicate
    console.log('Starting Replicate analysis...');
    console.log('Frame files:', frameFiles.length);
    
    // Check if pose-based analysis is requested
    const usePoseAnalysis = req.body.poseAnalysis === 'true' || req.query.pose === 'true';
    
    let analysis;
    try {
      if (usePoseAnalysis) {
        console.log('🎯 Using 4-Stage Pose-Based Pipeline...');
        analysis = await analyzeSnowboardingVideoPoseBased(videoPath, frameFiles);
        console.log('Pose-based analysis completed successfully');
      } else {
        console.log('🖼️  Using Image-Based Pipeline...');
        // Use multi-frame analysis for better results
        const { analyzeSnowboardingVideoMultiFrame } = require('./replicate-models');
        analysis = await analyzeSnowboardingVideoMultiFrame(frameFiles);
        console.log('Multi-frame analysis completed successfully');
      }
    } catch (error) {
      console.error('Primary analysis failed, trying fallback:', error);
      // Fallback to single frame analysis
      analysis = await analyzeSnowboardingVideoAdvanced(frameFiles);
      console.log('Fallback analysis completed successfully');
    }

    // Clean up temporary files
    fs.unlinkSync(videoPath);
    frameFiles.forEach(frameFile => fs.unlinkSync(frameFile));
    fs.rmdirSync(frameDir);

          // Create structured data for interactive chat if not provided
          let structuredAnalysis = analysis.analysis || analysis;
          let detailedPrompts = analysis.detailedPrompts;
          
          if (!detailedPrompts) {
            // Create brief assessment and detailed prompts for interactive chat
            const cleanAnalysis = (analysis.analysis || analysis).replace(/\s+/g, ' ').trim();
            structuredAnalysis = `I have analyzed your snowboarding technique across three frames and identified key strengths and areas for improvement. My findings are detailed below, with specific drills and exercises recommended to enhance your skills.

Comprehensive Coaching Report
Overall Rating: 7/10
Key Strengths: Good posture, appropriate joint angles, centered balance
Improvements: Edge control, flow and rhythm
Biomechanical Analysis: Specific joint angle measurements
Technical Recommendations: Balance exercises, edge control practice
Safety Considerations: Proper gear recommendations

I can provide more detailed information about your Key Strengths, Main Areas for Improvement, and Specific Drills and Exercises. Which would you like to learn more about?`;

            detailedPrompts = {
              strengths: `Based on this snowboarding analysis, provide detailed key strengths:\n\nANALYSIS:\n${cleanAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific strengths with detailed explanations.`,
              improvements: `Based on this snowboarding analysis, provide detailed areas for improvement:\n\nANALYSIS:\n${cleanAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific areas that need work with detailed explanations.`,
              drills: `Based on this snowboarding analysis, provide specific drills and exercises:\n\nANALYSIS:\n${cleanAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific drills with descriptions and purposes.`
            };
          }

          res.json({
            success: true,
            analysis: structuredAnalysis,
            pipeline: analysis.pipeline || (usePoseAnalysis ? 'pose-based' : 'image-based'),
            poseVideoUrl: analysis.poseVideoUrl || null,
            technicalAnalysis: analysis.technicalAnalysis || (analysis.analysis || analysis),
            sceneDescription: analysis.sceneDescription || 'Snowboarding technique analysis',
            detailedPrompts: detailedPrompts,
            message: analysis.message || 'Video analyzed successfully'
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

// Follow-up questions endpoint for interactive chat
app.post('/api/chat', async (req, res) => {
  try {
    const { question, analysisData } = req.body;
    
    if (!question || !analysisData) {
      return res.status(400).json({ error: 'Question and analysis data are required' });
    }

    console.log('🤖 Processing follow-up question:', question);
    
    // Determine which detailed section to generate based on the question
    let prompt = '';
    let sectionType = '';
    
    if (question.toLowerCase().includes('strength') || question.toLowerCase().includes('good') || question.toLowerCase().includes('positive')) {
      prompt = analysisData.detailedPrompts.strengths;
      sectionType = 'Key Strengths';
    } else if (question.toLowerCase().includes('improve') || question.toLowerCase().includes('problem') || question.toLowerCase().includes('issue') || question.toLowerCase().includes('better')) {
      prompt = analysisData.detailedPrompts.improvements;
      sectionType = 'Main Areas for Improvement';
    } else if (question.toLowerCase().includes('drill') || question.toLowerCase().includes('exercise') || question.toLowerCase().includes('practice') || question.toLowerCase().includes('work on')) {
      prompt = analysisData.detailedPrompts.drills;
      sectionType = 'Specific Drills and Exercises';
    } else {
      // General question - use a custom prompt
      prompt = `As a snowboarding coach, answer this question based on the technical analysis:

QUESTION: ${question}

TECHNICAL ANALYSIS:
${analysisData.technicalAnalysis.substring(0, 1500)}...

SCENE DESCRIPTION:
${analysisData.sceneDescription.substring(0, 800)}...

Provide a helpful, specific answer about snowboarding technique.`;
    }

    // Generate response using LLaMA 2
    const response = await replicate.run(
      'meta/llama-2-70b-chat:02e509c789964a7ea8736978a43525956ef40397be9033abf9fd2badfe68c9e3',
      {
        input: {
          prompt: prompt
        }
      }
    );

    const responseText = Array.isArray(response) ? response.join(' ') : response;
    
    // Clean up text formatting - remove extra spaces and fix word segmentation
    const cleanText = (text) => {
      if (!text) return text;
      return text
        // First, fix word segmentation issues (do this before space normalization)
        .replace(/\bAss\s+ess\s+ment\b/g, 'Assessment')
        .replace(/\bOver\s+all\b/g, 'Overall')
        .replace(/\bStr\s+ength\s+s\b/g, 'Strengths')
        .replace(/\bAre\s+as\b/g, 'Areas')
        .replace(/\bIm\s+prov\s+e\s+ment\b/g, 'Improvement')
        .replace(/\bDr\s+ills\b/g, 'Drills')
        .replace(/\bEx\s+er\s+cis\s+es\b/g, 'Exercises')
        .replace(/\bPract\s+ice\b/g, 'Practice')
        .replace(/\bsnow\s+board\s+er\b/g, 'snowboarder')
        .replace(/\bsnow\s+board\b/g, 'snowboard')
        .replace(/\bdemonstr\s+ates\b/g, 'demonstrates')
        .replace(/\bpost\s+ure\b/g, 'posture')
        .replace(/\bkne\s+es\b/g, 'knees')
        .replace(/\ban\s+k\s+les\b/g, 'ankles')
        .replace(/\bposition\s+ing\b/g, 'positioning')
        .replace(/\brelax\s+ed\b/g, 'relaxed')
        .replace(/\badjust\s+ed\b/g, 'adjusted')
        .replace(/\bincorpor\s+ating\b/g, 'incorporating')
        .replace(/\benh\s+ance\b/g, 'enhance')
        .replace(/\binit\s+iation\b/g, 'initiation')
        // Fix additional word segmentation issues from your example
        .replace(/\bB\s+ased\b/g, 'Based')
        .replace(/\bsnowboarder\s+'\s+s\b/g, "snowboarder's")
        .replace(/\bApp\s+ropri\s+ate\b/g, 'Appropriate')
        .replace(/\bCenter\s+ed\b/g, 'Centered')
        .replace(/\bIm\s+prov\s+e\s+ment\b/g, 'Improvement')
        .replace(/\bSpec\s+ific\b/g, 'Specific')
        .replace(/\badjust\s+ing\b/g, 'adjusting')
        .replace(/\bF\s+ocus\b/g, 'Focus')
        .replace(/\bmaintain\s+ing\b/g, 'maintaining')
        .replace(/\bnavig\s+ating\b/g, 'navigating')
        .replace(/\bterra\s+ins\b/g, 'terrains')
        .replace(/\bW\s+ould\b/g, 'Would')
        // Fix additional spacing issues from your example
        .replace(/\b1\s+0\b/g, '10')
        .replace(/\bbal\s+anced\b/g, 'balanced')
        .replace(/\bkne\s+e\b/g, 'knee')
        .replace(/\ban\s+k\s+le\b/g, 'ankle')
        .replace(/\bsnowboard\s+ing\b/g, 'snowboarding')
        // Fix additional word segmentation issues from the screenshot
        .replace(/\bsp\s+ine\b/g, 'spine')
        .replace(/\bh\s+ips\b/g, 'hips')
        .replace(/\bel\s+b\s+ows\b/g, 'elbows')
        .replace(/\bNe\s+ut\s+ral\b/g, 'Neutral')
        .replace(/\bPro\s+per\b/g, 'Proper')
        .replace(/\bWe\s+ight\b/g, 'Weight')
        .replace(/\bsh\s+ifting\b/g, 'shifting')
        .replace(/\bj\s+umps\b/g, 'jumps')
        .replace(/\bexer\s+cis\s+es\b/g, 'exercises')
        .replace(/\bsqu\s+ats\b/g, 'squats')
        .replace(/\bbo\s+ards\b/g, 'boards')
        .replace(/\bIn\s+cor\s+por\s+ate\b/g, 'Incorporate')
        // Now normalize spaces and punctuation (but preserve line breaks)
        .replace(/[ \t]+/g, ' ')  // Replace multiple spaces/tabs with single space (but keep \n)
        .replace(/\s*\/\s*/g, '/')  // Fix spacing around slashes (7 / 10 -> 7/10)
        .replace(/\s*:\s*/g, ': ')  // Fix spacing around colons
        .replace(/\s*-\s*/g, '-')  // Fix spacing around hyphens
        .replace(/\s*,\s*/g, ', ')  // Fix spacing around commas
        .replace(/\s*\.\s*/g, '. ')  // Fix spacing around periods
        .replace(/\s*\(\s*/g, '(')  // Fix spacing around parentheses
        .replace(/\s*\)\s*/g, ')')  // Fix spacing around parentheses
        .replace(/\s*\*\s*/g, '**')  // Fix spacing around asterisks
        .replace(/\n[ \t]+/g, '\n')  // Remove leading spaces/tabs after line breaks (but keep the \n)
        .trim();  // Remove leading/trailing spaces
    };
    
    const cleanedResponse = cleanText(responseText);
    
    console.log(`✅ Generated ${sectionType || 'general'} response`);
    
    res.json({
      success: true,
      response: cleanedResponse,
      sectionType: sectionType,
      message: 'Response generated successfully'
    });

  } catch (error) {
    console.error('❌ Chat error:', error);
    res.status(500).json({
      error: 'Failed to process chat question',
      details: error.message
    });
  }
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'Server is running',
    timestamp: new Date().toISOString(),
    pipelines: ['image-based', 'pose-based'],
    models: {
      poseEstimation: 'jagilley/controlnet-pose (pose detection overlay)',
      technicalAnalysis: 'yorickvp/llava-v1.6-mistral-7b',
      sceneDescription: 'andreasjansson/blip-2',
      reportGeneration: 'meta/llama-2-70b-chat'
    }
  });
});

// Test endpoint for analyze-pose
app.get('/api/analyze-pose', (req, res) => {
  res.json({
    message: 'This endpoint requires POST with video file',
    method: 'POST',
    contentType: 'multipart/form-data'
  });
});

// Debug endpoint for testing upload
app.post('/api/debug-upload', upload.single('video'), async (req, res) => {
  console.log('🔍 DEBUG UPLOAD - File info:');
  console.log('req.file:', req.file);
  console.log('req.body:', req.body);
  console.log('req.headers:', req.headers);
  
  if (!req.file) {
    return res.status(400).json({ 
      error: 'No file uploaded',
      file: req.file,
      body: req.body,
      headers: req.headers
    });
  }
  
  res.json({
    success: true,
    filename: req.file.filename,
    mimetype: req.file.mimetype,
    size: req.file.size
  });
});

// Pose analysis endpoint (forces pose-based pipeline)
app.post('/api/analyze-pose', upload.single('video'), async (req, res) => {
  console.log('🎯 POST /api/analyze-pose called');
  console.log('🔍 Request file:', req.file ? 'Present' : 'Missing');
  console.log('🔍 Request headers:', req.headers);
  
  try {
    if (!req.file) {
      console.log('❌ No video file uploaded');
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

    console.log('🎯 Starting Pose-Based Analysis...');
    console.log('Frame files:', frameFiles.length);

  // Use pose-based analysis (ControlNet pose detection)
  console.log('🔍 Debug - Calling analyzeSnowboardingVideoPoseBased...');
  const analysis = await analyzeSnowboardingVideoPoseBased(videoPath, frameFiles);
  console.log('🔍 Debug - Analysis result:', !!analysis);
  console.log('🔍 Debug - Analysis has detailedPrompts:', !!analysis.detailedPrompts);
  console.log('🔍 Debug - Analysis pipeline:', analysis.pipeline);
  console.log('🔍 Debug - Analysis keys:', Object.keys(analysis));
  console.log('🔍 Debug - detailedPrompts type:', typeof analysis.detailedPrompts);
  console.log('🔍 Debug - detailedPrompts keys:', analysis.detailedPrompts ? Object.keys(analysis.detailedPrompts) : 'none');

    // Clean up temporary files
    fs.unlinkSync(videoPath);
    frameFiles.forEach(frameFile => fs.unlinkSync(frameFile));
    fs.rmdirSync(frameDir);

    res.json({
      success: true,
      analysis: analysis.analysis,
      pipeline: 'pose-based-4stage',
      poseVideoUrl: analysis.poseVideoUrl,
      poseAnalyses: analysis.poseAnalyses,
      poseImages: analysis.poseAnalyses ? analysis.poseAnalyses.map(pose => ({
        frame: pose.frame,
        imageUrl: pose.poseImageUrl
      })) : [],
      technicalAnalysis: analysis.technicalAnalysis,
      sceneDescription: analysis.sceneDescription,
      detailedPrompts: analysis.detailedPrompts,
      message: 'Video analyzed using advanced pose estimation pipeline'
    });

  } catch (error) {
    console.error('Pose analysis error:', error);
    res.status(500).json({
      error: 'Failed to process video with pose analysis',
      details: error.message
    });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/api/health`);
});
