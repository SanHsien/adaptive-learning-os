import { normalizeName, reviewDue, evidenceLevel, tutorPrompt } from './core.js';
import { listLearners, listSubjects, getLearner, getSubject, addLearner, addSubject, saveMaterial, listMaterialVersions, listAttempts, addAttempt, exportScope, importIsolated } from './storage.js';
import { parseMaterialFile, validateImageFile, validateMediaFile } from './material-import.js';

const $ = id => document.getElementById(id);
let learnerId = '';
let subjectId = '';
let snapshot = [];
let pendingMaterialSource = null;
let importGeneration = 0;
let imagePreviewUrl = null;
let mediaPreviewUrl = null;

function clearImagePreview() {
  if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
  imagePreviewUrl = null;
  $('imagePreview').removeAttribute('src');
  $('imagePanel').hidden = true;
}

function clearMediaPreview() {
  if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl);
  mediaPreviewUrl = null;
  $('mediaPreview').pause();
  $('mediaPreview').removeAttribute('src');
  $('mediaPreview').load();
  $('mediaPanel').hidden = true;
}

function notify(message, isError = false) {
  $('message').textContent = message;
  $('message').style.color = isError ? '#a43f2d' : '#286747';
}

async function safe(action) {
  try { await action(); } catch (err) { notify(err?.message || '操作失敗', true); }
}

function setOptions(select, items, placeholder) {
  select.replaceChildren();
  select.add(new Option(placeholder, ''));
  for (const item of items) select.add(new Option(item.name, item.id));
}

async function refreshLearners(selectId = learnerId) {
  const learners = await listLearners();
  setOptions($('learner'), learners, '請選擇學習者');
  $('learner').value = learners.some(l => l.id === selectId) ? selectId : '';
  learnerId = $('learner').value;
  await refreshSubjects();
}

async function refreshSubjects(selectId = subjectId) {
  const available = Boolean(learnerId);
  $('subject').disabled = !available;
  $('subjectName').disabled = !available;
  $('addSubject').querySelector('button').disabled = !available;
  const subjects = available ? await listSubjects(learnerId) : [];
  setOptions($('subject'), subjects, available ? '請選擇科目' : '請先選擇學習者');
  $('subject').value = subjects.some(s => s.id === selectId) ? selectId : '';
  subjectId = $('subject').value;
  await refreshWorkspace();
}

async function refreshWorkspace() {
  importGeneration++;
  clearImagePreview();
  clearMediaPreview();
  // The active pair is always captured before asynchronous reads.
  const requestedLearner = learnerId;
  const requestedSubject = subjectId;
  $('workspace').hidden = !requestedLearner || !requestedSubject;
  snapshot = [];
  pendingMaterialSource = null;
  $('materialFile').value = '';
  $('materialOrigin').textContent = '';
  if ($('workspace').hidden) return;
  const [learner, subject, attempts, versions] = await Promise.all([
    getLearner(requestedLearner), getSubject(requestedSubject), listAttempts(requestedLearner, requestedSubject), listMaterialVersions(requestedLearner, requestedSubject)
  ]);
  if (requestedLearner !== learnerId || requestedSubject !== subjectId) return;
  if (!learner || !subject || subject.learnerId !== learner.id) throw new Error('學習空間驗證失敗');
  snapshot = attempts;
  $('contextTitle').textContent = `${learner.name} / ${subject.name}`;
  $('material').value = subject.material || '';
  $('materialOrigin').textContent = subject.materialSource ? `來源：${subject.materialSource.name} · 版本 ${subject.materialVersion || 0}` : `手動教材 · 版本 ${subject.materialVersion || 0}`;
  const history = $('materialVersions');
  history.replaceChildren();
  for (const entry of versions.slice().reverse()) {
    const option = new Option(`v${entry.version} · ${new Date(entry.createdAt).toLocaleString('zh-TW')} · ${entry.source?.name || '手動教材'}`, String(entry.version));
    history.add(option);
  }
  history.selectedIndex = 0;
  $('total').textContent = attempts.length;
  $('mastery').textContent = evidenceLevel(attempts);
  $('due').textContent = attempts.filter(a => a.reviewDue && new Date(a.reviewDue) <= new Date()).length;
  const attemptHistory = $('history');
  attemptHistory.replaceChildren();
  if (!attempts.length) {
    const li = document.createElement('li'); li.className = 'muted'; li.textContent = '尚無作答紀錄。'; attemptHistory.append(li);
  }
  for (const a of [...attempts].reverse().slice(0, 30)) {
    const li = document.createElement('li');
    const label = document.createElement('strong');
    label.textContent = `${a.result === 'correct' ? '答對' : '需補強'} · ${a.question}`;
    const small = document.createElement('small');
    small.textContent = `${a.kind === 'transfer' ? '變形應用' : '獨立回憶'} · 教材 v${a.materialVersion ?? '?'} · 提示 ${a.hints} 次 · ${new Date(a.createdAt).toLocaleDateString('zh-TW')}${a.reviewDue ? ' · 下次複習 ' + new Date(a.reviewDue).toLocaleDateString('zh-TW') : ''}`;
    li.append(label, small); attemptHistory.append(li);
  }
}

