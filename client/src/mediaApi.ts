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
  sampling_profile: 'overview' | 'action' | 'motion' | 'custom';
  sample_fps: number;
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
  source: 'human' | 'model' | 'model_corrected' | 'track_propagated';
  model_prediction_id?: string | null;
  propagation_id?: string | null;
}

export interface AnnotationDraft {
  label: string;
  annotation_type: 'bbox' | 'keypoints';
  geometry: Record<string, any>;
  source: 'human' | 'model' | 'model_corrected' | 'track_propagated';
  model_prediction_id?: string | null;
  propagation_id?: string | null;
}

export interface TrackPropagationResult {
  propagation_id: string;
  track_id: string;
  start_frame_number: number;
  end_frame_number: number;
  generated_count: number;
  corrected: boolean;
  frame_ids: string[];
}

export interface SanitizedExport {
  id: string;
  video_id: string;
  task_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  labels: string[];
  source_annotation_count: number;
  video_url?: string | null;
  manifest_url?: string | null;
  output_sha256?: string | null;
  reviewer?: string | null;
  processing_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ModelRun {
  id: string;
  video_id: string;
  model_kind: 'detection' | 'pose' | 'pii';
  provider: string;
  model_name: string;
  model_version: string;
  device: string;
  parameters: Record<string, unknown>;
  status: string;
  total_frames: number;
  processed_frames: number;
  latency_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ModelPrediction {
  id: string;
  model_run_id: string;
  frame_id: string;
  label: string;
  confidence: number;
  annotation_type: 'bbox' | 'keypoints';
  geometry: Record<string, any>;
  track_id?: string | null;
  associated_prediction_id?: string | null;
  association_score?: number | null;
  association_ambiguous?: boolean;
  status: 'PENDING' | 'ACCEPTED' | 'CORRECTED' | 'REJECTED';
  model_name: string;
  model_version: string;
}

export interface ModelMetrics {
  model_run_id: string;
  total_predictions: number;
  pending: number;
  accepted: number;
  corrected: number;
  rejected: number;
  acceptance_rate: number;
  correction_rate: number;
  rejection_rate: number;
  average_decision_time_ms?: number | null;
  by_label: Record<string, Record<string, number>>;
}

export interface AgreementMetrics {
  video_id?: string | null;
  bbox_comparisons: number;
  mean_bbox_iou?: number | null;
  keypoint_comparisons: number;
  mean_keypoint_pck?: number | null;
}

export interface DatasetHealth {
  video_id?: string | null;
  videos: number;
  frames: number;
  annotated_frames: number;
  propagated_annotations: number;
  propagation_operations: number;
  reviewed_frames: number;
  pending_tasks: number;
  completed_tasks: number;
  total_predictions: number;
  accepted_predictions: number;
  corrected_predictions: number;
  rejected_predictions: number;
  pending_predictions: number;
  model_acceptance_rate: number;
  model_correction_rate: number;
  model_rejection_rate: number;
  low_confidence_predictions: number;
  tracked_predictions: number;
  tracks: number;
  associated_snowboards: number;
  unassociated_snowboards: number;
  open_review_items: number;
  resolved_review_items: number;
  average_annotation_time_ms?: number | null;
  annotation_throughput_per_hour?: number | null;
  label_distribution: Record<string, number>;
  review_reason_distribution: Record<string, number>;
  agreement: AgreementMetrics;
}

export interface ReviewItem {
  id: string;
  video_id: string;
  frame_id: string;
  model_run_id: string;
  prediction_id?: string | null;
  reason: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  status: 'OPEN' | 'RESOLVED' | 'ESCALATED' | 'NEEDS_CORRECTION';
  score?: number | null;
  details: Record<string, unknown>;
  frame_number: number;
  timestamp_ms: number;
  image_url: string;
  prediction_label?: string | null;
  prediction_confidence?: number | null;
  prediction_track_id?: string | null;
  association_score?: number | null;
  annotation_task_id?: string | null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function ingestVideo(
  file: File,
  samplingProfile: 'overview' | 'action' | 'motion' = 'overview'
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('video', file);
  formData.append('sampling_profile', samplingProfile);
  const response = await fetch(`${MEDIA_API_BASE_URL}/api/videos`, {
    method: 'POST',
    headers: { 'Idempotency-Key': `${file.name}-${file.size}-${file.lastModified}-${samplingProfile}` },
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

export async function createSanitizedExport(
  videoId: string,
  taskId: string,
  reviewer: string
): Promise<SanitizedExport> {
  const payload = await parseResponse<{ sanitized_export: SanitizedExport }>(
    await fetch(`${MEDIA_API_BASE_URL}/api/videos/${videoId}/sanitized-exports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, reviewer }),
    })
  );
  return payload.sanitized_export;
}

export async function getSanitizedExport(exportId: string): Promise<SanitizedExport> {
  return parseResponse<SanitizedExport>(
    await fetch(`${MEDIA_API_BASE_URL}/api/sanitized-exports/${exportId}`)
  );
}

export const sanitizedBundleUrl = (exportId: string) =>
  `${MEDIA_API_BASE_URL}/api/sanitized-exports/${exportId}/bundle`;

export const taskExportUrl = (taskId: string, format: 'coco' | 'yolo') =>
  `${MEDIA_API_BASE_URL}/api/annotation-tasks/${taskId}/exports/${format}`;

export async function createModelRun(
  videoId: string,
  modelKind: 'detection' | 'pose' | 'pii'
): Promise<{ model_run: ModelRun; job: ProcessingJob }> {
  return parseResponse<{ model_run: ModelRun; job: ProcessingJob }>(
    await fetch(`${MEDIA_API_BASE_URL}/api/videos/${videoId}/model-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_kind: modelKind, confidence_threshold: 0.25 }),
    })
  );
}

export async function getModelRun(modelRunId: string): Promise<ModelRun> {
  return parseResponse<ModelRun>(
    await fetch(`${MEDIA_API_BASE_URL}/api/model-runs/${modelRunId}`)
  );
}

export async function getVideoModelRuns(videoId: string): Promise<ModelRun[]> {
  return parseResponse<ModelRun[]>(
    await fetch(`${MEDIA_API_BASE_URL}/api/videos/${videoId}/model-runs`)
  );
}

export async function getFramePredictions(frameId: string): Promise<ModelPrediction[]> {
  return parseResponse<ModelPrediction[]>(
    await fetch(`${MEDIA_API_BASE_URL}/api/frames/${frameId}/predictions`)
  );
}

export async function rejectModelPrediction(
  predictionId: string,
  taskId: string,
  durationMs: number
): Promise<void> {
  await parseResponse(
    await fetch(`${MEDIA_API_BASE_URL}/api/predictions/${predictionId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, duration_ms: durationMs }),
    })
  );
}

export async function propagateTrackPrediction(
  predictionId: string,
  taskId: string,
  geometry: Record<string, any>,
  startFrameNumber: number,
  endFrameNumber: number,
  durationMs: number
): Promise<TrackPropagationResult> {
  return parseResponse<TrackPropagationResult>(
    await fetch(`${MEDIA_API_BASE_URL}/api/predictions/${predictionId}/propagate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        geometry,
        start_frame_number: startFrameNumber,
        end_frame_number: endFrameNumber,
        duration_ms: durationMs,
        reviewer: 'portfolio-reviewer',
      }),
    })
  );
}

