import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMaterialFile, validateImageFile } from '../src/material-import.js';

const textFile = (name, value) => ({name, size: new TextEncoder().encode(value).byteLength, text: async () => value});

test('文字教材匯入保存格式與來源，去除 UTF-8 BOM', async () => {
  const result = await parseMaterialFile(textFile('第一章.md', '\uFEFF第一章：分數'));
  assert.equal(result.content, '第一章：分數');
  assert.deepEqual(result.source, {name: '第一章.md', type: 'text/markdown'});
});

test('圖片檔案須符合副檔名、內容簽章及尺寸限制', async () => {
  const file = (name, bytes, size = bytes.length) => ({name, size, slice: () => ({arrayBuffer: async () => Uint8Array.from(bytes).buffer})});
  assert.deepEqual(await validateImageFile(file('chapter.png', [137, 80, 78, 71, 13, 10, 26, 10])), {name: 'chapter.png', type: 'image/png'});
  assert.deepEqual(await validateImageFile(file('chapter.jpg', [255, 216, 255])), {name: 'chapter.jpg', type: 'image/jpeg'});
  await assert.rejects(() => validateImageFile(file('fake.png', [60, 115, 118, 103])), /格式與檔案內容不符/);
  await assert.rejects(() => validateImageFile(file('large.png', [137, 80, 78, 71, 13, 10, 26, 10], 9 * 1024 * 1024)), /8 MB/);
  await assert.rejects(() => validateImageFile(file('image.svg', [60, 115, 118, 103])), /僅支援/);
});

test('不支援的 DOC 與空白檔案不能假裝成功', async () => {
  await assert.rejects(() => parseMaterialFile(textFile('old.doc', 'something')), /DOCX/);
  await assert.rejects(() => parseMaterialFile(textFile('empty.txt', '')), /空白/);
  await assert.rejects(() => parseMaterialFile(textFile('blank.txt', ' ')), /未擷取到文字/);
});

test('DOCX 擷取器回傳內容與格式且掃描不到文字時拒絕', async () => {
  const previous = globalThis.mammoth;
  try {
    const file = {name: 'unit.docx', size: 10, arrayBuffer: async () => new ArrayBuffer(10)};
    globalThis.mammoth = {extractRawText: async () => ({value: '合成課文'})};
    assert.deepEqual(await parseMaterialFile(file), {
      content: '合成課文',
      source: {name: 'unit.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    });
    globalThis.mammoth = {extractRawText: async () => ({value: ''})};
    await assert.rejects(() => parseMaterialFile(file), /未擷取到文字/);
  } finally { globalThis.mammoth = previous; }
});
