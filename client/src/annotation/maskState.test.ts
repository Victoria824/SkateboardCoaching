import { bboxToMaskGeometry, decodeMask, paintMaskStroke } from './maskState';


test('mask brush paints and erases individual raster cells', () => {
  const geometry = bboxToMaskGeometry({ x: 0.4, y: 0.4, width: 0.2, height: 0.2 }, 32, 32, 0);
  const before = decodeMask(geometry).reduce((sum, value) => sum + value, 0);
  const painted = paintMaskStroke(geometry, { x: 0.1, y: 0.1 }, { x: 0.2, y: 0.1 }, 0.03, true);
  const afterPaint = decodeMask(painted).reduce((sum, value) => sum + value, 0);
  const erased = paintMaskStroke(painted, { x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }, 0.04, false);
  const afterErase = decodeMask(erased).reduce((sum, value) => sum + value, 0);

  expect(afterPaint).toBeGreaterThan(before);
  expect(afterErase).toBeLessThan(afterPaint);
  expect(erased.edit_count).toBe(2);
  expect(erased.last_edit).toBe('erase');
});