export async function getModelMetrics(modelRunId: string): Promise<ModelMetrics> {
  return parseResponse<ModelMetrics>(
    await fetch(`${MEDIA_API_BASE_URL}/api/model-runs/${modelRunId}/metrics`)
  );
}

export async function getDatasetHealth(videoId?: string): Promise<DatasetHealth> {
  const query = videoId ? `?video_id=${encodeURIComponent(videoId)}` : '';
  return parseResponse<DatasetHealth>(
    await fetch(`${MEDIA_API_BASE_URL}/api/dataset-health${query}`)
  );
}

export async function getReviewItems(status = 'OPEN', videoId?: string): Promise<ReviewItem[]> {
  const parameters = new URLSearchParams({ status });
  if (videoId) parameters.set('video_id', videoId);
  return parseResponse<ReviewItem[]>(
    await fetch(`${MEDIA_API_BASE_URL}/api/review-items?${parameters.toString()}`)
  );
}

export async function resolveReviewItem(
  reviewItemId: string,
  action: 'APPROVED' | 'DISMISSED' | 'ESCALATED' | 'NEEDS_CORRECTION',
  reviewer = 'portfolio-reviewer'
): Promise<ReviewItem> {
  return parseResponse<ReviewItem>(
    await fetch(`${MEDIA_API_BASE_URL}/api/review-items/${reviewItemId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, reviewer }),
    })
  );
}

export function mediaUrl(path: string): string {
  return path.startsWith('http') ? path : `${MEDIA_API_BASE_URL}${path}`;
}
