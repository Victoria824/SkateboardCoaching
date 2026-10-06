import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import { ArrowBack, Check, Close, Edit, Refresh, ReportProblem } from '@mui/icons-material';

import {
  DatasetHealth,
  ReviewItem,
  getDatasetHealth,
  getReviewItems,
  mediaUrl,
  resolveReviewItem,
} from '../mediaApi';

const reasonLabel = (reason: string) => reason.toLowerCase().replace(/_/g, ' ');

const MetricCard: React.FC<{ label: string; value: string | number; detail?: string }> = ({
  label,
  value,
  detail,
}) => (
  <Paper sx={{ p: 2, flex: '1 1 180px', minWidth: 0 }}>
    <Typography variant="caption" color="text.secondary" textTransform="uppercase">
      {label}
    </Typography>
    <Typography variant="h4" fontWeight={800}>{value}</Typography>
    {detail && <Typography variant="caption" color="text.secondary">{detail}</Typography>}
  </Paper>
);

const DatasetHealthDashboard: React.FC = () => {
  const [health, setHealth] = useState<DatasetHealth | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [status, setStatus] = useState('OPEN');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthResult, reviewResult] = await Promise.all([
        getDatasetHealth(),
        getReviewItems(status),
      ]);
      setHealth(healthResult);
      setReviews(reviewResult);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load quality data.');
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (
    item: ReviewItem,
    action: 'APPROVED' | 'DISMISSED' | 'ESCALATED' | 'NEEDS_CORRECTION'
  ) => {
    setBusyId(item.id);
    setError(null);
    try {
      await resolveReviewItem(item.id, action);
      if (action === 'NEEDS_CORRECTION' && item.annotation_task_id) {
        window.location.href = `/#/annotate/${item.annotation_task_id}`;
        return;
      }
      await load();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to resolve review item.');
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !health) {
    return <Box minHeight="100vh" bgcolor="#eef2f7" p={8} textAlign="center"><CircularProgress /></Box>;
  }

  return (
    <Box minHeight="100vh" bgcolor="#eef2f7" p={{ xs: 2, md: 4 }}>
      <Box maxWidth={1280} mx="auto">
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} mb={3}>
          <Button href="/" startIcon={<ArrowBack />}>Coach</Button>
          <Box flex={1}>
            <Typography variant="h4" fontWeight={800}>Dataset health</Typography>
            <Typography color="text.secondary">
              Model quality, human agreement, review routing, and annotation throughput
            </Typography>
          </Box>
          <Button onClick={load} startIcon={<Refresh />} disabled={loading}>Refresh</Button>
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {health && <>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap mb={3}>
            <MetricCard label="Frames" value={health.frames} detail={`${health.annotated_frames} annotated`} />
            <MetricCard label="Needs review" value={health.open_review_items} detail={`${health.resolved_review_items} resolved`} />
            <MetricCard label="Acceptance" value={`${(health.model_acceptance_rate * 100).toFixed(0)}%`} detail={`${health.total_predictions} predictions`} />
            <MetricCard label="BBox IoU" value={health.agreement.mean_bbox_iou == null ? '—' : health.agreement.mean_bbox_iou.toFixed(2)} detail={`${health.agreement.bbox_comparisons} comparisons`} />
            <MetricCard label="Keypoint PCK" value={health.agreement.mean_keypoint_pck == null ? '—' : health.agreement.mean_keypoint_pck.toFixed(2)} detail={`${health.agreement.keypoint_comparisons} comparisons`} />
            <MetricCard label="Throughput" value={health.annotation_throughput_per_hour == null ? '—' : Math.round(health.annotation_throughput_per_hour)} detail="annotations / hour" />
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} mb={3}>
            <Paper sx={{ p: 2.5, flex: 1 }}>
              <Typography variant="h6" gutterBottom>Model decisions</Typography>
              <Typography variant="body2" color="text.secondary" mb={1}>
                {health.accepted_predictions} accepted · {health.corrected_predictions} corrected · {health.rejected_predictions} rejected · {health.pending_predictions} pending
              </Typography>
              <LinearProgress
                variant="determinate"
                value={health.model_acceptance_rate * 100}
                color="success"
                sx={{ height: 10, borderRadius: 5 }}
              />
              <Typography variant="caption" color="text.secondary">
                {health.low_confidence_predictions} predictions below 50% confidence
              </Typography>
            </Paper>
            <Paper sx={{ p: 2.5, flex: 1 }}>
              <Typography variant="h6" gutterBottom>Review reasons</Typography>
              <Stack direction="row" gap={1} flexWrap="wrap">
                {Object.entries(health.review_reason_distribution).map(([reason, count]) => (
                  <Chip key={reason} label={`${reasonLabel(reason)} · ${count}`} />
                ))}
                {!Object.keys(health.review_reason_distribution).length && (
                  <Typography color="text.secondary">No routed items yet.</Typography>
                )}
              </Stack>
            </Paper>
          </Stack>
        </>}

        <Paper sx={{ p: 2.5 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} spacing={2} mb={2}>
            <Box flex={1}>
              <Typography variant="h5" fontWeight={750}>Review queue</Typography>
              <Typography variant="body2" color="text.secondary">
                Every action is persisted as an auditable review event.
              </Typography>
            </Box>
            <Select size="small" value={status} onChange={(event) => setStatus(event.target.value)}>
              <MenuItem value="OPEN">Open</MenuItem>
              <MenuItem value="NEEDS_CORRECTION">Needs correction</MenuItem>
              <MenuItem value="ESCALATED">Escalated</MenuItem>
              <MenuItem value="RESOLVED">Resolved</MenuItem>
            </Select>
          </Stack>

          <Stack spacing={1.5}>
            {reviews.map((item) => (
              <Paper key={item.id} variant="outlined" sx={{ p: 1.5 }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
                  <Box
                    component="img"
                    src={mediaUrl(item.image_url)}
                    alt={`Frame ${item.frame_number}`}
                    sx={{ width: { xs: '100%', md: 180 }, height: 102, objectFit: 'cover', bgcolor: 'black', borderRadius: 1 }}
                  />
                  <Box flex={1} minWidth={0}>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mb={0.5}>
                      <Chip size="small" label={item.severity} color={item.severity === 'HIGH' ? 'error' : item.severity === 'MEDIUM' ? 'warning' : 'default'} />
                      <Chip size="small" variant="outlined" label={reasonLabel(item.reason)} />
                      {item.prediction_label && <Chip size="small" label={item.prediction_label} />}
                    </Stack>
                    <Typography fontWeight={700}>Frame {item.frame_number} · {(item.timestamp_ms / 1000).toFixed(1)}s</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.prediction_confidence == null ? 'Frame-level check' : `${(item.prediction_confidence * 100).toFixed(1)}% confidence`}
                      {item.score == null ? '' : ` · score ${item.score.toFixed(3)}`}
                    </Typography>
                  </Box>
                  {item.status === 'OPEN' && <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    <Button size="small" color="success" startIcon={<Check />} disabled={busyId === item.id} onClick={() => resolve(item, 'APPROVED')}>Approve</Button>
                    <Button size="small" startIcon={<Edit />} disabled={busyId === item.id || !item.annotation_task_id} onClick={() => resolve(item, 'NEEDS_CORRECTION')}>Correct</Button>
                    <Button size="small" color="warning" startIcon={<ReportProblem />} disabled={busyId === item.id} onClick={() => resolve(item, 'ESCALATED')}>Escalate</Button>
                    <Button size="small" color="inherit" startIcon={<Close />} disabled={busyId === item.id} onClick={() => resolve(item, 'DISMISSED')}>Dismiss</Button>
                  </Stack>}
                </Stack>
              </Paper>
            ))}
            {!reviews.length && !loading && (
              <Alert severity="success">No {status.toLowerCase().replace(/_/g, ' ')} review items.</Alert>
            )}
          </Stack>
        </Paper>
      </Box>
    </Box>
  );
};

export default DatasetHealthDashboard;
