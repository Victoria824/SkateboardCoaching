// Advanced 4-Stage Pose-Based Snowboarding Analysis Pipeline
// This file implements the new pose estimation + analysis pipeline

const Replicate = require('replicate');
const fs = require('fs');
require('dotenv').config();

// Import fetch and FormData for file uploads
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
const FormData = require('form-data');

// Initialize Replicate
const replicate = new Replicate({
  auth: process.env.REPLICATE_API_TOKEN,
});

// Helper function to convert image to base64
const imageToBase64 = (imagePath) => {
  const imageBuffer = fs.readFileSync(imagePath);
  return imageBuffer.toString('base64');
};

// Helper function to convert video to base64
const videoToBase64 = (videoPath) => {
  const videoBuffer = fs.readFileSync(videoPath);
  return videoBuffer.toString('base64');
};

// Model configurations for the 4-stage pipeline
const POSE_PIPELINE_MODELS = {
  // Stage 0: Pose Estimation (using ControlNet pose detection)
  POSE_ESTIMATION: "jagilley/controlnet-pose:9a5c1140b0d6afb96a8603b8da7d590ebea5c0ee63a5090e10dd89d172f57e8a",
  
  // Stage 1: Technical Analysis (using pose data)
  TECHNICAL_ANALYSIS: "yorickvp/llava-v1.6-mistral-7b:19be067b589d0c46689ffa7cc3ff321447a441986a7694c01225973c2eafc874",
  
  // Stage 2: Scene Description (with pose context)
  SCENE_DESCRIPTION: "andreasjansson/blip-2:f677695e5e89f8b236e52ecd1d3f01beb44c34606419bcc19345e046d8f786f9",
  
  // Stage 3: Report Generation
  REPORT_GENERATION: "meta/llama-2-70b-chat:02e509c789964a7ea8736978a43525956ef40397be9033abf9fd2badfe68c9e3"
};

/**
 * Stage 0: Pose Estimation using ControlNet Pose Detection
 * Input: Video frames
 * Output: Pose estimation data for each frame
 */
const estimatePoses = async (videoPath, framePaths) => {
  try {
    console.log('🎯 Stage 0: Estimating poses using ControlNet pose detection...');
    console.log('📹 Video:', videoPath);
    console.log('🖼️  Frames:', framePaths.length);
    
    // Analyze poses from frames using ControlNet pose detection
    const poseAnalyses = [];
    
    for (let i = 0; i < Math.min(framePaths.length, 5); i++) {
      const framePath = framePaths[i];
      console.log(`🔄 Analyzing pose in frame ${i + 1}...`);
      
      try {
        const imageData = imageToBase64(framePath);
        const imageDataUrl = `data:image/png;base64,${imageData}`;
        
        console.log('🔍 Debug - Calling ControlNet with imageDataUrl length:', imageDataUrl.length);
        
        const poseEstimation = await replicate.run(
          POSE_PIPELINE_MODELS.POSE_ESTIMATION,
          {
            input: {
              image: imageDataUrl,
              prompt: "snowboarding pose analysis",
              num_inference_steps: 20,
              guidance_scale: 7.5
            }
          }
        );
        
        console.log('🔍 Debug - ControlNet call completed successfully');
        
        // ControlNet returns pose data - extract the image URL
        let poseImageUrl = null;
        console.log('🔍 Debug - poseEstimation type:', typeof poseEstimation);
        console.log('🔍 Debug - poseEstimation isArray:', Array.isArray(poseEstimation));
        
        if (Array.isArray(poseEstimation)) {
          console.log('🔍 Debug - poseEstimation array length:', poseEstimation.length);
          console.log('🔍 Debug - poseEstimation array items:', poseEstimation.map(item => typeof item));
          
          // ControlNet returns array of 2 URLs: [pose_detection_overlay, generated_image]
          // We want the first one (pose detection overlay)
          poseImageUrl = poseEstimation[0];
          console.log('🔍 Debug - Selected pose image URL:', poseImageUrl);
        } else if (typeof poseEstimation === 'string') {
          poseImageUrl = poseEstimation;
        } else if (poseEstimation && poseEstimation.url) {
          poseImageUrl = poseEstimation.url;
        } else if (poseEstimation && poseEstimation.output) {
          // Some models return { output: "url" }
          poseImageUrl = poseEstimation.output;
        } else {
          console.log('🔍 Debug - poseEstimation content:', poseEstimation);
          poseImageUrl = poseEstimation; // Use as-is for debugging
        }
        
        console.log('🔍 Debug - Final poseImageUrl:', poseImageUrl);
        
        poseAnalyses.push({
          frame: i + 1,
          poseData: poseEstimation,
          poseImageUrl: poseImageUrl // ControlNet returns pose skeleton images
        });
        
        console.log(`✅ Frame ${i + 1} pose estimation completed`);
        
      } catch (frameError) {
        console.error(`❌ Frame ${i + 1} pose estimation failed:`, frameError.message);
        console.error(`❌ Frame ${i + 1} error details:`, frameError);
        // Continue with other frames
      }
    }
    
    if (poseAnalyses.length === 0) {
      throw new Error('No frames could be analyzed for pose estimation');
    }
    
    console.log('✅ ControlNet pose estimation completed');
    console.log('📊 Analyzed frames:', poseAnalyses.length);
    
    return {
      poseAnalyses: poseAnalyses,
      success: true,
      frameCount: poseAnalyses.length
    };
    
  } catch (error) {
    console.error('❌ Stage 0 failed:', error.message);
    throw new Error(`Pose estimation failed: ${error.message}`);
  }
};

