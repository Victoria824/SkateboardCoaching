import { AnnotationDraft, ModelPrediction } from '../mediaApi';
import { bboxToMaskGeometry } from './maskState';


export function predictionToAnnotation(
  prediction: ModelPrediction,
  source: 'model' | 'model_corrected'
): AnnotationDraft {
  const piiMask = prediction.annotation_type === 'bbox'
    && ['face', 'license_plate', 'screen'].includes(prediction.label);
  return {
    label: prediction.label,
    annotation_type: piiMask ? 'mask' : prediction.annotation_type,
    geometry: piiMask ? bboxToMaskGeometry(prediction.geometry as any) : prediction.geometry,
    source,
    model_prediction_id: prediction.id,
  };
}


export function updatePredictionStatus(
  predictions: ModelPrediction[],
  predictionId: string,
  status: ModelPrediction['status']
): ModelPrediction[] {
  return predictions.map((prediction) => prediction.id === predictionId
    ? { ...prediction, status }
    : prediction);
}
