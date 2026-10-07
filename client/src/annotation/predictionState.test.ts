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


test('PII boxes become editable conservative masks with provenance', () => {
  const piiPrediction = { ...prediction, label: 'face' };
  const annotation = predictionToAnnotation(piiPrediction, 'model');

  expect(annotation.annotation_type).toBe('mask');
  expect(annotation.geometry.encoding).toBe('row-major-rle-v1');
  expect(annotation.geometry.rle.reduce((sum: number, count: number) => sum + count, 0)).toBe(128 * 128);
  expect(annotation.geometry.bbox).toEqual(piiPrediction.geometry);
  expect(annotation.model_prediction_id).toBe(piiPrediction.id);
});