function download(filename, content) {
  const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

$('addLearner').addEventListener('submit', event => { event.preventDefault(); safe(async () => {
  const learner = await addLearner(normalizeName($('learnerName').value, '學習者名稱'));
  $('learnerName').value = '';
  subjectId = '';
  await refreshLearners(learner.id);
  notify('已新增獨立的學習者空間。');
}); });

$('learner').addEventListener('change', () => safe(async () => {
  learnerId = $('learner').value;
  subjectId = '';
  await refreshSubjects('');
}));

$('addSubject').addEventListener('submit', event => { event.preventDefault(); safe(async () => {
  const activeLearner = learnerId;
  if (!activeLearner) throw new Error('請先選擇學習者');
  const subject = await addSubject(activeLearner, normalizeName($('subjectName').value, '科目名稱'));
  $('subjectName').value = '';
  if (activeLearner === learnerId) await refreshSubjects(subject.id);
  notify('已新增獨立科目。');
}); });

$('subject').addEventListener('change', () => safe(async () => {
  subjectId = $('subject').value;
  await refreshWorkspace();
}));

$('materialForm').addEventListener('submit', event => { event.preventDefault(); safe(async () => {
  const owner = learnerId, course = subjectId;
  if (pendingMaterialSource && /^(audio|video)\//.test(pendingMaterialSource.type) && !$('material').value.trim()) throw new Error('影音尚無逐字稿，請先輸入內容再儲存');
  await saveMaterial(owner, course, $('material').value, pendingMaterialSource);
  if (owner === learnerId && course === subjectId) { pendingMaterialSource = null; await refreshWorkspace(); notify('這個科目的教材已儲存。'); }
}); });

$('materialFile').addEventListener('change', event => safe(async () => {
  const file = event.target.files?.[0];
  if (!file) return;
  const owner = learnerId, course = subjectId;
  const generation = ++importGeneration;
  if (/\.(png|jpe?g|webp)$/i.test(file.name)) {
    const source = await validateImageFile(file);
    if (owner !== learnerId || course !== subjectId || generation !== importGeneration) throw new Error('教材選擇已變更，請重新選擇圖片');
    clearImagePreview();
    imagePreviewUrl = URL.createObjectURL(file);
    $('imagePreview').src = imagePreviewUrl;
    $('imagePanel').hidden = false;
    pendingMaterialSource = source;
    $('material').value = '';
    $('materialOrigin').textContent = `圖片來源：${source.name}（請人工辨識並輸入文字，再按儲存教材）`;
    notify('圖片只供本次預覽，尚未執行 OCR；請在教材欄輸入內容，確認後儲存。');
    return;
  }
  if (/\.(mp3|wav|m4a|mp4|webm)$/i.test(file.name)) {
    const source = await validateMediaFile(file);
    if (owner !== learnerId || course !== subjectId || generation !== importGeneration) throw new Error('學習空間已切換，請重新選擇影音');
    clearImagePreview();
    clearMediaPreview();
    mediaPreviewUrl = URL.createObjectURL(file);
    $('mediaPreview').src = mediaPreviewUrl;
    $('mediaPreview').setAttribute('aria-label', source.name);
    $('mediaPanel').hidden = false;
    pendingMaterialSource = source;
    $('material').value = '';
    $('materialOrigin').textContent = `影音來源：${source.name}（尚無逐字稿；可手動輸入或另行匯入文字逐字稿）`;
    notify('影音檔案僅暫時播放，不會保存。請輸入逐字稿並確認儲存；尚未進行自動語音辨識。');
    return;
  }
  const {content, source} = await parseMaterialFile(file);
  if (owner !== learnerId || course !== subjectId || generation !== importGeneration) throw new Error('教材選擇已變更，請重新選擇檔案');
  pendingMaterialSource = source;
  clearImagePreview();
  clearMediaPreview();
  $('material').value = content;
  $('materialOrigin').textContent = `待確認檔案：${file.name}（按「儲存教材」才會覆蓋目前教材）`;
  notify('檔案內容已載入預覽；確認後請按儲存教材。');
}));

$('material').addEventListener('input', () => {
  if (pendingMaterialSource && !pendingMaterialSource.type.startsWith('image/')) { pendingMaterialSource = null; $('materialOrigin').textContent = '已編輯檔案內容，將以手動教材儲存。'; }
});

$('viewMaterialVersion').addEventListener('click', () => safe(async () => {
  const owner = learnerId, course = subjectId;
  const selected = Number($('materialVersions').value);
  const versions = await listMaterialVersions(owner, course);
  if (owner !== learnerId || course !== subjectId) throw new Error('學習空間已切換');
  const entry = versions.find(item => item.version === selected);
  if (!entry) throw new Error('找不到指定教材版本');
  $('material').value = entry.content;
  pendingMaterialSource = null;
  $('materialOrigin').textContent = `正在預覽舊版 v${selected}（按儲存會產生新版本，並不覆寫歷程）`;
  notify(`已載入 v${selected} 文字供查閱；只有按儲存才會產生新版本。`);
}));

$('attemptForm').addEventListener('submit', event => { event.preventDefault(); safe(async () => {
  const owner = learnerId, course = subjectId;
  const result = event.submitter?.value;
  if (!['correct', 'incorrect'].includes(result)) throw new Error('請選擇答題結果');
  const question = $('question').value.trim(), answer = $('answer').value.trim();
  const hints = Number($('hints').value), kind = $('kind').value;
  if (!question || !answer || !Number.isInteger(hints) || hints < 0 || hints > 99 || !['recall','transfer'].includes(kind)) throw new Error('請填寫有效的練習資料');
  const prior = (await listAttempts(owner, course)).filter(a => a.result === 'correct' && a.hints === 0);
  const reviewLevel = result === 'incorrect' ? 0 : Math.min(prior.length, 3);
  await addAttempt(owner, course, { question, answer, kind, hints, result, reviewDue: reviewDue(reviewLevel) });
  if (owner === learnerId && course === subjectId) {
    $('attemptForm').reset(); await refreshWorkspace(); notify('已儲存作答與複習日期。');
  }
}); });

$('copyPrompt').addEventListener('click', () => safe(async () => {
  const owner = learnerId, course = subjectId;
  const [learner, subject, attempts] = await Promise.all([getLearner(owner),getSubject(course),listAttempts(owner,course)]);
  if (owner !== learnerId || course !== subjectId) throw new Error('學習空間已切換，請重試');
  await navigator.clipboard.writeText(tutorPrompt(learner, subject, attempts));
  notify('已複製此學習者與科目的專屬教學指令。');
}));

$('export').addEventListener('click', () => safe(async () => {
  const backup = await exportScope(learnerId, subjectId);
  download(`learning-${new Date().toISOString().slice(0,10)}.json`, JSON.stringify(backup, null, 2));
  notify('已匯出目前科目資料，請妥善保存備份。');
}));

$('importFile').addEventListener('change', event => safe(async () => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    if (file.size > 4 * 1024 * 1024) throw new Error('備份檔案上限為 4 MB');
    const backup = JSON.parse(await file.text());
    const { learner, subject } = await importIsolated(backup);
    subjectId = subject.id;
    await refreshLearners(learner.id);
    notify('匯入成功：已建立全新學習者與科目，原紀錄不受影響。');
  } finally { event.target.value = ''; }
}));

safe(() => refreshLearners(''));
