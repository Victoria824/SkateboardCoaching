import React, { useState, useEffect, useRef } from 'react';
import {
  Container,
  Paper,
  Typography,
  Box,
  Button,
  LinearProgress,
  Alert,
  Card,
  CardContent,
  Chip,
  Divider
} from '@mui/material';
import { CloudUpload, Sports, Psychology } from '@mui/icons-material';
import VideoUpload from './components/VideoUpload';
import ChatInterface from './components/ChatInterface';
import './App.css';

interface AnalysisResult {
  analysis: string;
  success: boolean;
  message: string;
  detailedPrompts?: {
    strengths: string;
    improvements: string;
    drills: string;
  };
  technicalAnalysis?: string;
  sceneDescription?: string;
  poseVideoUrl?: string;
  poseImages?: Array<{
    frame: number;
    imageUrl: string;
  }>;
}

function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [chatHistory, setChatHistory] = useState<Array<{role: 'user' | 'assistant', content: string}>>([]);
  const [uploadedVideo, setUploadedVideo] = useState<File | null>(null);
  const analysisResultRef = useRef<AnalysisResult | null>(null);

  // Debug: Monitor analysisResult state changes
  useEffect(() => {
    console.log('🔍 Debug - analysisResult state changed:', analysisResult);
    console.log('🔍 Debug - has detailedPrompts in state:', !!analysisResult?.detailedPrompts);
    analysisResultRef.current = analysisResult;
  }, [analysisResult]);

  const handleVideoAnalysis = async (file: File) => {
    // Prevent page from scrolling to bottom
    window.scrollTo(0, 0);
    
    setIsAnalyzing(true);
    setAnalysisResult(null);
    setChatHistory([]); // Clear previous chat history
    setUploadedVideo(file);
    
    try {
      const formData = new FormData();
      formData.append('video', file);

      const response = await fetch('/api/analyze-pose', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      
        console.log('🔍 Debug - Analysis result:', result);
        console.log('🔍 Debug - Has detailedPrompts:', !!result.detailedPrompts);
        console.log('🔍 Debug - detailedPrompts keys:', result.detailedPrompts ? Object.keys(result.detailedPrompts) : 'none');
      
      if (result.success) {
        setAnalysisResult(result);
        // Add the analysis to chat history
        setChatHistory(prev => [
          ...prev,
          { role: 'assistant', content: result.analysis }
        ]);
      } else {
        throw new Error(result.error || 'Analysis failed');
      }
    } catch (error) {
      console.error('Error analyzing video:', error);
      setAnalysisResult({
        success: false,
        analysis: '',
        message: error instanceof Error ? error.message : 'Failed to analyze video'
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleChatMessage = async (message: string) => {
    // Prevent page from scrolling to bottom
    const currentScrollY = window.scrollY;
    
    // Add user message to chat history
    setChatHistory(prev => [
      ...prev,
      { role: 'user', content: message }
    ]);
    
    // Maintain scroll position
    setTimeout(() => {
      window.scrollTo(0, currentScrollY);
    }, 0);

    // If we have analysis data, send follow-up question to backend
    const currentAnalysisResult = analysisResult || analysisResultRef.current;
    console.log('🔍 Debug - analysisResult:', analysisResult);
    console.log('🔍 Debug - analysisResultRef:', analysisResultRef.current);
    console.log('🔍 Debug - currentAnalysisResult:', currentAnalysisResult);
    console.log('🔍 Debug - has detailedPrompts:', !!currentAnalysisResult?.detailedPrompts);
    console.log('🔍 Debug - detailedPrompts object:', currentAnalysisResult?.detailedPrompts);
    
    if (currentAnalysisResult && currentAnalysisResult.detailedPrompts && Object.keys(currentAnalysisResult.detailedPrompts).length > 0) {
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            question: message,
            analysisData: {
              detailedPrompts: currentAnalysisResult.detailedPrompts,
              technicalAnalysis: currentAnalysisResult.technicalAnalysis,
              sceneDescription: currentAnalysisResult.sceneDescription
            }
          }),
        });

        const result = await response.json();
        
        if (result.success) {
          setChatHistory(prev => [
            ...prev,
            { role: 'assistant', content: result.response }
          ]);
        } else {
          setChatHistory(prev => [
            ...prev,
            { role: 'assistant', content: 'Sorry, I had trouble processing your question. Please try again.' }
          ]);
        }
        
        // Maintain scroll position after assistant response
        setTimeout(() => {
          window.scrollTo(0, currentScrollY);
        }, 0);
      } catch (error) {
        console.error('Error processing chat message:', error);
        setChatHistory(prev => [
          ...prev,
          { role: 'assistant', content: 'Sorry, I had trouble processing your question. Please try again.' }
        ]);
        
        // Maintain scroll position after error
        setTimeout(() => {
          window.scrollTo(0, currentScrollY);
        }, 0);
      }
    } else {
      // No analysis data available, provide general response
      console.log('🔍 Debug - No analysis data available, providing general response');
      setChatHistory(prev => [
        ...prev,
        { role: 'assistant', content: 'Please upload a video first to get personalized coaching advice!' }
      ]);
      
      // Maintain scroll position after general response
      setTimeout(() => {
        window.scrollTo(0, currentScrollY);
      }, 0);
    }
  };

  return (
    <div className="App" style={{
      background: `
        linear-gradient(135deg, #f8f9fa 0%, #e9ecef 25%, #dee2e6 50%, #ced4da 75%, #adb5bd 100%),
        radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.05) 0%, transparent 50%)
      `,
      minHeight: '100vh',
      position: 'relative'
    }}>
      {/* Sophisticated background elements */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: `
          linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%),
          linear-gradient(-45deg, transparent 30%, rgba(0, 0, 0, 0.02) 50%, transparent 70%),
          radial-gradient(ellipse at 10% 10%, rgba(255, 255, 255, 0.3) 0%, transparent 60%),
          radial-gradient(ellipse at 90% 90%, rgba(0, 0, 0, 0.1) 0%, transparent 60%)
        `,
        pointerEvents: 'none'
      }} />
      
      {/* Grid pattern overlay */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: `
          linear-gradient(rgba(0, 0, 0, 0.02) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0, 0, 0, 0.02) 1px, transparent 1px)
        `,
        backgroundSize: '50px 50px',
        pointerEvents: 'none',
        opacity: 0.5
      }} />
      
      <Container maxWidth="lg" sx={{ py: 4, position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <Paper 
          elevation={12} 
          sx={{ 
            p: 5, 
            mb: 5, 
            textAlign: 'center', 
            background: `
              linear-gradient(135deg, #1a252f 0%, #2c3e50 25%, #34495e 50%, #2c3e50 75%, #1a252f 100%),
              radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
              radial-gradient(circle at 70% 70%, rgba(0, 0, 0, 0.2) 0%, transparent 50%)
            `,
            borderRadius: 4,
            position: 'relative',
            overflow: 'hidden',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
          }}
        >
          {/* Sophisticated header background pattern */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `
              linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.08) 50%, transparent 70%),
              linear-gradient(-45deg, transparent 30%, rgba(255, 255, 255, 0.05) 50%, transparent 70%),
              radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.1) 0%, transparent 40%),
              radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.1) 0%, transparent 40%)
            `,
            backgroundSize: '30px 30px, 30px 30px, 100px 100px, 100px 100px',
            opacity: 0.6
          }} />
          
          {/* Subtle border highlight */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: 'linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.3) 50%, transparent 100%)'
          }} />
          
          <Box display="flex" alignItems="center" justifyContent="center" gap={2} mb={2} sx={{ position: 'relative', zIndex: 1 }}>
            <Sports sx={{ fontSize: 40, color: 'white', filter: 'drop-shadow(2px 2px 4px rgba(0, 0, 0, 0.3))' }} />
            <Typography variant="h3" component="h1" sx={{ 
              color: 'white', 
              fontWeight: 'bold',
              textShadow: '2px 2px 4px rgba(0, 0, 0, 0.3)'
            }}>
              Snowboard Coach AI
            </Typography>
            <Psychology sx={{ fontSize: 40, color: 'white', filter: 'drop-shadow(2px 2px 4px rgba(0, 0, 0, 0.3))' }} />
          </Box>
          <Typography variant="h6" sx={{ 
            color: 'white', 
            opacity: 0.9,
            position: 'relative',
            zIndex: 1,
            textShadow: '1px 1px 2px rgba(0, 0, 0, 0.3)'
          }}>
            Upload your snowboarding video and get personalized coaching advice powered by AI
          </Typography>
        </Paper>

        {/* Main Content */}
        <Box display="flex" gap={3} flexDirection={{ xs: 'column', lg: 'row' }}>
          {/* Video Upload Section */}
          <Box flex={1}>
            <Card 
              elevation={8} 
              sx={{ 
                background: `
                  linear-gradient(145deg, #ffffff 0%, #f8f9fa 50%, #ffffff 100%),
                  radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
                  radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.02) 0%, transparent 50%)
                `,
                border: '1px solid rgba(0, 0, 0, 0.06)',
                borderRadius: 4,
                position: 'relative',
                overflow: 'hidden',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                '&:hover': {
                  transform: 'translateY(-2px)',
                  boxShadow: '0 12px 40px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.8)'
                }
              }}
            >
              {/* Sophisticated card background pattern */}
              <div style={{
                position: 'absolute',
                top: 0,
                right: 0,
                width: '120px',
                height: '120px',
                background: `
                  linear-gradient(45deg, rgba(0, 0, 0, 0.02) 0%, transparent 50%),
                  radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.5) 0%, transparent 70%)
                `,
                borderRadius: '0 0 0 100%'
              }} />
              
              {/* Subtle inner border */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                borderRadius: 'inherit',
                background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 50%, rgba(0, 0, 0, 0.02) 100%)',
                pointerEvents: 'none'
              }} />
              
              <CardContent sx={{ p: 3, position: 'relative', zIndex: 1 }}>
                <Typography variant="h5" gutterBottom sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 1,
                  color: '#2c3e50',
                  fontWeight: 'bold'
                }}>
                  <CloudUpload sx={{ color: '#e74c3c' }} />
                  Upload Your Video
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Upload a video of your snowboarding session to get AI-powered coaching analysis.
                </Typography>
                
                <VideoUpload 
                  onVideoSelect={handleVideoAnalysis}
                  isAnalyzing={isAnalyzing}
                  uploadedVideo={uploadedVideo}
                  analysisComplete={!!analysisResult}
                />


                {isAnalyzing && (
                  <Box mt={3}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Analyzing your video...
                    </Typography>
                    <LinearProgress />
                  </Box>
                )}

                {analysisResult && (
                  <Box mt={3}>
                    {analysisResult.success ? (
                      <Alert severity="success" sx={{ mb: 2 }}>
                        {analysisResult.message}
                      </Alert>
                    ) : (
                      <Alert severity="error" sx={{ mb: 2 }}>
                        {analysisResult.message}
                      </Alert>
                    )}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Box>

          {/* Chat Interface */}
          <Box flex={1}>
            <Card 
              elevation={8} 
              sx={{ 
                height: '100%',
                background: `
                  linear-gradient(145deg, #ffffff 0%, #f8f9fa 50%, #ffffff 100%),
                  radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
                  radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.02) 0%, transparent 50%)
                `,
                border: '1px solid rgba(0, 0, 0, 0.06)',
                borderRadius: 4,
                position: 'relative',
                overflow: 'hidden',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                '&:hover': {
                  transform: 'translateY(-2px)',
                  boxShadow: '0 12px 40px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.8)'
                }
              }}
            >
              {/* Sophisticated card background pattern */}
              <div style={{
                position: 'absolute',
                top: 0,
                right: 0,
                width: '120px',
                height: '120px',
                background: `
                  linear-gradient(45deg, rgba(0, 0, 0, 0.02) 0%, transparent 50%),
                  radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.5) 0%, transparent 70%)
                `,
                borderRadius: '0 0 0 100%'
              }} />
              
              {/* Subtle inner border */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                borderRadius: 'inherit',
                background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 50%, rgba(0, 0, 0, 0.02) 100%)',
                pointerEvents: 'none'
              }} />
              
              <CardContent sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
                <Typography variant="h5" gutterBottom sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 1,
                  color: '#2c3e50',
                  fontWeight: 'bold'
                }}>
                  <Psychology sx={{ color: '#e74c3c' }} />
                  AI Coach Chat
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Chat with your AI snowboarding coach for personalized tips and advice.
                </Typography>

                <Divider sx={{ my: 2 }} />

                <ChatInterface 
                  chatHistory={chatHistory}
                  onSendMessage={handleChatMessage}
                  isAnalyzing={isAnalyzing}
                  hasAnalysis={!!analysisResult?.detailedPrompts}
                />
              </CardContent>
            </Card>
          </Box>
        </Box>

        {/* AI Pose Analysis Section - Positioned below both upload and chat */}
        {analysisResult && analysisResult.poseImages && analysisResult.poseImages.length > 0 && (
          <Box sx={{ mt: 4, mb: 4 }}>
            <Card sx={{ 
              p: 3,
              background: `
                linear-gradient(145deg, #ffffff 0%, #f8f9fa 50%, #ffffff 100%),
                radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.02) 0%, transparent 50%)
              `,
              border: '1px solid rgba(0, 0, 0, 0.06)',
              borderRadius: 3,
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.08)'
            }}>
              <Typography variant="h5" sx={{ 
                mb: 2, 
                color: '#333', 
                textAlign: 'center',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 1
              }}>
                🎯 AI Pose Analysis
              </Typography>
              <Typography variant="body1" sx={{ 
                mb: 3, 
                color: '#666', 
                textAlign: 'center',
                fontStyle: 'italic'
              }}>
                ControlNet detected these key poses from your video:
              </Typography>
              <Box sx={{ 
                display: 'flex', 
                flexDirection: 'row',
                justifyContent: 'center', 
                gap: 2,
                maxWidth: '100%',
                overflowX: 'auto',
                pb: 2
              }}>
                {analysisResult.poseImages.map((poseImage, index) => (
                  <Box key={index} sx={{ 
                    textAlign: 'center',
                    p: 1.5,
                    borderRadius: '12px',
                    backgroundColor: '#ffffff',
                    border: '2px solid #e9ecef',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                    transition: 'transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
                    minWidth: '120px',
                    flexShrink: 0,
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.15)'
                    }
                  }}>
                    <Typography variant="subtitle2" sx={{ 
                      display: 'block', 
                      mb: 2, 
                      fontWeight: 'bold',
                      color: '#495057',
                      fontSize: '1rem'
                    }}>
                      Frame {poseImage.frame}
                    </Typography>
                    <img 
                      src={poseImage.imageUrl} 
                      alt={`Pose analysis frame ${poseImage.frame}`}
                      style={{ 
                        width: '100px', 
                        height: '120px',
                        objectFit: 'cover',
                        borderRadius: '8px',
                        boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
                        border: '1px solid #dee2e6'
                      }}
                    />
                  </Box>
                ))}
              </Box>
            </Card>
          </Box>
        )}

        {/* Features Section */}
        <Box 
          mt={5} 
          sx={{ 
            background: `
              linear-gradient(145deg, #ffffff 0%, #f8f9fa 50%, #ffffff 100%),
              radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
              radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.02) 0%, transparent 50%)
            `,
            p: 5, 
            borderRadius: 4,
            border: '1px solid rgba(0, 0, 0, 0.06)',
            position: 'relative',
            overflow: 'hidden',
            boxShadow: '0 12px 40px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)'
          }}
        >
          {/* Sophisticated background pattern */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `
              linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%),
              linear-gradient(-45deg, transparent 30%, rgba(0, 0, 0, 0.02) 50%, transparent 70%),
              radial-gradient(ellipse at 10% 10%, rgba(255, 255, 255, 0.3) 0%, transparent 60%),
              radial-gradient(ellipse at 90% 90%, rgba(0, 0, 0, 0.05) 0%, transparent 60%)
            `,
            backgroundSize: '40px 40px, 40px 40px, 150px 150px, 150px 150px',
            pointerEvents: 'none',
            opacity: 0.6
          }} />
          
          {/* Subtle inner border */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            borderRadius: 'inherit',
            background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 50%, rgba(0, 0, 0, 0.02) 100%)',
            pointerEvents: 'none'
          }} />
          
          <Typography variant="h5" gutterBottom textAlign="center" sx={{ 
            mb: 3, 
            color: '#2c3e50',
            fontWeight: 'bold',
            position: 'relative',
            zIndex: 1
          }}>
            What Our AI Coach Analyzes
          </Typography>
          <Box display="flex" gap={2} flexWrap="wrap" justifyContent="center" sx={{ mb: 4 }}>
            {[
              'Body Position & Posture',
              'Edge Control & Board Angle',
              'Balance & Weight Distribution',
              'Arm & Shoulder Positioning',
              'Overall Technique',
              'Areas for Improvement'
            ].map((feature) => (
              <Chip 
                key={feature}
                label={feature}
                sx={{ 
                  mb: 1,
                  backgroundColor: '#e74c3c',
                  color: 'white',
                  fontWeight: 'bold',
                  '&:hover': {
                    backgroundColor: '#c0392b'
                  }
                }}
              />
            ))}
          </Box>

          {/* Human Coach Contacts */}
          <Box sx={{ position: 'relative', zIndex: 1 }}>
            <Typography variant="h5" gutterBottom textAlign="center" sx={{ 
              mb: 3, 
              color: '#2c3e50',
              fontWeight: 'bold'
            }}>
              Connect with Human Coaches
            </Typography>
            <Box display="flex" gap={3} flexWrap="wrap" justifyContent="center">
              {[
                { name: 'Superman', email: 'superman@superhero.com', specialty: 'Advanced Techniques' },
                { name: 'Snow Queen', email: 'snowqueen@winter.com', specialty: 'Beginner Friendly' },
                { name: 'Mountain Master', email: 'master@peaks.com', specialty: 'Freestyle' },
                { name: 'Alpine Ace', email: 'ace@alpine.com', specialty: 'Racing' }
              ].map((coach) => (
                <Card 
                  key={coach.name}
                  sx={{ 
                    minWidth: 220, 
                    background: `
                      linear-gradient(145deg, #ffffff 0%, #f8f9fa 50%, #ffffff 100%),
                      radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.8) 0%, transparent 50%),
                      radial-gradient(circle at 80% 80%, rgba(0, 0, 0, 0.02) 0%, transparent 50%)
                    `,
                    border: '1px solid rgba(0, 0, 0, 0.06)',
                    borderRadius: 3,
                    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
                    position: 'relative',
                    overflow: 'hidden',
                    transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                    '&:hover': {
                      borderColor: '#e74c3c',
                      transform: 'translateY(-6px) scale(1.02)',
                      boxShadow: '0 12px 35px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.8)'
                    }
                  }}
                >
                  {/* Card background pattern */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    right: 0,
                    width: '80px',
                    height: '80px',
                    background: `
                      linear-gradient(45deg, rgba(231, 76, 60, 0.1) 0%, transparent 50%),
                      radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.5) 0%, transparent 70%)
                    `,
                    borderRadius: '0 0 0 100%'
                  }} />
                  
                  {/* Subtle inner border */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    borderRadius: 'inherit',
                    background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 50%, rgba(0, 0, 0, 0.02) 100%)',
                    pointerEvents: 'none'
                  }} />
                  <CardContent sx={{ textAlign: 'center', p: 3, position: 'relative', zIndex: 1 }}>
                    <Typography variant="h6" sx={{ color: '#2c3e50', fontWeight: 'bold' }}>
                      {coach.name}
                    </Typography>
                    <Typography variant="body2" sx={{ color: '#7f8c8d', mb: 1 }}>
                      {coach.specialty}
                    </Typography>
                    <Typography 
                      variant="body2" 
                      sx={{ 
                        color: '#e74c3c', 
                        fontWeight: 'bold',
                        cursor: 'pointer',
                        '&:hover': {
                          textDecoration: 'underline'
                        }
                      }}
                      onClick={() => window.open(`mailto:${coach.email}`)}
                    >
                      {coach.email}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
            </Box>
          </Box>
        </Box>
      </Container>
    </div>
  );
}

export default App;
