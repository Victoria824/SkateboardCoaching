import React, { PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import {
  ArrowBack,
  ArrowForward,
  AutoAwesome,
  Check,
  Close,
  CropFree,
  Delete,
  Edit,
  Save,
  ScatterPlot,
} from '@mui/icons-material';

import {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTask,
  ModelMetrics,
  ModelPrediction,
  ModelRun,
  completeAnnotationTask,
  createModelRun,
  getAnnotationTask,
  getFrameAnnotations,
  getFramePredictions,
  getModelMetrics,
  getModelRun,
  getVideoModelRuns,
  mediaUrl,
  propagateTrackPrediction,
  rejectModelPrediction,
  saveFrameAnnotations,
} from '../mediaApi';
import { predictionToAnnotation, updatePredictionStatus } from '../annotation/predictionState';

type Tool = 'bbox' | 'keypoints';
type LocalAnnotation = AnnotationDraft & { id: string };
type BBox = { x: number; y: number; width: number; height: number };
type Point = { name: string; x: number; y: number; visible: boolean };
type Operation =
  | { kind: 'draw'; startX: number; startY: number }
  | { kind: 'move'; id: string; startX: number; startY: number; original: BBox }
  | { kind: 'resize'; id: string; original: BBox }
  | { kind: 'point'; id: string; name: string };

const KEYPOINTS = [
  'head', 'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
  'left_wrist', 'right_wrist', 'left_hip', 'right_hip', 'left_knee',
  'right_knee', 'left_ankle', 'right_ankle',
];

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const localId = () => `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const AnnotationWorkspace: React.FC<{ taskId: string }> = ({ taskId }) => {
  const [task, setTask] = useState<AnnotationTask | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [annotations, setAnnotations] = useState<LocalAnnotation[]>([]);
  const [predictions, setPredictions] = useState<ModelPrediction[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedPredictionId, setSelectedPredictionId] = useState<string | null>(null);
  const [modelRun, setModelRun] = useState<ModelRun | null>(null);
  const [modelJobProgress, setModelJobProgress] = useState(0);
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null);
  const [tool, setTool] = useState<Tool>('bbox');
  const [label, setLabel] = useState('rider');
  const [keypointName, setKeypointName] = useState(KEYPOINTS[0]);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [draftBox, setDraftBox] = useState<BBox | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [propagationRadius, setPropagationRadius] = useState(2);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const frameStartedAt = useRef(Date.now());
  const decisionStartedAt = useRef(Date.now());

  const frames = task?.video?.frames || [];
  const frame = frames[frameIndex];
  const selectedPrediction = predictions.find((item) => item.id === selectedPredictionId) || null;
  const selectedAnnotation = annotations.find((item) => item.id === selectedId) || null;
  const propagationPrediction = selectedPrediction || predictions.find(
    (item) => item.id === selectedAnnotation?.model_prediction_id
  ) || null;

  useEffect(() => {
    getAnnotationTask(taskId)
      .then(async (loadedTask) => {
        setTask(loadedTask);
        if (loadedTask.video) {
          const runs = await getVideoModelRuns(loadedTask.video.id);
          const latestRun = runs[0];
          if (latestRun) {
            setModelRun(latestRun);
            setModelJobProgress(latestRun.total_frames
              ? Math.round((latestRun.processed_frames / latestRun.total_frames) * 100)
              : 0);
            setMetrics(await getModelMetrics(latestRun.id));
          }
        }
      })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : 'Unable to load task.'));
  }, [taskId]);

  useEffect(() => {
    if (!frame) return;
    setError(null);
    setMessage(null);
    setSelectedId(null);
    setSelectedPredictionId(null);
    frameStartedAt.current = Date.now();
    Promise.all([getFrameAnnotations(taskId, frame.id), getFramePredictions(frame.id)])
      .then(async ([records, predictionRecords]) => {
        setAnnotations(records.map((record: AnnotationRecord) => ({
          id: record.id,
          label: record.label,
          annotation_type: record.annotation_type,
          geometry: record.geometry,
          source: record.source,
          model_prediction_id: record.model_prediction_id,
          propagation_id: record.propagation_id,
        })));
        setPredictions(predictionRecords);
        const latestRunId = predictionRecords[predictionRecords.length - 1]?.model_run_id;
        if (latestRunId) setMetrics(await getModelMetrics(latestRunId));
        setDirty(false);
      })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : 'Unable to load annotations.'));
  }, [frame, taskId]);

  useEffect(() => {
    if (!modelRun || !['QUEUED', 'RUNNING', 'RETRY_PENDING'].includes(modelRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await getModelRun(modelRun.id);
        setModelRun(nextRun);
        setModelJobProgress(nextRun.total_frames
          ? Math.round((nextRun.processed_frames / nextRun.total_frames) * 100)
          : 0);
        if (nextRun.status === 'COMPLETED' && frame) {
          setPredictions(await getFramePredictions(frame.id));
          setMetrics(await getModelMetrics(nextRun.id));
          setMessage(`${nextRun.model_kind} predictions are ready`);
        }
        if (nextRun.status === 'FAILED') {
          setError(nextRun.error_message || 'Model inference failed.');
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Unable to read inference status.');
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [frame, modelRun]);

  const normalizedPoint = (event: ReactPointerEvent<SVGSVGElement | SVGElement>) => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds) return { x: 0, y: 0 };
    return {
      x: clamp((event.clientX - bounds.left) / bounds.width),
      y: clamp((event.clientY - bounds.top) / bounds.height),
    };
  };

  const selectPrediction = (predictionId: string) => {
    decisionStartedAt.current = Date.now();
    setSelectedPredictionId(predictionId);
    setSelectedId(null);
  };

  const updateBBox = (id: string, geometry: BBox) => {
    setAnnotations((items) => items.map((item) => item.id === id ? { ...item, geometry } : item));
    setDirty(true);
  };

  const updatePoint = (id: string, name: string, x: number, y: number) => {
    setAnnotations((items) => items.map((item) => {
      if (item.id !== id) return item;
      const points = (item.geometry.points as Point[]).map((point) =>
        point.name === name ? { ...point, x, y } : point
      );
      return { ...item, geometry: { points } };
    }));
    setDirty(true);
  };

  const handleCanvasDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.target !== svgRef.current) return;
    const point = normalizedPoint(event);
    if (tool === 'bbox') {
      setOperation({ kind: 'draw', startX: point.x, startY: point.y });
      setDraftBox({ x: point.x, y: point.y, width: 0, height: 0 });
      setSelectedId(null);
      setSelectedPredictionId(null);
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }

    const pose = annotations.find((item) => item.annotation_type === 'keypoints');
    if (pose) {
      const existing = (pose.geometry.points as Point[]).filter((item) => item.name !== keypointName);
      setAnnotations((items) => items.map((item) => item.id === pose.id
        ? { ...item, geometry: { points: [...existing, { name: keypointName, ...point, visible: true }] } }
        : item));
      setSelectedId(pose.id);
      setSelectedPredictionId(null);
    } else {
      const id = localId();
      setAnnotations((items) => [...items, {
        id,
        label: 'rider_pose',
        annotation_type: 'keypoints',
        geometry: { points: [{ name: keypointName, ...point, visible: true }] },
        source: 'human',
      }]);
      setSelectedId(id);
      setSelectedPredictionId(null);
    }
    setDirty(true);
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!operation) return;
    const point = normalizedPoint(event);
    if (operation.kind === 'draw') {
      setDraftBox({
        x: Math.min(operation.startX, point.x),
        y: Math.min(operation.startY, point.y),
        width: Math.abs(point.x - operation.startX),
        height: Math.abs(point.y - operation.startY),
      });
    } else if (operation.kind === 'move') {
      const x = clamp(operation.original.x + point.x - operation.startX, 0, 1 - operation.original.width);
      const y = clamp(operation.original.y + point.y - operation.startY, 0, 1 - operation.original.height);
      updateBBox(operation.id, { ...operation.original, x, y });
    } else if (operation.kind === 'resize') {
      updateBBox(operation.id, {
        ...operation.original,
        width: Math.max(0.005, point.x - operation.original.x),
        height: Math.max(0.005, point.y - operation.original.y),
      });
    } else {
      updatePoint(operation.id, operation.name, point.x, point.y);
    }
  };

  const handlePointerUp = () => {
    if (operation?.kind === 'draw' && draftBox && draftBox.width >= 0.005 && draftBox.height >= 0.005) {
      const id = localId();
      setAnnotations((items) => [...items, {
        id,
        label,
        annotation_type: 'bbox',
        geometry: draftBox,
        source: 'human',
      }]);
      setSelectedId(id);
      setDirty(true);
    }
    setOperation(null);
    setDraftBox(null);
  };

  const save = useCallback(async () => {
    if (!frame || saving) return false;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveFrameAnnotations(
        taskId,
        frame.id,
        annotations.map(({ id, ...item }) => item),
        Date.now() - frameStartedAt.current
      );
      setAnnotations(saved.map((record) => ({
        id: record.id,
        label: record.label,
        annotation_type: record.annotation_type,
        geometry: record.geometry,
        source: record.source,
        model_prediction_id: record.model_prediction_id,
        propagation_id: record.propagation_id,
      })));
      setDirty(false);
      setMessage(`Saved ${saved.length} annotations`);
      const predictionRecords = await getFramePredictions(frame.id);
      setPredictions(predictionRecords);
      const runId = predictionRecords[0]?.model_run_id || modelRun?.id;
      if (runId) setMetrics(await getModelMetrics(runId));
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Save failed.');
      return false;
    } finally {
      setSaving(false);
    }
  }, [annotations, frame, modelRun?.id, saving, taskId]);

  const navigate = useCallback(async (offset: number) => {
    if (dirty && !await save()) return;
    setFrameIndex((current) => clamp(current + offset, 0, Math.max(0, frames.length - 1)));
  }, [dirty, frames.length, save]);

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    setAnnotations((items) => items.filter((item) => item.id !== selectedId));
    setSelectedId(null);
    setDirty(true);
  }, [selectedId]);

  const runInference = async (modelKind: 'detection' | 'pose') => {
    if (!task?.video) return;
    setError(null);
    setMessage(null);
    try {
      const created = await createModelRun(task.video.id, modelKind);
      setModelRun(created.model_run);
      setModelJobProgress(0);
      setMessage(`${modelKind} inference queued`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to start inference.');
    }
  };

  const acceptPrediction = useCallback(async () => {
    if (!selectedPrediction || !frame || saving) return;
    setSaving(true);
    setError(null);
    const next = [...annotations, {
      id: localId(),
      ...predictionToAnnotation(selectedPrediction, 'model'),
    }];
    try {
      const saved = await saveFrameAnnotations(
        taskId,
        frame.id,
        next.map(({ id, ...item }) => item),
        Date.now() - decisionStartedAt.current
      );
      setAnnotations(saved.map((record) => ({
        id: record.id,
        label: record.label,
        annotation_type: record.annotation_type,
        geometry: record.geometry,
        source: record.source,
        model_prediction_id: record.model_prediction_id,
        propagation_id: record.propagation_id,
      })));
      setPredictions(await getFramePredictions(frame.id));
      setSelectedPredictionId(null);
      setDirty(false);
      setMessage('Prediction accepted');
      if (selectedPrediction.model_run_id) {
        setMetrics(await getModelMetrics(selectedPrediction.model_run_id));
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to accept prediction.');
    } finally {
      setSaving(false);
    }
  }, [annotations, frame, saving, selectedPrediction, taskId]);

  const correctPrediction = useCallback(() => {
    if (!selectedPrediction) return;
    const id = localId();
    setAnnotations((items) => [...items, {
      id,
      ...predictionToAnnotation(selectedPrediction, 'model_corrected'),
    }]);
    setPredictions((items) => updatePredictionStatus(items, selectedPrediction.id, 'CORRECTED'));
    setSelectedId(id);
    setSelectedPredictionId(null);
    setDirty(true);
    setMessage('Prediction copied for correction; edit it and save the frame');
  }, [selectedPrediction]);

  const rejectPrediction = useCallback(async () => {
    if (!selectedPrediction) return;
    try {
      await rejectModelPrediction(
        selectedPrediction.id,
        taskId,
        Date.now() - decisionStartedAt.current
      );
      setPredictions((items) => updatePredictionStatus(items, selectedPrediction.id, 'REJECTED'));
      setSelectedPredictionId(null);
      setMessage('Prediction rejected');
      setMetrics(await getModelMetrics(selectedPrediction.model_run_id));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to reject prediction.');
    }
  }, [selectedPrediction, taskId]);

  const propagateTrack = async () => {
    if (!frame || !propagationPrediction?.track_id || propagationPrediction.annotation_type !== 'bbox') return;
    const sourceGeometry = selectedAnnotation?.model_prediction_id === propagationPrediction.id
      ? selectedAnnotation.geometry
      : propagationPrediction.geometry;
    if (dirty && !await save()) return;
    setSaving(true);
    setError(null);
    try {
      const startFrame = Math.max(1, frame.frame_number - propagationRadius);
      const endFrame = Math.min(frames.length, frame.frame_number + propagationRadius);
      const result = await propagateTrackPrediction(
        propagationPrediction.id,
        taskId,
        sourceGeometry,
        startFrame,
        endFrame,
        Date.now() - decisionStartedAt.current
      );
      const [records, predictionRecords] = await Promise.all([
        getFrameAnnotations(taskId, frame.id),
        getFramePredictions(frame.id),
      ]);
      setAnnotations(records.map((record) => ({
        id: record.id,
        label: record.label,
        annotation_type: record.annotation_type,
        geometry: record.geometry,
        source: record.source,
        model_prediction_id: record.model_prediction_id,
        propagation_id: record.propagation_id,
      })));
      setPredictions(predictionRecords);
      setSelectedId(null);
      setSelectedPredictionId(null);
      setDirty(false);
      setMessage(
        `${result.corrected ? 'Correction' : 'Prediction'} propagated to ${result.generated_count} tracked frames`
      );
      setMetrics(await getModelMetrics(propagationPrediction.model_run_id));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to propagate track.');
    } finally {
      setSaving(false);
    }
  };

  const completeTask = async () => {
    if (dirty && !await save()) return;
    try {
      const completed = await completeAnnotationTask(taskId);
      setTask((current) => current ? { ...current, ...completed } : current);
      setMessage('Task completed');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to complete task.');
    }
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        save();
      } else if (event.key === 'ArrowLeft') {
        navigate(event.shiftKey ? -10 : -1);
      } else if (event.key === 'ArrowRight') {
        navigate(event.shiftKey ? 10 : 1);
      } else if (event.key.toLowerCase() === 'b') {
        setTool('bbox');
      } else if (event.key.toLowerCase() === 'k') {
        setTool('keypoints');
      } else if (event.key.toLowerCase() === 'a' && selectedPrediction) {
        acceptPrediction();
      } else if (event.key.toLowerCase() === 'r' && selectedPrediction) {
        rejectPrediction();
      } else if (event.key.toLowerCase() === 'c' && selectedPrediction) {
        correctPrediction();
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        deleteSelected();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [acceptPrediction, correctPrediction, deleteSelected, navigate, rejectPrediction, save, selectedPrediction]);

  if (error && !task) return <Alert severity="error">{error}</Alert>;
  if (!task || !frame) return <Box p={8} textAlign="center"><CircularProgress /></Box>;

  return (
    <Box minHeight="100vh" bgcolor="#111827" color="white" p={{ xs: 1, md: 2 }}>
      <Paper sx={{ p: 1.5, mb: 2, bgcolor: '#1f2937', color: 'white' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
          <Button href="/" color="inherit" startIcon={<ArrowBack />}>Coach</Button>
          <Button href="/#/quality" color="inherit">Quality</Button>
          <Typography fontWeight={700} flex={1}>Annotation task · {task.video?.filename}</Typography>
          <Chip label={task.status} color="primary" size="small" />
          <Typography variant="body2">Frame {frameIndex + 1} / {frames.length} · {(frame.timestamp_ms / 1000).toFixed(1)}s</Typography>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}>
        <Box flex={1} minWidth={0}>
          <Box
            position="relative"
            width="100%"
            sx={{ aspectRatio: `${task.video?.width || 16}/${task.video?.height || 9}`, bgcolor: 'black', userSelect: 'none' }}
          >
            <Box component="img" src={mediaUrl(frame.image_url)} alt={`Frame ${frame.frame_number}`} sx={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
            <svg
              ref={svgRef}
              viewBox="0 0 1000 1000"
              preserveAspectRatio="none"
              onPointerDown={handleCanvasDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', cursor: tool === 'bbox' ? 'crosshair' : 'copy', touchAction: 'none' }}
            >
              {predictions.filter((prediction) => prediction.status === 'PENDING').map((prediction) =>
                prediction.annotation_type === 'bbox' ? (() => {
                  const box = prediction.geometry as BBox;
                  const selected = selectedPredictionId === prediction.id;
                  return <g key={prediction.id}>
                    <rect
                      x={box.x * 1000} y={box.y * 1000} width={box.width * 1000} height={box.height * 1000}
                      fill="rgba(245,158,11,.08)" stroke={selected ? '#facc15' : '#f59e0b'}
                      strokeWidth={selected ? 6 : 4} strokeDasharray="12 8" vectorEffect="non-scaling-stroke"
                      onPointerDown={(event) => {
                        event.stopPropagation();
                        selectPrediction(prediction.id);
                      }}
                    />
                    <text x={box.x * 1000 + 8} y={box.y * 1000 + 28} fill="#fbbf24" fontSize="24">
                      {prediction.label}{prediction.track_id ? ` #${prediction.track_id}` : ''} {(prediction.confidence * 100).toFixed(0)}%
                    </text>
                  </g>;
                })() : (prediction.geometry.points as Point[]).map((point) => (
                  <g key={`${prediction.id}-${point.name}`} onPointerDown={(event) => {
                    event.stopPropagation();
                    selectPrediction(prediction.id);
                  }}>
                    <circle cx={point.x * 1000} cy={point.y * 1000} r="10" fill="#f59e0b" stroke="#fef3c7" strokeWidth="3" vectorEffect="non-scaling-stroke" />
                    <text x={point.x * 1000 + 14} y={point.y * 1000 - 12} fill="#fbbf24" fontSize="20">{point.name}</text>
                  </g>
                ))
              )}
              {annotations.map((annotation) => annotation.annotation_type === 'bbox' ? (() => {
                const box = annotation.geometry as BBox;
                const selected = selectedId === annotation.id;
                const annotationColor = annotation.source === 'model'
                  ? '#22c55e'
                  : annotation.source === 'model_corrected'
                    ? '#a855f7'
                    : annotation.source === 'track_propagated' ? '#14b8a6' : '#0ea5e9';
                return <g key={annotation.id}>
                  <rect
                    x={box.x * 1000} y={box.y * 1000} width={box.width * 1000} height={box.height * 1000}
                    fill="rgba(14,165,233,.12)" stroke={selected ? '#facc15' : annotationColor} strokeWidth={selected ? 6 : 4}
                    vectorEffect="non-scaling-stroke"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      const point = normalizedPoint(event);
                      setSelectedId(annotation.id);
                      setSelectedPredictionId(null);
                      setOperation({ kind: 'move', id: annotation.id, startX: point.x, startY: point.y, original: box });
                    }}
                  />
                  <text x={box.x * 1000 + 8} y={box.y * 1000 + 28} fill="#fff" fontSize="24">{annotation.label}</text>
                  {selected && <rect
                    x={(box.x + box.width) * 1000 - 10} y={(box.y + box.height) * 1000 - 10} width="20" height="20" fill="#facc15"
                    onPointerDown={(event) => { event.stopPropagation(); setOperation({ kind: 'resize', id: annotation.id, original: box }); }}
                  />}
                </g>;
              })() : (annotation.geometry.points as Point[]).map((point) => (
                <g key={`${annotation.id}-${point.name}`}>
                  <circle
                    cx={point.x * 1000} cy={point.y * 1000} r="10" fill="#f43f5e" stroke="white" strokeWidth="3"
                    vectorEffect="non-scaling-stroke"
                    onPointerDown={(event) => { event.stopPropagation(); setSelectedId(annotation.id); setSelectedPredictionId(null); setOperation({ kind: 'point', id: annotation.id, name: point.name }); }}
                  />
                  <text x={point.x * 1000 + 14} y={point.y * 1000 - 12} fill="white" fontSize="20">{point.name}</text>
                </g>
              )))}
              {draftBox && <rect x={draftBox.x * 1000} y={draftBox.y * 1000} width={draftBox.width * 1000} height={draftBox.height * 1000} fill="rgba(250,204,21,.1)" stroke="#facc15" strokeWidth="4" vectorEffect="non-scaling-stroke" />}
            </svg>
          </Box>
          <Stack direction="row" spacing={1} justifyContent="center" mt={1.5}>
            <Button variant="outlined" color="inherit" disabled={frameIndex === 0} onClick={() => navigate(-1)} startIcon={<ArrowBack />}>Previous</Button>
            <Button variant="outlined" color="inherit" disabled={frameIndex === frames.length - 1} onClick={() => navigate(1)} endIcon={<ArrowForward />}>Next</Button>
          </Stack>
        </Box>

        <Paper sx={{ width: { lg: 300 }, p: 2, alignSelf: 'flex-start' }}>
          <Typography variant="h6" gutterBottom><AutoAwesome sx={{ verticalAlign: 'middle', mr: 1 }} />Model assist</Typography>
          <Stack direction="row" spacing={1} mb={1}>
            <Button size="small" variant="outlined" disabled={modelRun?.status === 'QUEUED' || modelRun?.status === 'RUNNING'} onClick={() => runInference('detection')}>Detect</Button>
            <Button size="small" variant="outlined" disabled={modelRun?.status === 'QUEUED' || modelRun?.status === 'RUNNING'} onClick={() => runInference('pose')}>Pose</Button>
          </Stack>
          {modelRun && (
            <Box mb={2}>
              <Typography variant="caption" color="text.secondary">{modelRun.model_name} · {modelRun.status}</Typography>
              {['QUEUED', 'RUNNING', 'RETRY_PENDING'].includes(modelRun.status) && <LinearProgress variant="determinate" value={modelJobProgress} sx={{ mt: 0.5 }} />}
            </Box>
          )}
          <Stack direction="row" spacing={1} flexWrap="wrap" mb={2}>
            <Chip size="small" label={`${predictions.filter((item) => item.status === 'PENDING').length} pending`} sx={{ bgcolor: '#fef3c7' }} />
            <Chip size="small" label="Model" sx={{ color: '#15803d' }} />
            <Chip size="small" label="Corrected" sx={{ color: '#9333ea' }} />
            <Chip size="small" label="Propagated" sx={{ color: '#0f766e' }} />
          </Stack>
          {selectedPrediction && (
            <Box sx={{ p: 1.5, mb: 2, bgcolor: '#fff7ed', borderRadius: 1 }}>
              <Typography fontWeight={700}>{selectedPrediction.label} · {(selectedPrediction.confidence * 100).toFixed(1)}%</Typography>
              <Typography variant="caption" color="text.secondary">{selectedPrediction.model_name} · {selectedPrediction.model_version}</Typography>
              {(selectedPrediction.track_id || selectedPrediction.association_score != null) && (
                <Typography display="block" variant="caption" color="text.secondary">
                  {selectedPrediction.track_id ? `Track ${selectedPrediction.track_id}` : 'Untracked'}
                  {selectedPrediction.association_score == null ? '' : ` · board association ${selectedPrediction.association_score.toFixed(3)}`}
                  {selectedPrediction.association_ambiguous ? ' · ambiguous' : ''}
                </Typography>
              )}
              <Stack direction="row" spacing={0.5} mt={1}>
                <Button size="small" color="success" startIcon={<Check />} onClick={acceptPrediction}>Accept</Button>
                <Button size="small" startIcon={<Edit />} onClick={correctPrediction}>Correct</Button>
                <Button size="small" color="error" startIcon={<Close />} onClick={rejectPrediction}>Reject</Button>
              </Stack>
            </Box>
          )}
          {propagationPrediction?.track_id && propagationPrediction.annotation_type === 'bbox' && (
            <Box sx={{ p: 1.5, mb: 2, bgcolor: '#eff6ff', borderRadius: 1 }}>
              <Typography variant="subtitle2">Track propagation · #{propagationPrediction.track_id}</Typography>
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Applies this {selectedAnnotation ? 'corrected box' : 'prediction'} to matching track frames without overwriting unrelated human labels.
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Select
                  size="small"
                  value={propagationRadius}
                  onChange={(event) => setPropagationRadius(Number(event.target.value))}
                >
                  <MenuItem value={1}>±1 frame</MenuItem>
                  <MenuItem value={2}>±2 frames</MenuItem>
                  <MenuItem value={5}>±5 frames</MenuItem>
                </Select>
                <Button size="small" variant="contained" disabled={saving} onClick={propagateTrack}>
                  Propagate
                </Button>
              </Stack>
            </Box>
          )}
          {metrics && (
            <Box sx={{ p: 1.5, mb: 2, bgcolor: '#f8fafc', borderRadius: 1 }}>
              <Typography variant="subtitle2">Run metrics</Typography>
              <Typography variant="body2">Accepted {(metrics.acceptance_rate * 100).toFixed(0)}% · Corrected {(metrics.correction_rate * 100).toFixed(0)}% · Rejected {(metrics.rejection_rate * 100).toFixed(0)}%</Typography>
              <Typography variant="caption" color="text.secondary">{metrics.pending} pending · {metrics.average_decision_time_ms ? `${Math.round(metrics.average_decision_time_ms)}ms avg decision` : 'No timing yet'}</Typography>
            </Box>
          )}
          <Typography variant="h6" gutterBottom>Tools</Typography>
          <Stack direction="row" spacing={1} mb={2}>
            <Button fullWidth variant={tool === 'bbox' ? 'contained' : 'outlined'} startIcon={<CropFree />} onClick={() => setTool('bbox')}>Box</Button>
            <Button fullWidth variant={tool === 'keypoints' ? 'contained' : 'outlined'} startIcon={<ScatterPlot />} onClick={() => setTool('keypoints')}>Points</Button>
          </Stack>
          {tool === 'bbox' ? (
            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <Select value={label} onChange={(event) => setLabel(event.target.value)}>
                <MenuItem value="rider">Rider</MenuItem>
                <MenuItem value="snowboard">Snowboard</MenuItem>
                <MenuItem value="helmet">Helmet</MenuItem>
              </Select>
            </FormControl>
          ) : (
            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <Select value={keypointName} onChange={(event) => setKeypointName(event.target.value)}>
                {KEYPOINTS.map((name) => <MenuItem key={name} value={name}>{name.replace(/_/g, ' ')}</MenuItem>)}
              </Select>
            </FormControl>
          )}
          <Stack spacing={1}>
            <Button variant="contained" startIcon={<Save />} disabled={!dirty || saving} onClick={save}>{saving ? 'Saving…' : 'Save frame'}</Button>
            <Button color="error" startIcon={<Delete />} disabled={!selectedId} onClick={deleteSelected}>Delete selected</Button>
            <Button variant="outlined" color="success" disabled={task.status === 'COMPLETED'} onClick={completeTask}>Complete task</Button>
          </Stack>
          <Typography variant="body2" color="text.secondary" mt={2}>
            A accept · C correct · R reject · B/K tools · ←/→ frames · Shift+←/→ jump 10 · Delete removes · Ctrl/Cmd+S saves
          </Typography>
          <Typography variant="body2" mt={2}>{annotations.length} annotations {dirty && '· unsaved'}</Typography>
          {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        </Paper>
      </Stack>
    </Box>
  );
};

export default AnnotationWorkspace;
