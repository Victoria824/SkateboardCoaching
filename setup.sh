#!/bin/bash

echo "🏂 Snowboard Coach AI - Setup Script"
echo "===================================="
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "📝 Creating .env file..."
    cat > .env << 'EOF'
# Replicate API Configuration
REPLICATE_API_TOKEN=your_replicate_api_token_here

# Server Configuration
PORT=5000
NODE_ENV=development

# File Upload Configuration
MAX_FILE_SIZE=50000000
UPLOAD_DIR=uploads
EOF
    echo "✅ .env file created!"
    echo ""
    echo "🔑 IMPORTANT: Edit .env file and add your Replicate API token!"
    echo "   Replace 'your_replicate_api_token_here' with your actual token"
    echo ""
else
    echo "✅ .env file found!"
fi

# Check if FFmpeg is installed
if command -v ffmpeg &> /dev/null; then
    echo "✅ FFmpeg is installed!"
else
    echo "❌ FFmpeg not found!"
    echo "📦 Installing FFmpeg..."
    brew install ffmpeg
    echo "✅ FFmpeg installed!"
fi

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing backend dependencies..."
    npm install
    echo "✅ Backend dependencies installed!"
else
    echo "✅ Backend dependencies found!"
fi

if [ ! -d "client/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd client && npm install && cd ..
    echo "✅ Frontend dependencies installed!"
else
    echo "✅ Frontend dependencies found!"
fi

echo ""
echo "🎉 Setup Complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Get your Replicate API token from https://replicate.com/"
echo "2. Edit .env file and add your token"
echo "3. Run: npm run dev"
echo "4. Open http://localhost:3000 in your browser"
echo "5. Upload a snowboarding video and get AI coaching!"
echo ""
echo "🔧 Available Commands:"
echo "  npm run dev          - Start the app"
echo "  npm run test-models  - Show available models"
echo "  npm run server       - Start backend only"
echo "  npm run client       - Start frontend only"
echo ""
