import { ModelPrediction } from '../mediaApi';
import { predictionToAnnotation, updatePredictionStatus } from './predictionState';


const prediction: ModelPrediction = {
  id: 'prediction-1',
  model_run_id: 'run-1',
  frame_id: 'frame-1',
  label: 'rider',
  confidence: 0.9,
  annotation_type: 'bbox',
  geometry: { x: 0.1, y: 0.2, width: 0.3, height: 0.5 },
  status: 'PENDING',
  model_name: 'detector',
  model_version: 'v1',
};


test('accepted prediction preserves provenance and original geometry', () => {
  const annotation = predictionToAnnotation(prediction, 'model');

  expect(annotation.source).toBe('model');
  expect(annotation.model_prediction_id).toBe(prediction.id);
  expect(annotation.geometry).toEqual(prediction.geometry);
});


test('correction state updates only the selected prediction', () => {
  const other = { ...prediction, id: 'prediction-2' };
  const updated = updatePredictionStatus([prediction, other], prediction.id, 'CORRECTED');

  expect(updated[0].status).toBe('CORRECTED');
  expect(updated[1].status).toBe('PENDING');
});

