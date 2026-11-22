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
