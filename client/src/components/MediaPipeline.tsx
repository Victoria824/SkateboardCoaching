import React, { ChangeEvent, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import { CloudUpload, Dataset, MovieFilter } from '@mui/icons-material';

import {
  createAnnotationTask,
  getJob,
  getProcessedVideo,
  ingestVideo,
  mediaUrl,
  ProcessedVideo,
  ProcessingJob,
} from '../mediaApi';

const TERMINAL_STATES = new Set(['READY_FOR_ANNOTATION', 'FAILED']);

const MediaPipeline: React.FC = () => {
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [video, setVideo] = useState<ProcessedVideo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [samplingProfile, setSamplingProfile] = useState<'overview' | 'action' | 'motion'>('overview');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!job || TERMINAL_STATES.has(job.state)) return;

    const timer = window.setInterval(async () => {
      try {
        const nextJob = await getJob(job.id);
        setJob(nextJob);
        if (nextJob.state === 'READY_FOR_ANNOTATION') {
          setVideo(await getProcessedVideo(nextJob.video_id));
        }
        if (nextJob.state === 'FAILED') {
          setError(nextJob.error_message || 'Video processing failed.');
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Unable to read job status.');
      }
    }, 1000);

    return () => window.clearInterval(timer);
  }, [job]);

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setJob(null);
    setVideo(null);
    setTaskId(null);
    try {
      const result = await ingestVideo(file, samplingProfile);
      setJob(result.job);
      setVideo(result.video);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Upload failed.');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const active = uploading || (job !== null && !TERMINAL_STATES.has(job.state));

  const prepareAnnotationTask = async () => {
    if (!video) return;
    setError(null);
    try {
      const task = await createAnnotationTask(video.id);
      setTaskId(task.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create annotation task.');
    }
  };

  return (
    <Card elevation={8} sx={{ mb: 4, borderRadius: 4, border: '1px solid rgba(0,0,0,.06)' }}>
      <CardContent sx={{ p: 3 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems={{ md: 'center' }}>
          <Box flex={1}>
            <Typography variant="overline" color="primary" fontWeight={700}>
              Vision data infrastructure
            </Typography>
            <Typography variant="h5" fontWeight={700} gutterBottom>
              <Dataset sx={{ mr: 1, verticalAlign: 'middle' }} />
              Prepare a video for annotation
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Upload returns immediately. A separate worker reads real metadata and extracts timestamped frames with FFmpeg.
            </Typography>
          </Box>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <Select
              size="small"
              value={samplingProfile}
              disabled={active}
              onChange={(event) => setSamplingProfile(event.target.value as 'overview' | 'action' | 'motion')}
            >
              <MenuItem value="overview">Overview · 1 FPS</MenuItem>
              <MenuItem value="action">Action · 5 FPS</MenuItem>
              <MenuItem value="motion">Motion-aware · 1–5 FPS</MenuItem>
            </Select>
            <input ref={inputRef} hidden type="file" accept="video/*,.mkv" onChange={handleFile} />
            <Button
              variant="contained"
              size="large"
              startIcon={<CloudUpload />}
              disabled={active}
              onClick={() => inputRef.current?.click()}
            >
              {uploading ? 'Uploading…' : 'Ingest video'}
            </Button>
          </Stack>
        </Stack>

        {job && (
          <Box mt={3}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
              <Chip size="small" label={job.state.replace(/_/g, ' ')} color={job.state === 'FAILED' ? 'error' : 'primary'} />
              <Typography variant="caption" color="text.secondary">
                Attempt {job.attempts}/{job.max_attempts} · {job.progress}%
              </Typography>
            </Stack>
            <LinearProgress variant="determinate" value={job.progress} />
          </Box>
        )}

        {error && <Alert severity="error" sx={{ mt: 3 }}>{error}</Alert>}

        {video?.status === 'READY_FOR_ANNOTATION' && (
          <Box mt={3}>
            <Alert severity="success" icon={<MovieFilter />}>
              {video.frames.length} real frames at {video.sample_fps} FPS ({video.sampling_profile}) are ready for annotation · {video.width}×{video.height} · {video.codec} · {video.duration_ms ? (video.duration_ms / 1000).toFixed(1) : '—'}s
            </Alert>
            <Box mt={2}>
              {taskId ? (
                <Button variant="contained" href={`/#/annotate/${taskId}`}>Open annotation workspace</Button>
              ) : (
                <Button variant="outlined" onClick={prepareAnnotationTask}>Create annotation task</Button>
              )}
            </Box>
            <Box mt={2} display="grid" gridTemplateColumns="repeat(auto-fill, minmax(150px, 1fr))" gap={1.5}>
              {video.frames.slice(0, 6).map((frame) => (
                <Box key={frame.id}>
                  <Box
                    component="img"
                    src={mediaUrl(frame.image_url)}
                    alt={`Frame ${frame.frame_number}`}
                    sx={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', borderRadius: 1 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Frame {frame.frame_number} · {(frame.timestamp_ms / 1000).toFixed(1)}s
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default MediaPipeline;
