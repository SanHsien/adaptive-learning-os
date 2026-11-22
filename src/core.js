export const REVIEW_INTERVALS = [1, 3, 7, 14];

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
  if (value.attempts.length > 10000) throw new Error('單次匯入紀錄不可超過 10,000 筆');
  for (const a of value.attempts) {
    if (typeof a.question !== 'string' || typeof a.answer !== 'string' || !['correct', 'incorrect'].includes(a.result) || !['recall','transfer'].includes(a.kind) || !Number.isInteger(a.hints) || a.hints < 0 || a.hints > 99) {
      throw new Error('備份內有無效作答紀錄');
    }
  }
  return { learnerName, subjectName };
}

export function tutorPrompt(learner, subject, attempts = []) {
  const recent = attempts.slice(-5).map(a => `題目：${a.question.slice(0,180)}；結果：${a.result}；提示：${a.hints} 次`).join('\n');
  return `你是繁體中文自適應家教。學習者：${learner.name}；科目：${subject.name}。\n教材：\n${subject.material || '尚未提供教材；先詢問教材或明確標示外部知識。'}\n\n教學規則：先用最多三題診斷先備知識；每次只問一題；先提示再揭露答案；錯誤先處理一個主要觀念；區分筆誤與概念錯誤；使用教材作答並標記超出教材資訊；最後用無提示變形題驗收。若使用者明確要求直接完成任務則切換為任務模式。不要將其他家人或科目的資料混入本次教學。\n最近作答：\n${recent || '尚無紀錄'}\n請先提出本次最適合的一個學習動作。`;
}
