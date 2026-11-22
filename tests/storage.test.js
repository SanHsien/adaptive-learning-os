import 'fake-indexeddb/auto';
import test from 'node:test';
import assert from 'node:assert/strict';
import { addLearner, addSubject, saveMaterial, getSubject, addAttempt, listAttempts, exportScope, importIsolated, listSubjects } from '../src/storage.js';

test('不同家人與科目完全分開查詢、修改與匯出', async () => {
  const parent = await addLearner('甲');
  const child = await addLearner('乙');
  const math = await addSubject(parent.id, '數學', '甲的數學');
  const english = await addSubject(parent.id, '英文', '甲的英文');
  const otherMath = await addSubject(child.id, '數學', '乙的數學');
  await addAttempt(parent.id, math.id, {question:'甲題',answer:'甲答',kind:'recall',hints:0,result:'correct'});
  await addAttempt(parent.id, english.id, {question:'英文題',answer:'英文答',kind:'recall',hints:0,result:'incorrect'});
  await addAttempt(child.id, otherMath.id, {question:'乙題',answer:'乙答',kind:'recall',hints:0,result:'incorrect'});
  assert.deepEqual((await listAttempts(parent.id,math.id)).map(x=>x.question),['甲題']);
  assert.deepEqual((await listAttempts(parent.id,english.id)).map(x=>x.question),['英文題']);
  assert.deepEqual((await listAttempts(child.id,otherMath.id)).map(x=>x.question),['乙題']);
  await assert.rejects(() => listAttempts(child.id,math.id), /不屬於/);
  await assert.rejects(() => saveMaterial(child.id,math.id,'竄改'), /不屬於/);
  assert.equal((await getSubject(math.id)).material,'甲的數學');
  const exportData = await exportScope(parent.id,math.id);
  assert.equal(exportData.attempts.length,1);
  assert.equal(exportData.subject.material,'甲的數學');
  assert.equal(JSON.stringify(exportData).includes('乙題'), false);
  assert.equal(JSON.stringify(exportData).includes('英文題'), false);
});

test('匯入建立獨立副本，不污染原家人的科目', async () => {
  const learner = await addLearner('來源');
  const subject = await addSubject(learner.id,'自然','第一章');
  const backup = await exportScope(learner.id,subject.id);
  const imported = await importIsolated(backup);
  assert.notEqual(imported.learner.id,learner.id);
  assert.notEqual(imported.subject.id,subject.id);
  assert.equal((await listSubjects(learner.id)).length,1);
  assert.equal((await listSubjects(imported.learner.id)).length,1);
  await saveMaterial(imported.learner.id,imported.subject.id,'第二章');
  assert.equal((await getSubject(subject.id)).material,'第一章');
});

test('作答欄位不能偽造或改寫 owner 與 scope', async () => {
  const learner = await addLearner('測試防竄改');
  const subject = await addSubject(learner.id, '自然');
  const attempt = await addAttempt(learner.id, subject.id, {
    question: '水的化學式', answer: 'H2O', kind: 'recall', hints: 0, result: 'correct',
    learnerId: 'forged', subjectId: 'forged', scope: 'forged:forged', id: 'forged', createdAt: '2020-01-01T00:00:00.000Z'
  });
  assert.equal(attempt.learnerId, learner.id);
  assert.equal(attempt.subjectId, subject.id);
  assert.equal(attempt.scope, `${learner.id}:${subject.id}`);
  assert.notEqual(attempt.id, 'forged');
  assert.notEqual(attempt.createdAt, '2020-01-01T00:00:00.000Z');
  assert.deepEqual((await listAttempts(learner.id, subject.id)).map(a => a.question), ['水的化學式']);
});

test('無效作答與超長教材拒絕且不留下資料', async () => {
  const learner = await addLearner('長度檢查');
  const subject = await addSubject(learner.id, '數學', '原教材');
  await assert.rejects(() => saveMaterial(learner.id, subject.id, 'x'.repeat(100001)), /教材/);
  await assert.rejects(() => addAttempt(learner.id, subject.id, {
    question: ' ', answer: '2', kind: 'recall', hints: 0, result: 'correct'
  }), /作答/);
  assert.equal((await getSubject(subject.id)).material, '原教材');
  assert.equal((await listAttempts(learner.id, subject.id)).length, 0);
});

test('匯入畸形備份不能建立部分學習空間', async () => {
  const marker = 'INVALID_IMPORT_MARKER';
  const backup = {
    schema: 'adaptive-learning-os/v1', learner: {name: marker},
    subject: {name: '英文', material: '教材'},
    attempts: [
      {question: 'one', answer: '1', result: 'correct', kind: 'recall', hints: 0},
      {question: 'two', answer: '2', result: 'correct', kind: 'recall', hints: 0, reviewDue: 'not-a-date'}
    ]
  };
  await assert.rejects(() => importIsolated(backup), /日期/);
  const { listLearners } = await import('../src/storage.js');
  assert.equal((await listLearners()).some(l => l.name.includes(marker)), false);
});

test('檔案教材來源與版本僅綁定該學習者科目且可備份', async () => {
  const alpha = await addLearner('教材甲');
  const beta = await addLearner('教材乙');
  const first = await addSubject(alpha.id, '國文');
  const second = await addSubject(beta.id, '國文', '乙的課文');
  await saveMaterial(alpha.id, first.id, '甲的課文', {name:'ch1.md', type:'text/markdown'});
  await assert.rejects(() => saveMaterial(beta.id, first.id, '試圖跨人覆蓋'), /不屬於/);
  assert.equal((await getSubject(first.id)).materialVersion, 1);
  assert.deepEqual((await getSubject(first.id)).materialSource, {name:'ch1.md', type:'text/markdown'});
  assert.equal((await getSubject(second.id)).material, '乙的課文');
  const backup = await exportScope(alpha.id, first.id);
  assert.equal(backup.subject.materialSource.name, 'ch1.md');
  const imported = await importIsolated(backup);
  assert.equal((await getSubject(imported.subject.id)).materialVersion, 1);
  assert.equal((await getSubject(imported.subject.id)).materialSource.name, 'ch1.md');
  await saveMaterial(alpha.id, first.id, '甲的新課文');
  assert.equal((await getSubject(first.id)).materialVersion, 2);
  assert.equal((await getSubject(first.id)).materialSource, null);
  assert.equal((await getSubject(imported.subject.id)).material, '甲的課文');
});

test('並行更新同科教材仍逐次增加版本且跨人寫入拒絕', async () => {
  const owner = await addLearner('並行甲');
  const other = await addLearner('並行乙');
  const subject = await addSubject(owner.id, '理化');
  await Promise.all([
    saveMaterial(owner.id, subject.id, '版本 A'),
    saveMaterial(owner.id, subject.id, '版本 B'),
    saveMaterial(owner.id, subject.id, '版本 C')
  ]);
  assert.equal((await getSubject(subject.id)).materialVersion, 3);
  await assert.rejects(() => saveMaterial(other.id, subject.id, '越權內容'), /資料庫交易中止|不屬於/);
  assert.equal((await getSubject(subject.id)).materialVersion, 3);
});
