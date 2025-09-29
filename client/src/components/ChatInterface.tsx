import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  TextField,
  Button,
  Typography,
  Paper,
  Avatar,
  Chip
} from '@mui/material';
import { Send, Sports, Psychology } from '@mui/icons-material';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatInterfaceProps {
  chatHistory: ChatMessage[];
  onSendMessage: (message: string) => void;
  isAnalyzing: boolean;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ 
  chatHistory, 
  onSendMessage, 
  isAnalyzing 
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  const handleSendMessage = () => {
    if (inputMessage.trim() && !isAnalyzing) {
      onSendMessage(inputMessage.trim());
      setInputMessage('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const getQuickQuestions = () => [
    "How can I improve my balance?",
    "What about my edge control?",
    "Any tips for better posture?",
    "How's my arm positioning?"
  ];

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Chat Messages */}
      <Box 
        sx={{ 
          flex: 1, 
          overflowY: 'auto', 
          mb: 2,
          maxHeight: '400px',
          minHeight: '200px'
        }}
      >
        {chatHistory.length === 0 ? (
          <Box textAlign="center" py={4}>
            <Psychology sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Welcome to your AI Snowboarding Coach!
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Upload a video to get started, or ask me any snowboarding questions.
            </Typography>
            
            <Box display="flex" flexWrap="wrap" gap={1} justifyContent="center" mt={2}>
              {getQuickQuestions().map((question) => (
                <Chip
                  key={question}
                  label={question}
                  variant="outlined"
                  size="small"
                  onClick={() => onSendMessage(question)}
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Box>
          </Box>
        ) : (
          chatHistory.map((message, index) => (
            <Box
              key={index}
              sx={{
                display: 'flex',
                justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
                mb: 2
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 1,
                  maxWidth: '80%',
                  flexDirection: message.role === 'user' ? 'row-reverse' : 'row'
                }}
              >
                <Avatar
                  sx={{
                    bgcolor: message.role === 'user' ? 'primary.main' : 'secondary.main',
                    width: 32,
                    height: 32
                  }}
                >
                  {message.role === 'user' ? <Sports /> : <Psychology />}
                </Avatar>
                
                <Paper
                  elevation={1}
                  sx={{
                    p: 2,
                    bgcolor: message.role === 'user' ? 'primary.light' : 'grey.100',
                    color: message.role === 'user' ? 'primary.contrastText' : 'text.primary',
                    borderRadius: 2,
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  <Typography variant="body2">
                    {message.content}
                  </Typography>
                </Paper>
              </Box>
            </Box>
          ))
        )}
        
        {isAnalyzing && (
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'flex-start',
              mb: 2
            }}
          >
            <Box
              sx={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1
              }}
            >
              <Avatar sx={{ bgcolor: 'secondary.main', width: 32, height: 32 }}>
                <Psychology />
              </Avatar>
              
              <Paper
                elevation={1}
                sx={{
                  p: 2,
                  bgcolor: 'grey.100',
                  borderRadius: 2
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  Analyzing your video... This may take a moment.
                </Typography>
              </Paper>
            </Box>
          </Box>
        )}
        
        <div ref={messagesEndRef} />
      </Box>

      {/* Chat Input */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
        <TextField
          fullWidth
          multiline
          maxRows={3}
          placeholder="Ask your AI coach anything about snowboarding..."
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isAnalyzing}
          variant="outlined"
          size="small"
        />
        <Button
          variant="contained"
          onClick={handleSendMessage}
          disabled={!inputMessage.trim() || isAnalyzing}
          sx={{ minWidth: 'auto', px: 2 }}
        >
          <Send />
        </Button>
      </Box>
    </Box>
  );
};

export default ChatInterface;