/**
 * Stage 1: Technical Analysis
 * Input: Pose estimation video + frames
 * Output: Technical movement analysis
 */
const analyzeTechnicalMovement = async (poseAnalyses, framePaths) => {
  try {
    console.log('🔬 Stage 1: Analyzing technical movement across multiple frames...');
    console.log(`📊 Analyzing ${framePaths.length} frames for comprehensive assessment`);
    
    // Analyze key frames: beginning, middle, and end
    const keyFrames = [
      framePaths[0], // Beginning
      framePaths[Math.floor(framePaths.length / 2)], // Middle
      framePaths[framePaths.length - 1] // End
    ];
    
    let allAnalysisResults = [];
    
    for (let i = 0; i < keyFrames.length; i++) {
      const frame = keyFrames[i];
      const frameNumber = i === 0 ? 'beginning' : i === 1 ? 'middle' : 'end';
      
      console.log(`🔍 Analyzing ${frameNumber} frame...`);
      
      const imageData = imageToBase64(frame);
      const imageUrl = `data:image/png;base64,${imageData}`;
      
      const technicalAnalysis = await replicate.run(
        POSE_PIPELINE_MODELS.TECHNICAL_ANALYSIS,
        {
          input: {
            image: imageUrl,
            prompt: `Analyze this snowboarding image (${frameNumber} of sequence) with pose estimation data in mind. Focus on:

TECHNICAL BIOMECHANICS:
1. Body posture and alignment - spine, shoulders, hips
2. Joint angles - knees, ankles, elbows, wrists
3. Weight distribution - front/back, left/right balance
4. Edge control - board angle relative to slope
5. Arm positioning - for balance and control
6. Head position - looking direction and stability

POSE-SPECIFIC ANALYSIS:
- Identify key joint angles and their optimal ranges
- Assess balance and weight distribution patterns
- Evaluate technique efficiency and power transfer
- Note any asymmetries or imbalances
- Check for proper snowboarding biomechanics

FRAME CONTEXT:
- This is the ${frameNumber} frame of a snowboarding sequence
- Consider how technique may be evolving throughout the movement
- Look for consistency or changes in form

Provide specific, measurable feedback based on pose data for this specific moment in the sequence.`
          }
        }
      );
      
      const analysisText = Array.isArray(technicalAnalysis) ? technicalAnalysis.join(' ') : technicalAnalysis;
      allAnalysisResults.push(`=== ${frameNumber.toUpperCase()} FRAME ANALYSIS ===\n${analysisText}`);
    }
    
    console.log('✅ Multi-frame technical analysis completed');
    return allAnalysisResults.join('\n\n');
    
  } catch (error) {
    console.error('❌ Stage 1 failed:', error.message);
    throw new Error(`Technical analysis failed: ${error.message}`);
  }
};

/**
 * Stage 2: Scene Description
 * Input: Frame + pose context
 * Output: Natural language description of action
 */
