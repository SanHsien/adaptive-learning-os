import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMaterialFile, validateImageFile, validateMediaFile } from '../src/material-import.js';

const textFile = (name, value) => ({name, size: new TextEncoder().encode(value).byteLength, text: async () => value});

test('文字教材匯入保存格式與來源，去除 UTF-8 BOM', async () => {
  const result = await parseMaterialFile(textFile('第一章.md', '\uFEFF第一章：分數'));
  assert.equal(result.content, '第一章：分數');
  assert.deepEqual(result.source, {name: '第一章.md', type: 'text/markdown'});
});

test('SRT 與 WebVTT 逐字稿解析與來源保留', async () => {
  const srt = '1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n2\n00:00:01,000 --> 00:00:02,000\n第二句';
  const vtt = 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n中文 <b>測試</b>';
  assert.deepEqual(await parseMaterialFile(textFile('講座.srt', srt)), {
    content: '第一句\n第二句', source: {name: '講座.srt', type: 'application/x-subrip'}
  });
  assert.equal((await parseMaterialFile(textFile('講座.vtt', vtt))).content, '中文 測試');
  await assert.rejects(() => parseMaterialFile(textFile('bad.vtt', '00:00:00.000 --> 00:00:01.000\n不合法')), /WEBVTT/);
  await assert.rejects(() => parseMaterialFile(textFile('bad.srt', '任意文字')), /時間碼/);
  await assert.rejects(() => parseMaterialFile(textFile('empty.srt', '1\n00:00:00,000 --> 00:00:01,000')), /時間碼/);
});

test('文字檔讀取中取消後不可交付教材', async () => {
  const controller = new AbortController();
  const file = {
    name: 'slow.txt', size: 10,
    text: async () => { controller.abort(); return '已取消的教材'; }
  };
  await assert.rejects(() => parseMaterialFile(file, controller.signal), {name: 'AbortError'});
});

test('DOCX 解碼中取消後不可交付教材', async () => {
  const previous = globalThis.mammoth;
  const controller = new AbortController();
  try {
    globalThis.mammoth = {extractRawText: async () => {
      controller.abort();
      return {value: '已取消的 Word 內容'};
    }};
    await assert.rejects(() => parseMaterialFile({
      name: 'slow.docx', size: 10, arrayBuffer: async () => new ArrayBuffer(10)
    }, controller.signal), {name: 'AbortError'});
  } finally { globalThis.mammoth = previous; }
});

test('圖片檔案須符合副檔名、內容簽章及尺寸限制', async () => {
  const file = (name, bytes, size = bytes.length) => ({name, size, slice: () => ({arrayBuffer: async () => Uint8Array.from(bytes).buffer})});
  assert.deepEqual(await validateImageFile(file('chapter.png', [137, 80, 78, 71, 13, 10, 26, 10])), {name: 'chapter.png', type: 'image/png'});
  assert.deepEqual(await validateImageFile(file('chapter.jpg', [255, 216, 255])), {name: 'chapter.jpg', type: 'image/jpeg'});
  await assert.rejects(() => validateImageFile(file('fake.png', [60, 115, 118, 103])), /格式與檔案內容不符/);
  await assert.rejects(() => validateImageFile(file('large.png', [137, 80, 78, 71, 13, 10, 26, 10], 9 * 1024 * 1024)), /8 MB/);
  await assert.rejects(() => validateImageFile(file('image.svg', [60, 115, 118, 103])), /僅支援/);
});

test('影音只接受受限格式、大小與實際檔頭', async () => {
  const file = (name, bytes, size = bytes.length) => ({name, size, slice: () => ({arrayBuffer: async () => Uint8Array.from(bytes).buffer})});
  assert.deepEqual(await validateMediaFile(file('lecture.mp3', [73, 68, 51, 4])), {name: 'lecture.mp3', type: 'audio/mpeg'});
  assert.deepEqual(await validateMediaFile(file('lecture.wav', [82,73,70,70,0,0,0,0,87,65,86,69])), {name: 'lecture.wav', type: 'audio/wav'});
  assert.deepEqual(await validateMediaFile(file('lecture.mp4', [0,0,0,24,102,116,121,112])), {name: 'lecture.mp4', type: 'video/mp4'});
  await assert.rejects(() => validateMediaFile(file('fake.mp4', [60,115,118,103])), /內容不符/);
  await assert.rejects(() => validateMediaFile(file('huge.mp3', [73,68,51], 101 * 1024 * 1024)), /100 MB/);
  await assert.rejects(() => validateMediaFile(file('danger.html', [73,68,51])), /僅支援/);
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


test('Malformed subtitle markup cannot leave literal angle brackets', async () => {
  const result = await parseMaterialFile(textFile('nested.srt', '1\n00:00:00,000 --> 00:00:01,000\n<<b>text</b>> <unfinished'));
  assert.equal(result.content, 'text unfinished');
  const samples = [
    ['<scr<script>ipt>payload</script>', 'scriptpayload'],
    ['before <b>bold</b> after', 'before bold after'],
    ['a > b < c', 'a  b  c'],
    ['<a<b>c', 'ac'],
    ['<unfinished', 'unfinished']
  ];
  for (const [input, expected] of samples) {
    const parsed = await parseMaterialFile(textFile('nested.srt', `1\n00:00:00,000 --> 00:00:01,000\n${input}`));
    assert.equal(parsed.content, expected);
    assert.doesNotMatch(parsed.content, /[<>]/);
  }
});

test('Preview extensions cannot resolve inherited properties', async () => {
  const file = {name: 'sample.constructor', size: 16, slice: () => ({arrayBuffer: async () => Uint8Array.from([26,69,223,163]).buffer})};
  await assert.rejects(() => validateImageFile(file));
  await assert.rejects(() => validateMediaFile(file));
});
