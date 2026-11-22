import test from 'node:test';
import assert from 'node:assert/strict';
import {checkImageDimensions} from '../src/ocr.js';

test('OCR 僅接受可控的影像大小並縮至 2200 邊長', () => {
  assert.equal(checkImageDimensions(1000, 1000), 1);
  assert.equal(checkImageDimensions(4400, 2200), 0.5);
  assert.throws(() => checkImageDimensions(5000, 5000), /2,000 萬/);
  assert.throws(() => checkImageDimensions(0, 1), /2,000 萬/);
  assert.throws(() => checkImageDimensions(NaN, 2), /2,000 萬/);
});
