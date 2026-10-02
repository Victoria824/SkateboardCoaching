export const MEDIA_API_BASE_URL =
  process.env.REACT_APP_MEDIA_API_URL || 'http://localhost:8000';

export interface ProcessingJob {
  id: string;
  video_id: string;
  state: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ProcessedFrame {
  id: string;
  frame_number: number;
  timestamp_ms: number;
  image_url: string;
}

export interface ProcessedVideo {
  id: string;
  filename: string;
  file_size: number;
  duration_ms?: number | null;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  codec?: string | null;
  status: string;
  frames: ProcessedFrame[];
}

export interface UploadResult {
  video: ProcessedVideo;
  job: ProcessingJob;
}

export interface AnnotationTask {
  id: string;
  video_id: string;
  assigned_to?: string | null;
  status: string;
  priority: number;
  video?: ProcessedVideo;
}

export interface AnnotationRecord {
  id: string;
  task_id: string;
  frame_id: string;
  label: string;
  annotation_type: 'bbox' | 'keypoints';
  geometry: Record<string, any>;
  source: 'human' | 'model' | 'model_corrected';
  model_prediction_id?: string | null;
}

export interface AnnotationDraft {
  label: string;
  annotation_type: 'bbox' | 'keypoints';
  geometry: Record<string, any>;
  source: 'human' | 'model' | 'model_corrected';
  model_prediction_id?: string | null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function ingestVideo(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('video', file);
  const response = await fetch(`${MEDIA_API_BASE_URL}/api/videos`, {
    method: 'POST',
    headers: { 'Idempotency-Key': `${file.name}-${file.size}-${file.lastModified}` },
    body: formData,
  });
  return parseResponse<UploadResult>(response);
}

export async function getJob(jobId: string): Promise<ProcessingJob> {
  return parseResponse<ProcessingJob>(
    await fetch(`${MEDIA_API_BASE_URL}/api/jobs/${jobId}`)
  );
}

export async function getProcessedVideo(videoId: string): Promise<ProcessedVideo> {
  return parseResponse<ProcessedVideo>(
    await fetch(`${MEDIA_API_BASE_URL}/api/videos/${videoId}`)
  );
}

export async function createAnnotationTask(videoId: string): Promise<AnnotationTask> {
  return parseResponse<AnnotationTask>(
    await fetch(`${MEDIA_API_BASE_URL}/api/videos/${videoId}/annotation-tasks`, { method: 'POST' })
  );
}

export async function getAnnotationTask(taskId: string): Promise<AnnotationTask> {
  return parseResponse<AnnotationTask>(
    await fetch(`${MEDIA_API_BASE_URL}/api/annotation-tasks/${taskId}`)
  );
}

export async function getFrameAnnotations(taskId: string, frameId: string): Promise<AnnotationRecord[]> {
  return parseResponse<AnnotationRecord[]>(
    await fetch(`${MEDIA_API_BASE_URL}/api/annotation-tasks/${taskId}/frames/${frameId}/annotations`)
  );
}

export async function saveFrameAnnotations(
  taskId: string,
  frameId: string,
  annotations: AnnotationDraft[],
  durationMs: number
): Promise<AnnotationRecord[]> {
  const response = await fetch(
    `${MEDIA_API_BASE_URL}/api/annotation-tasks/${taskId}/frames/${frameId}/annotations`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ annotations, duration_ms: durationMs }),
    }
  );
  const payload = await parseResponse<{ annotations: AnnotationRecord[] }>(response);
  return payload.annotations;
}

export async function completeAnnotationTask(taskId: string): Promise<AnnotationTask> {
  return parseResponse<AnnotationTask>(
    await fetch(`${MEDIA_API_BASE_URL}/api/annotation-tasks/${taskId}/complete`, { method: 'POST' })
  );
}

export function mediaUrl(path: string): string {
  return path.startsWith('http') ? path : `${MEDIA_API_BASE_URL}${path}`;
}
