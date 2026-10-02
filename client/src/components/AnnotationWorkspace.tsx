import React, { PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import {
  ArrowBack,
  ArrowForward,
  CropFree,
  Delete,
  Save,
  ScatterPlot,
} from '@mui/icons-material';

import {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTask,
  completeAnnotationTask,
  getAnnotationTask,
  getFrameAnnotations,
  mediaUrl,
  saveFrameAnnotations,
} from '../mediaApi';

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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>('bbox');
  const [label, setLabel] = useState('rider');
  const [keypointName, setKeypointName] = useState(KEYPOINTS[0]);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [draftBox, setDraftBox] = useState<BBox | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const frameStartedAt = useRef(Date.now());

  const frames = task?.video?.frames || [];
  const frame = frames[frameIndex];

  useEffect(() => {
    getAnnotationTask(taskId)
      .then(setTask)
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : 'Unable to load task.'));
  }, [taskId]);

  useEffect(() => {
    if (!frame) return;
    setError(null);
    setMessage(null);
    setSelectedId(null);
    frameStartedAt.current = Date.now();
    getFrameAnnotations(taskId, frame.id)
      .then((records) => {
        setAnnotations(records.map((record: AnnotationRecord) => ({
          id: record.id,
          label: record.label,
          annotation_type: record.annotation_type,
          geometry: record.geometry,
          source: record.source,
          model_prediction_id: record.model_prediction_id,
        })));
        setDirty(false);
      })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : 'Unable to load annotations.'));
  }, [frame, taskId]);

  const normalizedPoint = (event: ReactPointerEvent<SVGSVGElement | SVGElement>) => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds) return { x: 0, y: 0 };
    return {
      x: clamp((event.clientX - bounds.left) / bounds.width),
      y: clamp((event.clientY - bounds.top) / bounds.height),
    };
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
      })));
      setDirty(false);
      setMessage(`Saved ${saved.length} annotations`);
      return true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Save failed.');
      return false;
    } finally {
      setSaving(false);
    }
  }, [annotations, frame, saving, taskId]);

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
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        deleteSelected();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [deleteSelected, navigate, save]);

  if (error && !task) return <Alert severity="error">{error}</Alert>;
  if (!task || !frame) return <Box p={8} textAlign="center"><CircularProgress /></Box>;

  return (
    <Box minHeight="100vh" bgcolor="#111827" color="white" p={{ xs: 1, md: 2 }}>
      <Paper sx={{ p: 1.5, mb: 2, bgcolor: '#1f2937', color: 'white' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
          <Button href="/" color="inherit" startIcon={<ArrowBack />}>Coach</Button>
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
              {annotations.map((annotation) => annotation.annotation_type === 'bbox' ? (() => {
                const box = annotation.geometry as BBox;
                const selected = selectedId === annotation.id;
                return <g key={annotation.id}>
                  <rect
                    x={box.x * 1000} y={box.y * 1000} width={box.width * 1000} height={box.height * 1000}
                    fill="rgba(14,165,233,.12)" stroke={selected ? '#facc15' : '#0ea5e9'} strokeWidth={selected ? 6 : 4}
                    vectorEffect="non-scaling-stroke"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      const point = normalizedPoint(event);
                      setSelectedId(annotation.id);
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
                    onPointerDown={(event) => { event.stopPropagation(); setSelectedId(annotation.id); setOperation({ kind: 'point', id: annotation.id, name: point.name }); }}
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
            B/K tools · ←/→ frames · Shift+←/→ jump 10 · Delete removes · Ctrl/Cmd+S saves
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
