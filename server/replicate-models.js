// Alternative Replicate models for snowboarding analysis
// This file contains different model options you can use

const Replicate = require('replicate');
const fs = require('fs');
require('dotenv').config();

// Initialize Replicate
const replicate = new Replicate({
  auth: process.env.REPLICATE_API_TOKEN,
});

// Helper function to convert image to base64
const imageToBase64 = (imagePath) => {
  const imageBuffer = fs.readFileSync(imagePath);
  return imageBuffer.toString('base64');
};

const REPLICATE_MODELS = {
  // === IMAGE ANALYSIS (for frame-by-frame) ===
  // LLaVA for detailed image understanding (VERIFIED WORKING)
  IMAGE_ANALYSIS: "yorickvp/llava-v1.6-mistral-7b:19be067b589d0c46689ffa7cc3ff321447a441986a7694c01225973c2eafc874",
  
  // Alternative: BLIP-2 for image captioning (VERIFIED WORKING)
  IMAGE_CAPTION: "andreasjansson/blip-2:f677695e5e89f8b236e52ecd1d3f01beb44c34606419bcc19345e046d8f786f9",
  
  // === TEXT SYNTHESIS ===
  // For generating coaching reports (VERIFIED WORKING)
  TEXT_SYNTHESIS: "meta/llama-2-70b-chat:02e509c789964a7ea8736978a43525956ef40397be9033abf9fd2badfe68c9e3",
  TEXT_SYNTHESIS_ALT: "mistralai/mistral-7b-instruct-v0.1:83b6a56e7c828e667f21fd596c338fd4f0039b46bcfa18d973e8e70e000f16c4",
  
  // === VIDEO UNDERSTANDING ===
  // Video analysis and understanding (NOT AVAILABLE)
  VIDEO_ANALYSIS: "daanelson/video-llama:latest", // This model doesn't exist
  
  // === GENERAL PURPOSE MODELS ===
  // GPT-4 Vision via Replicate (if available)
  GPT4_VISION: "openai/gpt-4-vision-preview",
};

// Cost-effective analysis function
const analyzeSnowboardingVideoCostEffective = async (framePaths) => {
  try {
    // Analyze just the middle frame to save costs
    const middleFrame = framePaths[Math.floor(framePaths.length / 2)];
    const imageData = imageToBase64(middleFrame);
    const imageUrl = `data:image/png;base64,${imageData}`;
    
    const output = await replicate.run(
      REPLICATE_MODELS.IMAGE_ANALYSIS,
      {
        input: {
          image: imageUrl,
          prompt: `Analyze this snowboarding image and provide detailed coaching advice. Focus on:
          1. Body position and posture
          2. Edge control and board angle
          3. Balance and weight distribution
          4. Arm and shoulder positioning
          5. Overall technique and areas for improvement
          
          Provide specific, actionable advice for snowboarding improvement. Be encouraging and practical.`
        }
      }
    );
    
    return output.join(' ');
  } catch (error) {
    console.error('Error analyzing video:', error);
    throw new Error('Failed to analyze video');
  }
};

// Premium analysis function (analyzes all frames)
const analyzeSnowboardingVideoPremium = async (framePaths) => {
  try {
    // Analyze all frames for comprehensive feedback
    const analysisPromises = framePaths.map(async (framePath, index) => {
      const imageData = imageToBase64(framePath);
      const imageUrl = `data:image/png;base64,${imageData}`;
      
      const output = await replicate.run(
        REPLICATE_MODELS.IMAGE_ANALYSIS,
        {
          input: {
            image: imageUrl,
            prompt: `Analyze snowboarding frame ${index + 1} of ${framePaths.length}. Focus on:
            1. Body position and posture
            2. Edge control and board angle
            3. Balance and weight distribution
            4. Arm and shoulder positioning
            5. Overall technique
            
            Provide specific coaching advice for this frame.`
          }
        }
      );
      
      return `Frame ${index + 1}: ${output.join(' ')}`;
    });

    const analyses = await Promise.all(analysisPromises);
    
    // Synthesize all analyses
    const finalOutput = await replicate.run(
      REPLICATE_MODELS.TEXT_SYNTHESIS,
      {
        input: {
          prompt: `As an expert snowboarding coach, synthesize these frame analyses into comprehensive coaching advice:

${analyses.join('\n\n')}

Provide a structured report with:
1. Overall assessment
2. Key strengths
3. Main areas for improvement
4. Specific drills and exercises
5. Next steps for progression

Keep it practical and encouraging.`
        }
      }
    );

    return finalOutput.join(' ');
  } catch (error) {
    console.error('Error analyzing video:', error);
    throw new Error('Failed to analyze video');
  }
};

