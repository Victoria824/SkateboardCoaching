import React, { useCallback, useState } from 'react';
import {
  Box,
  Button,
  Typography,
  Alert,
  LinearProgress
} from '@mui/material';
import { CloudUpload, Videocam } from '@mui/icons-material';

interface VideoUploadProps {
  onVideoSelect: (file: File) => void;
  isAnalyzing: boolean;
  uploadedVideo?: File | null;
  analysisComplete?: boolean;
}

const VideoUpload: React.FC<VideoUploadProps> = ({ onVideoSelect, isAnalyzing, uploadedVideo, analysisComplete }) => {
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleFile = (file: File) => {
    setError(null);
    
    // Validate file type
    if (!file.type.startsWith('video/')) {
      setError('Please select a video file');
      return;
    }

    // Validate file size (20MB limit for Vercel compatibility)
    if (file.size > 20 * 1024 * 1024) {
      setError('File size must be less than 20MB');
      return;
    }

    onVideoSelect(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <Box>
      <Box
        className={`upload-area ${dragActive ? 'dragover' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => document.getElementById('video-upload-input')?.click()}
        sx={{
          border: '2px dashed',
          borderColor: dragActive ? 'primary.main' : 'grey.300',
          borderRadius: 2,
          p: 4,
          textAlign: 'center',
          backgroundColor: dragActive ? 'action.hover' : 'background.paper',
          cursor: 'pointer',
          transition: 'all 0.3s ease',
          '&:hover': {
            borderColor: 'primary.main',
            backgroundColor: 'action.hover',
          }
        }}
      >
        <input
          id="video-upload-input"
          type="file"
          accept="video/*"
          onChange={handleFileInput}
          style={{ display: 'none' }}
          disabled={isAnalyzing}
        />
        
        <Videocam sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
        
        <Typography variant="h6" gutterBottom>
          {dragActive ? 'Drop your video here' : 'Click to upload or drag and drop'}
        </Typography>
        
        <Typography variant="body2" color="text.secondary">
          Supported formats: MP4, MOV, AVI, WebM
        </Typography>
        
        <Typography variant="body2" color="text.secondary">
          Maximum file size: 20MB
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {isAnalyzing && (
        <Box mt={2}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Analyzing your snowboarding video...
          </Typography>
          <LinearProgress />
        </Box>
      )}

      {uploadedVideo && analysisComplete && (
        <Box mt={3}>
          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Videocam color="primary" />
            Your Uploaded Video
          </Typography>
          <Box
            sx={{
              border: '1px solid',
              borderColor: 'grey.300',
              borderRadius: 2,
              overflow: 'hidden',
              backgroundColor: 'background.paper'
            }}
          >
            <video
              controls
              style={{
                width: '100%',
                maxHeight: '300px',
                display: 'block'
              }}
              src={URL.createObjectURL(uploadedVideo)}
            >
              Your browser does not support the video tag.
            </video>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            File: {uploadedVideo.name} ({(uploadedVideo.size / (1024 * 1024)).toFixed(1)} MB)
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default VideoUpload;
