import test from 'node:test';
import assert from 'node:assert/strict';
import { scopedKey, ensureOwner, evidenceLevel, validateBackup, tutorPrompt, reviewDue } from '../src/core.js';

test('學習者和科目組成不同隔離鍵', () => {
  assert.notEqual(scopedKey('family-a','math'), scopedKey('family-b','math'));
  assert.notEqual(scopedKey('family-a','math'), scopedKey('family-a','english'));
  assert.throws(() => scopedKey('a:b','math'));
});

test('拒絕跨學習者使用科目', () => {
  assert.throws(() => ensureOwner({ learnerId:'a' }, 'b'), /不屬於/);
  assert.doesNotThrow(() => ensureOwner({ learnerId:'a' }, 'a'));
});

test('掌握證據只依無提示作答判定', () => {
  assert.equal(evidenceLevel([]),'待驗證');
  assert.equal(evidenceLevel([{result:'correct',hints:1,kind:'recall'}]),'提示後答對');
  assert.equal(evidenceLevel([{result:'correct',hints:0,kind:'recall'}]),'獨立回憶');
  assert.equal(evidenceLevel([{result:'correct',hints:0,kind:'transfer'}]),'遷移應用');
});

test('匯入備份限制格式與作答欄位', () => {
  const backup = {schema:'adaptive-learning-os/v1',learner:{name:'甲'},subject:{name:'數學'},attempts:[{question:'1+1',answer:'2',result:'correct',kind:'recall',hints:0}]};
  assert.equal(validateBackup(backup).subjectName,'數學');
  assert.throws(() => validateBackup({...backup,attempts:[{...backup.attempts[0],result:'admin'}]}));
  assert.throws(() => validateBackup({...backup,schema:'unknown'}));
});

test('字幕來源及版本允許備份，但拒絕未知 MIME', () => {
  const source = {name:'lesson.srt', type:'application/x-subrip'};
  const backup = {schema:'adaptive-learning-os/v1', learner:{name:'甲'}, subject:{name:'中文', material:'合成逐字稿', materialVersion:1, materialSource:source}, attempts:[], materialVersions:[{version:1, content:'合成逐字稿', source, contentHash:null, parserStatus:'confirmed', createdAt:'2026-11-23T00:00:00.000Z'}]};
  assert.equal(validateBackup(backup).subjectName, '中文');
  const vttSource = {name:'lesson.vtt', type:'text/vtt'};
  assert.equal(validateBackup({...backup, subject:{...backup.subject, materialSource:vttSource}, materialVersions:[{...backup.materialVersions[0], source:vttSource}]}).subjectName, '中文');
  assert.throws(() => validateBackup({...backup, subject:{...backup.subject, materialSource:{name:'invalid', type:'application/x-unknown'}}}), /教材來源無效/);
});

test('提示只包含指定家人科目與傳入紀錄', () => {
  const text = tutorPrompt({name:'甲'}, {name:'數學',material:'加法'}, [{question:'1+1',result:'correct',hints:0}]);
  assert.match(text,/甲/); assert.match(text,/加法/); assert.doesNotMatch(text,/乙/);
});

test('複習日期依階段遞增', () => {
  const start = new Date('2026-11-22T08:00:00Z');
  assert.ok(new Date(reviewDue(0,start)) < new Date(reviewDue(3,start)));
});
