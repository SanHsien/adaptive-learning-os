import test from 'node:test';
import assert from 'node:assert/strict';
import {checkImageDimensions, recognizeImage} from '../src/ocr.js';

test('OCR 僅接受可控的影像大小並縮至 2200 邊長', () => {
  assert.equal(checkImageDimensions(1000, 1000), 1);
  assert.equal(checkImageDimensions(4400, 2200), 0.5);
  assert.throws(() => checkImageDimensions(5000, 5000), /2,000 萬/);
  assert.throws(() => checkImageDimensions(0, 1), /2,000 萬/);
  assert.throws(() => checkImageDimensions(NaN, 2), /2,000 萬/);
});

test('OCR 取消時會停止 Worker，且不可回傳已取消結果', async () => {
  const previous = {
    createImageBitmap: globalThis.createImageBitmap,
    document: globalThis.document,
    Tesseract: globalThis.Tesseract
  };
  let started;
  const startedPromise = new Promise(resolve => { started = resolve; });
  let failRecognize;
  let terminated = 0;
  globalThis.createImageBitmap = async () => ({width: 100, height: 100, close() {}});
  globalThis.document = {
    createElement: () => ({
      width: 0, height: 0,
      getContext: () => ({fillRect() {}, drawImage() {}}),
      toBlob: callback => callback(new Blob(['image']))
    })
  };
  globalThis.Tesseract = {
    createWorker: async () => ({
      recognize: () => { started(); return new Promise((_, reject) => { failRecognize = reject; }); },
      terminate: async () => { terminated++; failRecognize?.(new Error('worker stopped')); }
    })
  };
  try {
    const controller = new AbortController();
    const promise = recognizeImage(new Blob(['image']), controller.signal);
    await startedPromise;
    controller.abort();
    await assert.rejects(promise, {name: 'AbortError'});
    assert.equal(terminated, 1);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
});

test('Worker 尚在初始化時取消，初始化完成後仍應終止且不執行辨識', async () => {
  const previous = {
    createImageBitmap: globalThis.createImageBitmap,
    document: globalThis.document,
    Tesseract: globalThis.Tesseract
  };
  let finishInitialization;
  let initializationStarted;
  const started = new Promise(resolve => { initializationStarted = resolve; });
  let recognized = 0;
  let terminated = 0;
  globalThis.createImageBitmap = async () => ({width: 10, height: 10, close() {}});
  globalThis.document = {createElement: () => ({getContext: () => ({fillRect() {}, drawImage() {}}), toBlob: cb => cb(new Blob(['image']))})};
  globalThis.Tesseract = {createWorker: () => {
    initializationStarted();
    return new Promise(resolve => { finishInitialization = () => resolve({
      recognize: async () => { recognized++; return {data: {text: '不應出現'}}; },
      terminate: async () => { terminated++; }
    }); });
  }};
  try {
    const controller = new AbortController();
    const result = recognizeImage(new Blob(['image']), controller.signal);
    await started;
    controller.abort();
    finishInitialization();
    await assert.rejects(result, {name: 'AbortError'});
    assert.equal(recognized, 0);
    assert.equal(terminated, 1);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
});

test('取消後等待同一個 Worker 終止 Promise 完成才結束', async () => {
  const previous = {
    createImageBitmap: globalThis.createImageBitmap,
    document: globalThis.document,
    Tesseract: globalThis.Tesseract
  };
  let recognizeStarted;
  const started = new Promise(resolve => { recognizeStarted = resolve; });
  let rejectRecognition;
  let finishTermination;
  let terminations = 0;
  globalThis.createImageBitmap = async () => ({width: 10, height: 10, close() {}});
  globalThis.document = {createElement: () => ({getContext: () => ({fillRect() {}, drawImage() {}}), toBlob: cb => cb(new Blob(['image']))})};
  globalThis.Tesseract = {createWorker: async () => ({
    recognize: () => { recognizeStarted(); return new Promise((_, reject) => { rejectRecognition = reject; }); },
    terminate: () => { terminations++; rejectRecognition(new Error('stopped')); return new Promise(resolve => { finishTermination = resolve; }); }
  })};
  try {
    const controller = new AbortController();
    const operation = recognizeImage(new Blob(['image']), controller.signal);
    await started;
    controller.abort();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(terminations, 1);
    let settled = false;
    void operation.finally(() => { settled = true; }).catch(() => {});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(settled, false);
    finishTermination();
    await assert.rejects(operation, {name: 'AbortError'});
    assert.equal(terminations, 1);
    assert.equal(settled, true);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
});
