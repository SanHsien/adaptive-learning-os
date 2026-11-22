import { MAX_MATERIAL_CHARS, validateMaterial } from './core.js';

const FORMATS = {
  txt: 'text/plain', md: 'text/markdown', markdown: 'text/markdown', csv: 'text/csv',
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
};

const IMAGE_TYPES = {png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp'};
const MEDIA_TYPES = {mp3: 'audio/mpeg', wav: 'audio/wav', m4a: 'audio/mp4', mp4: 'video/mp4', webm: 'video/webm'};

export async function validateMediaFile(file) {
  const extension = file?.name?.toLowerCase().split('.').pop();
  const type = MEDIA_TYPES[extension];
  if (!type) throw new Error('影音僅支援 MP3、WAV、M4A、MP4、WebM');
  if (!file.size || file.size > 100 * 1024 * 1024) throw new Error('影音檔案上限為 100 MB，空檔不可匯入');
  const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
  const ascii = (start, end) => String.fromCharCode(...bytes.slice(start, end));
  const valid = extension === 'mp3' ? ascii(0, 3) === 'ID3' || (bytes[0] === 255 && (bytes[1] & 224) === 224)
    : extension === 'wav' ? ascii(0, 4) === 'RIFF' && ascii(8, 12) === 'WAVE'
    : extension === 'm4a' || extension === 'mp4' ? ascii(4, 8) === 'ftyp'
    : bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3;
  if (!valid) throw new Error('影音格式與檔案內容不符');
  return {name: file.name.slice(0, 180), type};
}

export async function validateImageFile(file) {
  const extension = file?.name?.toLowerCase().split('.').pop();
  const type = IMAGE_TYPES[extension];
  if (!type) throw new Error('圖片僅支援 PNG、JPEG、WebP');
  if (!file.size || file.size > 8 * 1024 * 1024) throw new Error('圖片檔案上限為 8 MB，空檔不可匯入');
  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const valid = type === 'image/png'
    ? [137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value)
    : type === 'image/jpeg'
      ? bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255
      : String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP';
  if (!valid) throw new Error('圖片格式與檔案內容不符，請選擇有效圖片');
  return {name: file.name.slice(0, 180), type};
}

export async function parseMaterialFile(file) {
  if (!file || typeof file.name !== 'string') throw new Error('請選擇教材檔案');
  const extension = file.name.toLowerCase().split('.').pop();
  const type = FORMATS[extension];
  if (!type) throw new Error('支援 TXT、Markdown、CSV、PDF 或 DOCX；舊版 DOC 請先轉成 DOCX');
  if (!file.size || file.size > (['pdf', 'docx'].includes(extension) ? 8 : 1) * 1024 * 1024) {
    throw new Error('文字教材上限 1 MB，PDF／DOCX 上限 8 MB，空白檔案不可匯入');
  }
  let content;
  if (['txt', 'md', 'markdown', 'csv'].includes(extension)) {
    content = (await file.text()).replace(/^\uFEFF/, '');
  } else if (extension === 'pdf') {
    const pdfjs = await import('../vendor/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdf.worker.min.mjs', import.meta.url).href;
    const task = pdfjs.getDocument({data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false});
    let pdf;
    try {
      pdf = await task.promise;
      if (pdf.numPages > 100) throw new Error('PDF 超過 100 頁上限，請先拆分教材');
      const pages = [];
      let charCount = 0;
      for (let index = 1; index <= pdf.numPages; index++) {
        const page = await pdf.getPage(index);
        const lines = (await page.getTextContent()).items.map(item => item.str || '');
        const pageText = `【第 ${index} 頁】\n${lines.join(' ')}`;
        charCount += pageText.length;
        if (charCount > MAX_MATERIAL_CHARS) throw new Error('擷取文字超過十萬字元，請先拆分教材');
        pages.push(pageText);
      }
      content = pages.join('\n\n');
    } finally { await task.destroy(); }
  } else {
    if (!globalThis.mammoth?.extractRawText) throw new Error('Word 解析元件尚未載入');
    const result = await globalThis.mammoth.extractRawText({arrayBuffer: await file.arrayBuffer()});
    content = result.value;
  }
  if (!content.trim() || (extension === 'pdf' && !content.replace(/【第 \d+ 頁】/g, '').trim())) throw new Error('未擷取到文字；掃描型 PDF／圖片須先 OCR，原教材未變更');
  validateMaterial(content);
  return {content, source: {name: file.name.slice(0, 180), type}};
}
