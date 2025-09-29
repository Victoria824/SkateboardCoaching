import React, { useState } from 'react';
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
}

function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [chatHistory, setChatHistory] = useState<Array<{role: 'user' | 'assistant', content: string}>>([]);

  const handleVideoAnalysis = async (file: File) => {
    setIsAnalyzing(true);
    setAnalysisResult(null);
    
    try {
      const formData = new FormData();
      formData.append('video', file);

      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      
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

  const handleChatMessage = (message: string) => {
    setChatHistory(prev => [
      ...prev,
      { role: 'user', content: message }
    ]);
  };

  return (
    <div className="App">
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* Header */}
        <Paper elevation={3} sx={{ p: 4, mb: 4, textAlign: 'center', background: 'linear-gradient(45deg, #2196F3 30%, #21CBF3 90%)' }}>
          <Box display="flex" alignItems="center" justifyContent="center" gap={2} mb={2}>
            <Sports sx={{ fontSize: 40, color: 'white' }} />
            <Typography variant="h3" component="h1" sx={{ color: 'white', fontWeight: 'bold' }}>
              Snowboard Coach AI
            </Typography>
            <Psychology sx={{ fontSize: 40, color: 'white' }} />
          </Box>
          <Typography variant="h6" sx={{ color: 'white', opacity: 0.9 }}>
            Upload your snowboarding video and get personalized coaching advice powered by AI
          </Typography>
        </Paper>

        {/* Main Content */}
        <Box display="flex" gap={3} flexDirection={{ xs: 'column', lg: 'row' }}>
          {/* Video Upload Section */}
          <Box flex={1}>
            <Card elevation={3}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CloudUpload color="primary" />
                  Upload Your Video
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Upload a video of your snowboarding session to get AI-powered coaching analysis.
                </Typography>
                
                <VideoUpload 
                  onVideoSelect={handleVideoAnalysis}
                  isAnalyzing={isAnalyzing}
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
            <Card elevation={3} sx={{ height: '100%' }}>
              <CardContent sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
                <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Psychology color="primary" />
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
                />
              </CardContent>
            </Card>
          </Box>
        </Box>

        {/* Features Section */}
        <Box mt={4}>
          <Typography variant="h5" gutterBottom textAlign="center" sx={{ mb: 3 }}>
            What Our AI Coach Analyzes
          </Typography>
          <Box display="flex" gap={2} flexWrap="wrap" justifyContent="center">
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
                color="primary"
                variant="outlined"
                sx={{ mb: 1 }}
              />
            ))}
          </Box>
        </Box>
      </Container>
    </div>
  );
}

export default App;
