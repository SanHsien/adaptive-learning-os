import { MAX_MATERIAL_CHARS } from './core.js';

const MAX_PIXELS = 20_000_000;
const MAX_EDGE = 2200;

export function checkImageDimensions(width, height) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 ||
      width * height > MAX_PIXELS) throw new Error('OCR 圖片像素超出 2,000 萬上限');
  return Math.min(1, MAX_EDGE / Math.max(width, height));
}

async function downsample(file) {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = checkImageDimensions(bitmap.width, bitmap.height);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext('2d', {alpha: false});
    if (!ctx) throw new Error('無法初始化本機 OCR 畫布');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('圖片預處理失敗')), 'image/png'));
  } finally { bitmap.close(); }
}

export async function recognizeImage(file, signal) {
  signal?.throwIfAborted();
  const processed = await downsample(file);
  signal?.throwIfAborted();
  const createWorker = globalThis.Tesseract?.createWorker;
  if (typeof createWorker !== 'function') throw new Error('本機 OCR 引擎未載入');
  const base = new URL('../vendor/ocr/', import.meta.url);
  const worker = await createWorker('chi_tra', 1, {
    workerPath: new URL('worker.min.js', base).href,
    corePath: new URL('core/', base).href,
    langPath: base.href.replace(/\/$/, ''),
    workerBlobURL: false
  });
  // Cancellation during worker initialization must still dispose the worker.
  let terminationPromise;
  const terminate = () => {
    if (!terminationPromise) {
      terminationPromise = Promise.resolve().then(() => worker.terminate());
    }
    return terminationPromise;
  };
  const onAbort = () => { void terminate().catch(() => {}); };
  signal?.addEventListener('abort', onAbort, {once: true});
  try {
    signal?.throwIfAborted();
    const result = await worker.recognize(processed);
    signal?.throwIfAborted();
    const content = String(result.data?.text || '').trim();
    if (!content) throw new Error('OCR 未辨識到文字，原教材未變更；請改用人工輸入');
    if (content.length > MAX_MATERIAL_CHARS) throw new Error('OCR 內容超過十萬字元上限');
    return content;
  } catch (error) {
    signal?.throwIfAborted();
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
    await terminate();
  }
}
