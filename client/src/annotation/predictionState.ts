import { AnnotationDraft, ModelPrediction } from '../mediaApi';


export function predictionToAnnotation(
  prediction: ModelPrediction,
  source: 'model' | 'model_corrected'
): AnnotationDraft {
  return {
    label: prediction.label,
    annotation_type: prediction.annotation_type,
    geometry: prediction.geometry,
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

