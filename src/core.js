export const REVIEW_INTERVALS = [1, 3, 7, 14];
export const MAX_MATERIAL_CHARS = 100000;
export const MAX_ATTEMPT_CHARS = 10000;

export function validateMaterial(value) {
  if (typeof value !== 'string' || value.length > MAX_MATERIAL_CHARS) throw new Error('教材必須是十萬字元以內的文字');
  return value;
}

export function validateAttempt(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      typeof value.question !== 'string' || !value.question.trim() || value.question.length > MAX_ATTEMPT_CHARS ||
      typeof value.answer !== 'string' || !value.answer.trim() || value.answer.length > MAX_ATTEMPT_CHARS ||
      !['correct', 'incorrect'].includes(value.result) || !['recall', 'transfer'].includes(value.kind) ||
      !Number.isInteger(value.hints) || value.hints < 0 || value.hints > 99) {
    throw new Error('作答紀錄內容或長度無效');
  }
  for (const key of ['createdAt', 'reviewDue']) {
    if (value[key] !== undefined && value[key] !== null &&
        (typeof value[key] !== 'string' || !Number.isFinite(Date.parse(value[key])) || value[key].length > 40)) {
      throw new Error(`${key} 日期格式無效`);
    }
  }
  return {
    question: value.question, answer: value.answer, result: value.result,
    kind: value.kind, hints: value.hints,
    reviewDue: value.reviewDue ?? null
  };
}

export function normalizeName(name, label = '名稱') {
  const value = String(name ?? '').trim();
  if (!value || value.length > 70) throw new Error(`${label}必須為 1–70 個字元`);
  return value;
}

export function newId() {
  return crypto.randomUUID();
}

export function scopedKey(learnerId, subjectId) {
  if (!learnerId || !subjectId || /[:]/.test(learnerId) || /[:]/.test(subjectId)) {
    throw new Error('學習者或科目識別碼無效');
  }
  return `${learnerId}:${subjectId}`;
}

export function ensureOwner(subject, learnerId) {
  if (!subject || subject.learnerId !== learnerId) throw new Error('科目不屬於目前學習者');
}

export function reviewDue(level, from = new Date()) {
  const days = REVIEW_INTERVALS[Math.min(Math.max(0, level), REVIEW_INTERVALS.length - 1)];
  const day = new Date(from);
  day.setDate(day.getDate() + days);
  return day.toISOString();
}

export function evidenceLevel(attempts) {
  const independent = attempts.filter(a => a.result === 'correct' && Number(a.hints) === 0);
  const transfer = independent.some(a => a.kind === 'transfer');
  if (transfer) return '遷移應用';
  if (independent.length) return '獨立回憶';
  if (attempts.some(a => a.result === 'correct')) return '提示後答對';
  return '待驗證';
}

export function validateBackup(value) {
  if (!value || value.schema !== 'adaptive-learning-os/v1' || !value.learner || !value.subject || !Array.isArray(value.attempts)) {
    throw new Error('備份格式不符');
  }
  const learnerName = normalizeName(value.learner.name, '學習者名稱');
  const subjectName = normalizeName(value.subject.name, '科目名稱');
  validateMaterial(value.subject.material ?? '');
  if (value.subject.materialVersion !== undefined && (!Number.isInteger(value.subject.materialVersion) || value.subject.materialVersion < 0 || value.subject.materialVersion > 1000000)) throw new Error('教材版本無效');
  if (value.subject.materialSource != null) {
    const source = value.subject.materialSource;
    if (typeof source !== 'object' || typeof source.name !== 'string' || !source.name.trim() || source.name.length > 180 || !['text/plain', 'text/markdown', 'text/csv', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/webp', 'audio/mpeg', 'audio/wav', 'audio/mp4', 'video/mp4', 'video/webm'].includes(source.type)) throw new Error('教材來源無效');
  }
  if (value.attempts.length > 10000) throw new Error('單次匯入紀錄不可超過 10,000 筆');
  if (value.materialVersions !== undefined) {
    if (!Array.isArray(value.materialVersions) || value.materialVersions.length > 1000) throw new Error('教材版本歷程無效');
    const versions = new Set();
    for (const entry of value.materialVersions) {
      if (!entry || !Number.isInteger(entry.version) || entry.version < 1 || entry.version > 1000000 || versions.has(entry.version) ||
          typeof entry.content !== 'string' || entry.content.length > MAX_MATERIAL_CHARS ||
          entry.parserStatus !== 'confirmed' ||
          (entry.contentHash !== null && (typeof entry.contentHash !== 'string' || !/^[a-f0-9]{64}$/.test(entry.contentHash))) ||
          typeof entry.createdAt !== 'string' || !Number.isFinite(Date.parse(entry.createdAt)) || entry.createdAt.length > 40 ||
          (entry.source != null && (typeof entry.source !== 'object' || typeof entry.source.name !== 'string' || !entry.source.name.trim() || entry.source.name.length > 180 || !['text/plain', 'text/markdown', 'text/csv', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/webp', 'audio/mpeg', 'audio/wav', 'audio/mp4', 'video/mp4', 'video/webm'].includes(entry.source.type)))) throw new Error('教材版本歷程無效');
      versions.add(entry.version);
    }
    if ((value.subject.materialVersion || 0) > 0 && !versions.has(value.subject.materialVersion)) throw new Error('教材最新版本不存在');
  }
  for (const a of value.attempts) {
    validateAttempt(a);
    if (a.materialVersion !== undefined && (!Number.isInteger(a.materialVersion) || a.materialVersion < 0 || a.materialVersion > 1000000)) throw new Error('作答教材版本無效');
  }
  return { learnerName, subjectName };
}

export function tutorPrompt(learner, subject, attempts = []) {
  const recent = attempts.slice(-5).map(a => `題目：${a.question.slice(0,180)}；結果：${a.result}；提示：${a.hints} 次`).join('\n');
  return `你是繁體中文自適應家教。學習者：${learner.name}；科目：${subject.name}。\n教材：\n${subject.material || '尚未提供教材；先詢問教材或明確標示外部知識。'}\n\n教學規則：先用最多三題診斷先備知識；每次只問一題；先提示再揭露答案；錯誤先處理一個主要觀念；區分筆誤與概念錯誤；使用教材作答並標記超出教材資訊；最後用無提示變形題驗收。若使用者明確要求直接完成任務則切換為任務模式。不要將其他家人或科目的資料混入本次教學。\n最近作答：\n${recent || '尚無紀錄'}\n請先提出本次最適合的一個學習動作。`;
}
