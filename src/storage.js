import { ensureOwner, newId, scopedKey, validateBackup } from './core.js';

const DB_NAME = 'adaptive-learning-os-v1';
const DB_VERSION = 1;

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('learners', { keyPath: 'id' });
      db.createObjectStore('subjects', { keyPath: 'id' }).createIndex('learnerId', 'learnerId');
      db.createObjectStore('attempts', { keyPath: 'id' }).createIndex('scope', 'scope');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transaction(storeNames, mode, work) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(storeNames, mode);
      let result;
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error('資料庫交易中止'));
      try { result = work(tx); } catch (error) { tx.abort(); reject(error); }
    });
  } finally { db.close(); }
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function read(store, key) {
  const db = await openDb();
  try {
    const tx = db.transaction(store, 'readonly');
    return await requestResult(tx.objectStore(store).get(key));
  } finally { db.close(); }
}

async function all(store, index, key) {
  const db = await openDb();
  try {
    const tx = db.transaction(store, 'readonly');
    const source = index ? tx.objectStore(store).index(index) : tx.objectStore(store);
    return await requestResult(index ? source.getAll(key) : source.getAll());
  } finally { db.close(); }
}

export const listLearners = () => all('learners');
export const listSubjects = learnerId => all('subjects', 'learnerId', learnerId);
export const getLearner = id => read('learners', id);
export const getSubject = id => read('subjects', id);

export async function addLearner(name) {
  const learner = { id: newId(), name, createdAt: new Date().toISOString() };
  await transaction(['learners'], 'readwrite', tx => tx.objectStore('learners').add(learner));
  return learner;
}

export async function addSubject(learnerId, name, material = '') {
  if (!await getLearner(learnerId)) throw new Error('學習者不存在');
  const subject = { id: newId(), learnerId, name, material, createdAt: new Date().toISOString() };
  await transaction(['subjects'], 'readwrite', tx => tx.objectStore('subjects').add(subject));
  return subject;
}

export async function saveMaterial(learnerId, subjectId, material) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  await transaction(['subjects'], 'readwrite', tx => tx.objectStore('subjects').put({ ...subject, material }));
}

export async function listAttempts(learnerId, subjectId) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  return (await all('attempts', 'scope', scopedKey(learnerId, subjectId))).sort((a,b) => a.createdAt.localeCompare(b.createdAt));
}

export async function addAttempt(learnerId, subjectId, values) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  const attempt = { id: newId(), learnerId, subjectId, scope: scopedKey(learnerId,subjectId), ...values, createdAt: new Date().toISOString() };
  await transaction(['attempts'], 'readwrite', tx => tx.objectStore('attempts').add(attempt));
  return attempt;
}

export async function exportScope(learnerId, subjectId) {
  const learner = await getLearner(learnerId);
  const subject = await getSubject(subjectId);
  if (!learner) throw new Error('學習者不存在');
  ensureOwner(subject, learnerId);
  const attempts = await listAttempts(learnerId, subjectId);
  return { schema: 'adaptive-learning-os/v1', exportedAt: new Date().toISOString(), learner: { name: learner.name }, subject: { name: subject.name, material: subject.material }, attempts: attempts.map(({question, answer, result, hints, kind, createdAt, reviewDue}) => ({question, answer, result, hints, kind, createdAt, reviewDue})) };
}

export async function importIsolated(backup) {
  const { learnerName, subjectName } = validateBackup(backup);
  const learner = { id: newId(), name: `${learnerName}（匯入）`, createdAt: new Date().toISOString() };
  const subject = { id: newId(), learnerId: learner.id, name: subjectName, material: String(backup.subject.material || ''), createdAt: new Date().toISOString() };
  await transaction(['learners','subjects','attempts'], 'readwrite', tx => {
    tx.objectStore('learners').add(learner);
    tx.objectStore('subjects').add(subject);
    for (const a of backup.attempts) {
      tx.objectStore('attempts').add({
        id: newId(), learnerId: learner.id, subjectId: subject.id, scope: scopedKey(learner.id,subject.id),
        question: a.question, answer: a.answer, result: a.result, kind: a.kind, hints: a.hints,
        reviewDue: typeof a.reviewDue === 'string' ? a.reviewDue : null,
        createdAt: typeof a.createdAt === 'string' ? a.createdAt : new Date().toISOString()
      });
    }
  });
  return { learner, subject };
}