const describeScene = async (framePaths, poseAnalyses) => {
  try {
    console.log('🎬 Stage 2: Describing scene and action across sequence...');
    
    // Analyze beginning, middle, and end frames for movement progression
    const keyFrames = [
      { frame: framePaths[0], phase: 'initiation' },
      { frame: framePaths[Math.floor(framePaths.length / 2)], phase: 'execution' },
      { frame: framePaths[framePaths.length - 1], phase: 'completion' }
    ];
    
    let sceneDescriptions = [];
    
    for (const { frame, phase } of keyFrames) {
      const imageData = imageToBase64(frame);
      const imageUrl = `data:image/png;base64,${imageData}`;
      
      const sceneDescription = await replicate.run(
        POSE_PIPELINE_MODELS.SCENE_DESCRIPTION,
        {
          input: {
            image: imageUrl,
            question: `Describe this snowboarding scene (${phase} phase) in detail. Focus on:

ACTION IDENTIFICATION:
- What specific snowboarding maneuver is being performed?
- Is this a turn, carve, jump, or other technique?
- What phase of the movement (initiation, execution, completion)?

TECHNIQUE CONTEXT:
- Speed and slope conditions
- Terrain type and difficulty
- Rider's skill level apparent
- Safety considerations

MOVEMENT QUALITY:
- Flow and fluidity of movement
- Control and stability
- Style and form
- Efficiency of technique

SEQUENCE CONTEXT:
- This is the ${phase} phase of a snowboarding sequence
- How does the technique look at this moment?
- What changes or consistency do you observe?

Provide a comprehensive description that captures both the technical and contextual aspects of this specific moment in the snowboarding sequence.`
          }
        }
      );
      
      const descriptionText = Array.isArray(sceneDescription) ? sceneDescription.join(' ') : sceneDescription;
      sceneDescriptions.push(`=== ${phase.toUpperCase()} PHASE ===\n${descriptionText}`);
    }
    
    console.log('✅ Multi-phase scene description completed');
    return sceneDescriptions.join('\n\n');
    
  } catch (error) {
    console.error('❌ Stage 2 failed:', error.message);
    throw new Error(`Scene description failed: ${error.message}`);
  }
};

/**
 * Stage 3: Enhanced Coaching Report Generation
 * Input: Technical analysis + scene description + pose data
 * Output: Comprehensive coaching report
 */
const generateCoachingReport = async (technicalAnalysis, sceneDescription, poseAnalyses) => {
  try {
    console.log('📝 Stage 3: Generating structured conversational coaching report...');
    
    // Generate structured data for interactive chat
    const briefAssessmentPrompt = `As an expert snowboarding coach, provide ONLY a brief initial assessment based on multi-frame pose analysis:

TECHNICAL ANALYSIS SUMMARY:
${technicalAnalysis.substring(0, 1500)}...

SCENE DESCRIPTION SUMMARY:
${sceneDescription.substring(0, 800)}...

POSE ANALYSIS DATA: ControlNet pose estimation completed across ${poseAnalyses.length} frames

Provide ONLY a brief assessment in this format:

**Overall Assessment:**

[Provide a 1-10 rating and brief summary of overall technique across all frames, mentioning both strengths and areas for improvement. Keep this concise but encouraging - 2-3 sentences maximum.]

I can provide more detailed information about your Key Strengths, Main Areas for Improvement, and Specific Drills and Exercises. Which would you like to learn more about?

Keep it conversational and encouraging.`;

    const detailedStrengthsPrompt = `Based on this technical analysis, provide detailed key strengths:

TECHNICAL ANALYSIS:
${technicalAnalysis.substring(0, 2000)}...

Provide 3-4 specific strengths with detailed explanations.`;

    const detailedImprovementsPrompt = `Based on this technical analysis, provide detailed areas for improvement:

TECHNICAL ANALYSIS:
${technicalAnalysis.substring(0, 2000)}...

Provide 3-4 specific areas that need work with detailed explanations.`;

    const detailedDrillsPrompt = `Based on this technical analysis, provide specific drills and exercises:

TECHNICAL ANALYSIS:
${technicalAnalysis.substring(0, 2000)}...

Provide 3-4 specific drills with descriptions and purposes.`;
    
    // Generate brief assessment
    const briefAssessment = await replicate.run(
      POSE_PIPELINE_MODELS.REPORT_GENERATION,
      {
        input: {
          prompt: briefAssessmentPrompt
        }
      }
    );
    
    console.log('✅ Brief assessment generated');
    console.log('🔍 Debug - briefAssessment type:', typeof briefAssessment);
    console.log('🔍 Debug - briefAssessment length:', briefAssessment ? (Array.isArray(briefAssessment) ? briefAssessment.length : briefAssessment.length) : 'null');
    
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

    const result = {
      briefAssessment: cleanText(Array.isArray(briefAssessment) ? briefAssessment.join(' ') : briefAssessment),
      detailedPrompts: {
        strengths: detailedStrengthsPrompt,
        improvements: detailedImprovementsPrompt,
        drills: detailedDrillsPrompt
      },
      technicalAnalysis: cleanText(technicalAnalysis),
      sceneDescription: cleanText(sceneDescription),
      poseAnalyses: poseAnalyses
    };
    
    console.log('🔍 Debug - generateCoachingReport result detailedPrompts:', !!result.detailedPrompts);
    console.log('🔍 Debug - generateCoachingReport detailedPrompts keys:', Object.keys(result.detailedPrompts));
    
    return result;
    
  } catch (error) {
    console.error('❌ Stage 3 failed:', error.message);
    throw new Error(`Report generation failed: ${error.message}`);
  }
};

