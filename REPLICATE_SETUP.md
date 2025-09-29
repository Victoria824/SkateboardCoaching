# 🚀 Replicate Setup Guide

## Why Replicate is Perfect for Your Snowboarding App

[Replicate](https://replicate.com/) is an excellent choice for your snowboarding coaching app because:

- **💰 Cost-Effective**: Pay only for compute time used
- **🎯 Specialized Models**: Access to models specifically designed for image/video analysis
- **⚡ Fast Processing**: Optimized for production use
- **🔧 Easy Integration**: Simple API calls
- **📊 No Monthly Fees**: Pay-as-you-go pricing

## 🔑 Getting Your Replicate API Token

### Step 1: Create Account
1. Go to [https://replicate.com/](https://replicate.com/)
2. Click **"Sign in"** or **"Try for free"**
3. Sign up with your email or GitHub account

### Step 2: Get API Token
1. Once logged in, click your profile icon (top right)
2. Select **"Account"** from the dropdown
3. Scroll down to **"API tokens"** section
4. Click **"Create token"**
5. Give it a name like "Snowboard Coach App"
6. Click **"Create token"**
7. **Copy the token immediately** - you won't see it again!

### Step 3: Add Credits
1. Go to **"Billing"** in your account
2. Add a payment method (credit card)
3. Add some credits ($10-20 is plenty to start)
4. You'll get some free credits when you sign up!

## 💰 Pricing (Very Affordable!)

**Replicate Pricing:**
- **CPU**: $0.000100/second
- **Nvidia T4 GPU**: $0.000225/second  
- **Nvidia L40S GPU**: $0.000975/second

**For Your Snowboarding App:**
- **Per video analysis**: ~$0.01-0.05
- **$10 in credits**: Will last for 200-1000 video analyses!
- **No monthly fees**: Pay only when you use it

## 🛠️ Models Used in Your App

Your snowboarding app uses these Replicate models:

1. **LLaVA (yorickvp/llava-v1.6-mistral-7b)**: 
   - Analyzes snowboarding images
   - Provides detailed coaching feedback
   - Cost: ~$0.01 per analysis

2. **LLaMA (meta/llama-2-70b-chat)**:
   - Synthesizes coaching advice
   - Creates structured reports
   - Cost: ~$0.005 per analysis

## 🚀 Quick Setup

1. **Get your API token** (steps above)
2. **Create .env file**:
   ```bash
   cp env.example .env
   ```
3. **Add your token**:
   ```env
   REPLICATE_API_TOKEN=r8_your_token_here
   ```
4. **Install dependencies**:
   ```bash
   npm install
   cd client && npm install && cd ..
   ```
5. **Start the app**:
   ```bash
   npm run dev
   ```

## 🎯 Alternative Models (If Needed)

If you want to try different models, edit `server/replicate-models.js`:

```javascript
const REPLICATE_MODELS = {
  // For image analysis
  IMAGE_ANALYSIS: "yorickvp/llava-v1.6-mistral-7b:latest",
  
  // Alternative image models
  IMAGE_ANALYSIS_ALT: "salesforce/blip-2:latest",
  
  // For text synthesis
  TEXT_SYNTHESIS: "meta/llama-2-70b-chat:latest",
  
  // Alternative text models
  TEXT_SYNTHESIS_ALT: "mistralai/mistral-7b-instruct-v0.1:latest"
};
```

## 🔍 Testing Your Setup

1. **Check API token**: Visit [https://replicate.com/account](https://replicate.com/account)
2. **Test a simple model**: Try running a basic model in the playground
3. **Check credits**: Make sure you have sufficient credits
4. **Run your app**: Upload a test video to see if it works

## 🆘 Troubleshooting

**Common Issues:**
- **"Invalid API token"**: Check your token is correct
- **"Insufficient credits"**: Add more credits to your account
- **"Model not found"**: The model name might have changed
- **"Rate limited"**: You're making too many requests too quickly

**Getting Help:**
- Check [Replicate Docs](https://replicate.com/docs)
- Visit [Replicate Discord](https://discord.gg/replicate)
- Check your account dashboard for usage stats

## 🎉 You're Ready!

Once you have your Replicate API token set up, your snowboarding coaching app will be able to:
- Analyze snowboarding videos frame by frame
- Provide detailed coaching feedback
- Generate structured improvement plans
- Chat with users about technique

The best part? It's incredibly cost-effective and scales automatically!
