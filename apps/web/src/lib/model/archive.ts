import type { ModelPrediction } from '$lib/model';

export interface ArchivedVisual {
  model?: string;
  work_stage: string;
  stage_evidence: string;
  scene_summary: string;
  plan_alignment: 'consistent' | 'possible_mismatch' | 'insufficient_evidence' | 'not_provided';
  plan_reason: string;
  planText: string;
}

export interface ArchivedFrame {
  id: string;
  name: string;
  preview: Blob;
  prediction: ModelPrediction;
  visual?: ArchivedVisual;
}

export interface ArchivedRun {
  id: string;
  createdAt: string;
  title: string;
  origin: 'demo' | 'upload';
  recognitionMode: '640' | '960';
  frames: ArchivedFrame[];
}

const DB_NAME = 'sitewatch.analysis.v1';
const STORE = 'runs';

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, { keyPath: 'id' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveArchivedRun(run: ArchivedRun): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(run);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

export async function listArchivedRuns(): Promise<ArchivedRun[]> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();
      request.onsuccess = () => resolve((request.result as ArchivedRun[]).sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
      request.onerror = () => reject(request.error);
    });
  } finally { db.close(); }
}

export async function updateArchivedVisual(runId: string, frameId: string, visual: ArchivedVisual): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      const request = store.get(runId);
      request.onsuccess = () => {
        const run = request.result as ArchivedRun | undefined;
        if (!run) return;
        const frame = run.frames.find((item) => item.id === frameId);
        if (frame) { frame.visual = visual; store.put(run); }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

export async function deleteArchivedRun(id: string): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally { db.close(); }
}

/** A small view copy keeps the local archive usable without storing full source files. */
export async function archivePreview(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, 1280 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Не удалось подготовить миниатюру.');
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error('Не удалось сохранить миниатюру.')),
      'image/jpeg', 0.76,
    ));
  } finally { bitmap.close(); }
}