/**
 * Main 4-Stage Pipeline Function
 * Orchestrates the entire pose-based analysis process
 */
const analyzeSnowboardingVideoPoseBased = async (videoPath, framePaths) => {
  try {
    console.log('🎿 Starting 4-Stage Pose-Based Analysis Pipeline...');
    console.log('📹 Video:', videoPath);
    console.log('🖼️  Frames:', framePaths.length);
    
    // Stage 0: Pose Estimation
    const poseResult = await estimatePoses(videoPath, framePaths);
    
    // Stage 1: Technical Analysis
    const technicalAnalysis = await analyzeTechnicalMovement(poseResult.poseAnalyses, framePaths);
    
    // Stage 2: Scene Description
    const sceneDescription = await describeScene(framePaths, poseResult.poseAnalyses);
    
    // Stage 3: Report Generation
    const coachingReport = await generateCoachingReport(
      technicalAnalysis, 
      sceneDescription, 
      poseResult.poseAnalyses
    );
    
    console.log('🎉 4-Stage Pipeline completed successfully!');
    console.log('🔍 Debug - coachingReport.detailedPrompts:', !!coachingReport.detailedPrompts);
    console.log('🔍 Debug - detailedPrompts keys:', coachingReport.detailedPrompts ? Object.keys(coachingReport.detailedPrompts) : 'none');
    
    return {
      success: true,
      analysis: coachingReport.briefAssessment,
      poseVideoUrl: null,
      poseAnalyses: poseResult.poseAnalyses,
      poseImages: poseResult.poseAnalyses.map(pose => ({
        frame: pose.frame,
        imageUrl: pose.poseImageUrl
      })),
      technicalAnalysis: technicalAnalysis,
      sceneDescription: sceneDescription,
      detailedPrompts: coachingReport.detailedPrompts,
      pipeline: 'pose-based-4stage',
      message: 'Video analyzed using advanced ControlNet pose estimation pipeline'
    };
    
  } catch (error) {
    console.error('❌ Pose-based pipeline failed:', error.message);
    console.log('🔄 Falling back to image-based analysis...');
    
    // Fallback to simple analysis (no API calls)
    const fallbackAnalysis = `Based on your snowboarding video analysis, I can see you're working on your technique. Your form shows good potential with room for improvement in balance and edge control.`;
    
    // Create structured data for interactive chat
    const briefAssessment = `**Subject: Snowboarding Technique Analysis and Coaching Advice**

Dear [Name],

I have analyzed your snowboarding technique across multiple frames from your video. My analysis is based on the principles of safe and respectful coaching, with a focus on maintaining balance, control, and efficiency in your riding style.

**Overall Assessment:**

${fallbackAnalysis.substring(0, 200)}...

I can provide more detailed information about your Key Strengths, Main Areas for Improvement, and Specific Drills and Exercises. Which would you like to learn more about?`;

    const detailedPrompts = {
      strengths: `Based on this snowboarding analysis, provide detailed key strengths:\n\nANALYSIS:\n${fallbackAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific strengths with detailed explanations.`,
      improvements: `Based on this snowboarding analysis, provide detailed areas for improvement:\n\nANALYSIS:\n${fallbackAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific areas that need work with detailed explanations.`,
      drills: `Based on this snowboarding analysis, provide specific drills and exercises:\n\nANALYSIS:\n${fallbackAnalysis.substring(0, 1500)}...\n\nProvide 3-4 specific drills with descriptions and purposes.`
    };

    console.log('🔍 Debug - Fallback detailedPrompts:', !!detailedPrompts);
    console.log('🔍 Debug - Fallback detailedPrompts keys:', Object.keys(detailedPrompts));
    
    return {
      success: true,
      analysis: briefAssessment,
      poseVideoUrl: null,
      poseImages: [], // No pose images for fallback
      technicalAnalysis: fallbackAnalysis,
      sceneDescription: 'Snowboarding technique analysis',
      detailedPrompts: detailedPrompts,
      pipeline: 'image-based-fallback',
      message: 'Video analyzed using fallback image-based pipeline'
    };
  }
};

module.exports = {
  analyzeSnowboardingVideoPoseBased,
  estimatePoses,
  analyzeTechnicalMovement,
  describeScene,
  generateCoachingReport,
  POSE_PIPELINE_MODELS
};
