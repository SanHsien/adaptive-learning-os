import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMaterialFile } from '../src/material-import.js';

const textFile = (name, value) => ({name, size: new TextEncoder().encode(value).byteLength, text: async () => value});

test('文字教材匯入保存格式與來源，去除 UTF-8 BOM', async () => {
  const result = await parseMaterialFile(textFile('第一章.md', '\uFEFF第一章：分數'));
  assert.equal(result.content, '第一章：分數');
  assert.deepEqual(result.source, {name: '第一章.md', type: 'text/markdown'});
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
