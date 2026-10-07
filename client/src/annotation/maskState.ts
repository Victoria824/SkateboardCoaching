export type BBox = { x: number; y: number; width: number; height: number };

export type MaskGeometry = {
  encoding: 'row-major-rle-v1';
  width: number;
  height: number;
  rle: number[];
  bbox: BBox;
  edit_count: number;
  last_edit: 'proposal' | 'paint' | 'erase';
};

export const decodeMask = (geometry: MaskGeometry): number[] => {
  const pixels: number[] = [];
  let value = 0;
  geometry.rle.forEach((count) => {
    for (let index = 0; index < count; index += 1) pixels.push(value);
    value = 1 - value;
  });
  if (pixels.length !== geometry.width * geometry.height) {
    throw new Error('Mask RLE dimensions do not match');
  }
  return pixels;
};

export const encodeMask = (pixels: number[]): number[] => {
  const counts: number[] = [];
  let expected = 0;
  let count = 0;
  pixels.forEach((pixel) => {
    const value = pixel ? 1 : 0;
    if (value === expected) {
      count += 1;
    } else {
      counts.push(count);
      count = 1;
      expected = value;
    }
  });
  counts.push(count);
  return counts;
};

export const bboxToMaskGeometry = (
  box: BBox,
  width = 128,
  height = 128,
  padding = 0.015
): MaskGeometry => {
  const pixels = new Array(width * height).fill(0);
  const x1 = Math.max(0, Math.floor((box.x - padding) * width));
  const y1 = Math.max(0, Math.floor((box.y - padding) * height));
  const x2 = Math.min(width, Math.ceil((box.x + box.width + padding) * width));
  const y2 = Math.min(height, Math.ceil((box.y + box.height + padding) * height));
  for (let row = y1; row < y2; row += 1) {
    for (let column = x1; column < x2; column += 1) pixels[row * width + column] = 1;
  }
  return {
    encoding: 'row-major-rle-v1',
    width,
    height,
    rle: encodeMask(pixels),
    bbox: box,
    edit_count: 0,
    last_edit: 'proposal',
  };
};

export const paintMaskStroke = (
  geometry: MaskGeometry,
  start: { x: number; y: number },
  end: { x: number; y: number },
  radius: number,
  enabled: boolean
): MaskGeometry => {
  const pixels = decodeMask(geometry);
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  const steps = Math.max(1, Math.ceil(distance / Math.max(0.002, radius / 2)));
  const radiusX = Math.max(1, Math.ceil(radius * geometry.width));
  const radiusY = Math.max(1, Math.ceil(radius * geometry.height));
  for (let step = 0; step <= steps; step += 1) {
    const x = start.x + (end.x - start.x) * (step / steps);
    const y = start.y + (end.y - start.y) * (step / steps);
    const centerX = Math.round(x * (geometry.width - 1));
    const centerY = Math.round(y * (geometry.height - 1));
    for (let row = Math.max(0, centerY - radiusY); row <= Math.min(geometry.height - 1, centerY + radiusY); row += 1) {
      for (let column = Math.max(0, centerX - radiusX); column <= Math.min(geometry.width - 1, centerX + radiusX); column += 1) {
        const dx = (column - centerX) / radiusX;
        const dy = (row - centerY) / radiusY;
        if (dx * dx + dy * dy <= 1) pixels[row * geometry.width + column] = enabled ? 1 : 0;
      }
    }
  }
  return {
    ...geometry,
    rle: encodeMask(pixels),
    edit_count: (geometry.edit_count || 0) + 1,
    last_edit: enabled ? 'paint' : 'erase',
  };
};

export const maskRuns = (geometry: MaskGeometry) => {
  const pixels = decodeMask(geometry);
  const runs: Array<{ x: number; y: number; width: number; height: number }> = [];
  for (let row = 0; row < geometry.height; row += 1) {
    let column = 0;
    while (column < geometry.width) {
      while (column < geometry.width && !pixels[row * geometry.width + column]) column += 1;
      const start = column;
      while (column < geometry.width && pixels[row * geometry.width + column]) column += 1;
      if (start < column) runs.push({
        x: start / geometry.width,
        y: row / geometry.height,
        width: (column - start) / geometry.width,
        height: 1 / geometry.height,
      });
    }
  }
  return runs;
};
