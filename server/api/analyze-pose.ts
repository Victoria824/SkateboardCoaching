import { NextRequest, NextResponse } from 'next/server';

export const config = {
  runtime: 'edge',
  maxDuration: 300,
};

export default async function handler(req: NextRequest) {
  // Set CORS headers
  const headers = new Headers();
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  headers.set('Access-Control-Allow-Credentials', 'true');

  if (req.method === 'OPTIONS') {
    return new NextResponse(null, { status: 200, headers });
  }

  try {
    const formData = await req.formData();
    const video = formData.get('video') as File;
    
    if (!video) {
      return NextResponse.json({ error: 'No video file uploaded' }, { status: 400, headers });
    }

    // For now, return a simple response to test
    return NextResponse.json({
      success: true,
      message: 'Video received successfully',
      fileSize: video.size,
      fileName: video.name
    }, { headers });

  } catch (error) {
    return NextResponse.json({ error: 'Failed to process video' }, { status: 500, headers });
  }
}
