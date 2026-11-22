import 'fake-indexeddb/auto';
import test from 'node:test';
import assert from 'node:assert/strict';
import { getSubject, listMaterialVersions, listAttempts, saveMaterial } from '../src/storage.js';

test('IndexedDB v1 升級 v2 保留舊教材、作答與後續版本', async () => {
  const name = 'adaptive-learning-os-v1';
  const original = await new Promise((resolve, reject) => {
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('learners', {keyPath: 'id'});
      db.createObjectStore('subjects', {keyPath: 'id'}).createIndex('learnerId', 'learnerId');
      db.createObjectStore('attempts', {keyPath: 'id'}).createIndex('scope', 'scope');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  await new Promise((resolve, reject) => {
    const tx = original.transaction(['learners', 'subjects', 'attempts'], 'readwrite');
    tx.objectStore('learners').add({id: 'legacy-learner', name: '舊家人'});
    tx.objectStore('subjects').add({id: 'legacy-subject', learnerId: 'legacy-learner', name: '舊數學', material: '第三版內容', materialVersion: 3, createdAt: '2026-01-01T00:00:00.000Z'});
    tx.objectStore('attempts').add({id: 'legacy-attempt', learnerId: 'legacy-learner', subjectId: 'legacy-subject', scope: 'legacy-learner:legacy-subject', question: '舊題', answer: '舊答', kind: 'recall', hints: 0, result: 'correct', materialVersion: 2, createdAt: '2026-01-02T00:00:00.000Z'});
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  original.close();

  assert.equal((await getSubject('legacy-subject')).material, '第三版內容');
  assert.deepEqual((await listAttempts('legacy-learner', 'legacy-subject')).map(a => [a.question, a.materialVersion]), [['舊題', 2]]);
  assert.deepEqual((await listMaterialVersions('legacy-learner', 'legacy-subject')).map(v => v.version), [3]);
  await saveMaterial('legacy-learner', 'legacy-subject', '第四版內容');
  assert.deepEqual((await listMaterialVersions('legacy-learner', 'legacy-subject')).map(v => [v.version, v.content]), [[3, '第三版內容'], [4, '第四版內容']]);
  await assert.rejects(() => listMaterialVersions('other-learner', 'legacy-subject'), /不屬於/);
});