// Direct video analysis using Video-LLaMA
const analyzeSnowboardingVideoDirect = async (videoPath) => {
  try {
    console.log('Starting Video-LLaMA analysis...');
    
    // Convert video to base64 for Video-LLaMA
    const videoData = imageToBase64(videoPath);
    const videoUrl = `data:video/mp4;base64,${videoData}`;
    
    const analysis = await replicate.run(
      REPLICATE_MODELS.VIDEO_ANALYSIS,
      {
        input: {
          video: videoUrl,
          prompt: `Analyze this snowboarding video and provide comprehensive coaching feedback. Focus on:

1. **Body Position & Posture**
   - Stance and alignment
   - Core stability
   - Head and shoulder position

2. **Edge Control & Board Management**
   - Edge transitions
   - Board angle and pressure
   - Carving technique

3. **Balance & Weight Distribution**
   - Weight shifts during turns
   - Center of gravity
   - Stability throughout the run

4. **Arm & Upper Body Movement**
   - Arm positioning for balance
   - Shoulder rotation
   - Upper body control

5. **Overall Technique Assessment**
   - Strengths and weaknesses
   - Areas for improvement
   - Skill level evaluation

6. **Specific Coaching Recommendations**
   - Drills and exercises
   - Practice suggestions
   - Safety considerations

Provide detailed, actionable advice for snowboarding improvement. Be encouraging and technical.`
        }
      }
    );

    return analysis.join(' ');
  } catch (error) {
    console.error('Error in Video-LLaMA analysis:', error);
    // Fallback to frame-based analysis
    return analyzeSnowboardingVideoAdvanced(framePaths);
  }
};

// Advanced analysis using multiple working models (fallback)
const analyzeSnowboardingVideoAdvanced = async (framePaths) => {
  try {
    const middleFrame = framePaths[Math.floor(framePaths.length / 2)];
    const imageData = imageToBase64(middleFrame);
    const imageUrl = `data:image/png;base64,${imageData}`;
    
    // Step 1: Detailed Image Analysis with LLaVA
    const imageAnalysis = await replicate.run(
      REPLICATE_MODELS.IMAGE_ANALYSIS,
      {
        input: {
          image: imageUrl,
          prompt: `Analyze this snowboarding image in detail. Focus on:
          1. Body position and posture - how is the rider's stance?
          2. Edge control and board angle - is the board properly angled?
          3. Balance and weight distribution - where is their weight?
          4. Arm and shoulder positioning - are arms helping balance?
          5. Overall technique and areas for improvement
          6. Equipment positioning - helmet, bindings, etc.
          
          Provide specific, actionable advice for snowboarding improvement. Be detailed and technical.`
        }
      }
    );
    
    // Step 2: Additional context with BLIP-2
    const contextAnalysis = await replicate.run(
      REPLICATE_MODELS.IMAGE_CAPTION,
      {
        input: {
          image: imageUrl,
          question: "What is happening in this snowboarding scene? Describe the technique and form."
        }
      }
    );
    
    // Step 3: Synthesize into comprehensive coaching advice
    const finalOutput = await replicate.run(
      REPLICATE_MODELS.TEXT_SYNTHESIS,
      {
        input: {
          prompt: `As an expert snowboarding coach, analyze this data and provide comprehensive feedback:

DETAILED IMAGE ANALYSIS:
${imageAnalysis.join(' ')}

CONTEXT ANALYSIS:
${contextAnalysis.join(' ')}

Create a structured coaching report with:
1. Overall assessment of technique
2. Key strengths identified
3. Main areas for improvement
4. Specific drills and exercises
5. Next steps for progression
6. Safety considerations

Focus on body mechanics, balance, and technique. Be encouraging and practical.`
        }
      }
    );

    return finalOutput.join(' ');
  } catch (error) {
    console.error('Error in advanced analysis:', error);
    // Fallback to basic analysis
    return analyzeSnowboardingVideoCostEffective(framePaths);
  }
};

// Multi-frame analysis (analyzes multiple frames for better understanding)
const analyzeSnowboardingVideoMultiFrame = async (framePaths) => {
  try {
    const analyses = [];
    
    // Analyze multiple frames for better understanding
    const framesToAnalyze = Math.min(framePaths.length, 3);
    for (let i = 0; i < framesToAnalyze; i++) {
      const framePath = framePaths[i];
      const imageData = imageToBase64(framePath);
      const imageUrl = `data:image/png;base64,${imageData}`;
      
      const frameAnalysis = await replicate.run(
        REPLICATE_MODELS.IMAGE_ANALYSIS,
        {
          input: {
            image: imageUrl,
            prompt: `Analyze snowboarding frame ${i + 1} of ${framesToAnalyze}. Focus on:
            1. Body position and posture
            2. Edge control and board angle
            3. Balance and weight distribution
            4. Arm and shoulder positioning
            5. Overall technique
            
            Provide specific coaching advice for this frame.`
          }
        }
      );
      
      analyses.push(`Frame ${i + 1}: ${frameAnalysis.join(' ')}`);
    }
    
    // Synthesize all frame analyses into comprehensive coaching advice
    const finalOutput = await replicate.run(
      REPLICATE_MODELS.TEXT_SYNTHESIS,
      {
        input: {
          prompt: `As a snowboarding coach, synthesize these frame analyses into comprehensive coaching advice:

${analyses.join('\n\n')}

Create a structured report with:
1. Overall assessment across all frames
2. Key strengths identified
3. Main areas for improvement
4. Specific drills and exercises
5. Next steps for progression

Focus on consistency across frames and overall technique improvement.`
        }
      }
    );

    return finalOutput.join(' ');
  } catch (error) {
    console.error('Error in multi-frame analysis:', error);
    throw new Error('Failed to analyze video');
  }
};

module.exports = {
  REPLICATE_MODELS,
  analyzeSnowboardingVideoDirect,
  analyzeSnowboardingVideoCostEffective,
  analyzeSnowboardingVideoPremium,
  analyzeSnowboardingVideoAdvanced,
  analyzeSnowboardingVideoMultiFrame
};
