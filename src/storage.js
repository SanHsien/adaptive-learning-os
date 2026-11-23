import { ensureOwner, newId, scopedKey, validateBackup, validateAttempt, validateMaterial, normalizeName } from './core.js';

const DB_NAME = 'adaptive-learning-os-v1';
const DB_VERSION = 2;

async function contentHash(content) {
  const bytes = new TextEncoder().encode(content);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function versionRecord(subject, version, material, source, timestamp, hash) {
  return {
    id: `${subject.id}:${version}`, learnerId: subject.learnerId, subjectId: subject.id,
    scope: scopedKey(subject.learnerId, subject.id), version, content: material,
    source: source || null, contentHash: hash, parserStatus: 'confirmed', createdAt: timestamp
  };
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = event => {
      const db = request.result;
      if (event.oldVersion < 1) {
        db.createObjectStore('learners', { keyPath: 'id' });
        db.createObjectStore('subjects', { keyPath: 'id' }).createIndex('learnerId', 'learnerId');
        db.createObjectStore('attempts', { keyPath: 'id' }).createIndex('scope', 'scope');
      }
      if (!db.objectStoreNames.contains('materials')) db.createObjectStore('materials', {keyPath: 'id'}).createIndex('scope', 'scope');
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
  const learner = { id: newId(), name: normalizeName(name, '學習者名稱'), createdAt: new Date().toISOString() };
  await transaction(['learners'], 'readwrite', tx => tx.objectStore('learners').add(learner));
  return learner;
}

export async function addSubject(learnerId, name, material = '') {
  if (!await getLearner(learnerId)) throw new Error('學習者不存在');
  const subject = { id: newId(), learnerId, name: normalizeName(name, '科目名稱'), material: validateMaterial(material), materialVersion: material ? 1 : 0, materialSource: null, materialHistoryMigrated: true, createdAt: new Date().toISOString() };
  const hash = material ? await contentHash(material) : null;
  await transaction(['subjects', 'materials'], 'readwrite', tx => {
    tx.objectStore('subjects').add(subject);
    if (material) tx.objectStore('materials').add(versionRecord(subject, 1, material, null, subject.createdAt, hash));
  });
  return subject;
}

export async function saveMaterial(learnerId, subjectId, material, source = null) {
  validateMaterial(material);
  if (source !== null && (!source || typeof source !== 'object' || typeof source.name !== 'string' || source.name.length > 180 || !source.name.trim() || !['text/plain', 'text/markdown', 'text/csv', 'application/x-subrip', 'text/vtt', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/webp', 'audio/mpeg', 'audio/wav', 'audio/mp4', 'video/mp4', 'video/webm'].includes(source.type))) {
    throw new Error('教材檔案來源資訊無效');
  }
  ensureOwner(await getSubject(subjectId), learnerId);
  const hash = await contentHash(material);
  await transaction(['subjects', 'materials'], 'readwrite', tx => {
    const store = tx.objectStore('subjects');
    const materials = tx.objectStore('materials');
    const request = store.get(subjectId);
    request.onsuccess = () => {
      try {
        const subject = request.result;
        ensureOwner(subject, learnerId);
        const version = (subject.materialVersion || 0) + 1;
        const timestamp = new Date().toISOString();
        // Legacy records were stored inline; retain their latest snapshot on first edit.
        if (subject.materialVersion > 0 && !subject.materialHistoryMigrated) {
          materials.put(versionRecord(subject, subject.materialVersion, subject.material || '', subject.materialSource || null, subject.materialUpdatedAt || subject.createdAt, null));
        }
        materials.add(versionRecord(subject, version, material, source, timestamp, hash));
        store.put({
          ...subject, material, materialVersion: version, materialHistoryMigrated: true,
          materialSource: source ? {name: source.name, type: source.type} : null,
          materialUpdatedAt: timestamp
        });
      } catch (_error) { tx.abort(); }
    };
  });
}

export async function listMaterialVersions(learnerId, subjectId) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  const entries = (await all('materials', 'scope', scopedKey(learnerId, subjectId))).sort((a,b) => a.version - b.version);
  if (subject.materialVersion && !entries.some(a => a.version === subject.materialVersion)) {
    entries.push(versionRecord(subject, subject.materialVersion, subject.material || '', subject.materialSource || null, subject.materialUpdatedAt || subject.createdAt, null));
  }
  return entries.sort((a,b) => a.version - b.version);
}

export async function listAttempts(learnerId, subjectId) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  return (await all('attempts', 'scope', scopedKey(learnerId, subjectId))).sort((a,b) => a.createdAt.localeCompare(b.createdAt));
}

export async function addAttempt(learnerId, subjectId, values) {
  const subject = await getSubject(subjectId);
  ensureOwner(subject, learnerId);
  const fields = validateAttempt(values);
  const attempt = { ...fields, id: newId(), learnerId, subjectId, scope: scopedKey(learnerId,subjectId), materialVersion: subject.materialVersion || 0, createdAt: new Date().toISOString() };
  await transaction(['attempts'], 'readwrite', tx => tx.objectStore('attempts').add(attempt));
  return attempt;
}

export async function exportScope(learnerId, subjectId) {
  const learner = await getLearner(learnerId);
  const subject = await getSubject(subjectId);
  if (!learner) throw new Error('學習者不存在');
  ensureOwner(subject, learnerId);
  const attempts = await listAttempts(learnerId, subjectId);
  const versions = await listMaterialVersions(learnerId, subjectId);
  return { schema: 'adaptive-learning-os/v1', exportedAt: new Date().toISOString(), learner: { name: learner.name }, subject: { name: subject.name, material: subject.material, materialVersion: subject.materialVersion || 0, materialSource: subject.materialSource || null }, materialVersions: versions.map(({version,content,source,contentHash,parserStatus,createdAt}) => ({version,content,source,contentHash,parserStatus,createdAt})), attempts: attempts.map(({question, answer, result, hints, kind, createdAt, reviewDue, materialVersion}) => ({question, answer, result, hints, kind, createdAt, reviewDue, materialVersion})) };
}

export async function importIsolated(backup) {
  const { learnerName, subjectName } = validateBackup(backup);
  // Check content integrity before opening a write transaction. Legacy hashes may be null.
  if (backup.materialVersions) {
    const latest = backup.materialVersions.find(entry => entry.version === (backup.subject.materialVersion || 0));
    if (latest && latest.content !== (backup.subject.material ?? '')) throw new Error('教材最新版本與備份內容不一致');
    for (const entry of backup.materialVersions) {
      if (entry.contentHash !== null && entry.contentHash !== await contentHash(entry.content)) {
        throw new Error('教材版本 SHA-256 驗證失敗，拒絕匯入');
      }
    }
  }
  const allowedVersions = new Set((backup.materialVersions || []).map(entry => entry.version));
  if (!backup.materialVersions && (backup.subject.materialVersion || backup.subject.material)) {
    allowedVersions.add(backup.subject.materialVersion || 1);
  }
  for (const attempt of backup.attempts) {
    const legacyHistoricalReference = !backup.materialVersions && attempt.materialVersion > 0 &&
      attempt.materialVersion <= (backup.subject.materialVersion || 0);
    if (attempt.materialVersion != null && attempt.materialVersion !== 0 &&
        !allowedVersions.has(attempt.materialVersion) && !legacyHistoricalReference) {
      throw new Error('作答引用不存在的教材版本');
    }
  }
  const learner = { id: newId(), name: `${learnerName}（匯入）`, createdAt: new Date().toISOString() };
  const subject = { id: newId(), learnerId: learner.id, name: subjectName, material: backup.subject.material ?? '', materialVersion: backup.subject.materialVersion || (backup.subject.material ? 1 : 0), materialSource: backup.subject.materialSource || null, createdAt: new Date().toISOString() };
  const versions = backup.materialVersions || (subject.materialVersion ? [{version: subject.materialVersion, content: subject.material, source: subject.materialSource, contentHash: null, parserStatus:'confirmed', createdAt: subject.createdAt}] : []);
  await transaction(['learners','subjects','attempts','materials'], 'readwrite', tx => {
    tx.objectStore('learners').add(learner);
    tx.objectStore('subjects').add({...subject, materialHistoryMigrated: true});
    for (const entry of versions) tx.objectStore('materials').add(versionRecord(subject, entry.version, entry.content, entry.source, entry.createdAt, entry.contentHash));
    for (const a of backup.attempts) {
      const fields = validateAttempt(a);
      tx.objectStore('attempts').add({
        ...fields, id: newId(), learnerId: learner.id, subjectId: subject.id, scope: scopedKey(learner.id,subject.id),
        createdAt: typeof a.createdAt === 'string' ? a.createdAt : new Date().toISOString(), materialVersion: a.materialVersion ?? subject.materialVersion
      });
    }
  });
  return { learner, subject };
}
