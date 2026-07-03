/**
 * Recording storage (mobile) — mirrors whisperflow/app/recordings.py.
 *
 * Every recording is persisted to the app's document directory (survives the
 * temp cache) as a local backup + retry cache, and uploaded to the same
 * Supabase Storage `recordings` bucket so any device can play it. Playback
 * prefers the local file and falls back to downloading the cloud URL.
 */
import * as FileSystem from 'expo-file-system/legacy';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './supabase';

const DIR = FileSystem.documentDirectory + 'recordings/';
const BUCKET = 'recordings';
const STORAGE = `${SUPABASE_URL}/storage/v1`;

async function ensureDir() {
  const info = await FileSystem.getInfoAsync(DIR);
  if (!info.exists) await FileSystem.makeDirectoryAsync(DIR, { intermediates: true });
}

function extOf(uri: string): string {
  const m = uri.match(/\.([a-zA-Z0-9]+)(?:\?|$)/);
  return m ? m[1].toLowerCase() : 'm4a';
}

function contentType(ext: string): string {
  if (ext === 'wav') return 'audio/wav';
  if (ext === 'caf') return 'audio/x-caf';
  return 'audio/m4a';
}

/** Copy the recorder's temp file into a persistent location. Returns its uri. */
export async function persist(tempUri: string, id: string): Promise<string | null> {
  try {
    await ensureDir();
    const dest = `${DIR}${id}.${extOf(tempUri)}`;
    await FileSystem.copyAsync({ from: tempUri, to: dest });
    return dest;
  } catch (e) {
    console.error('recordings.persist failed:', e);
    return null;
  }
}

/** Upload a local recording to the cloud bucket. Returns its public URL. */
export async function uploadCloud(localUri: string, userId: string, id: string): Promise<string | null> {
  if (!userId || !localUri) return null;
  try {
    const ext = extOf(localUri);
    const objectPath = `${userId}/${id}.${ext}`;
    const res = await FileSystem.uploadAsync(`${STORAGE}/object/${BUCKET}/${objectPath}`, localUri, {
      httpMethod: 'POST',
      uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
      headers: {
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        'Content-Type': contentType(ext),
        'x-upsert': 'true',
      },
    });
    if (res.status >= 200 && res.status < 300) {
      return `${STORAGE}/object/public/${BUCKET}/${objectPath}`;
    }
    console.warn('recordings.uploadCloud failed', res.status, (res.body || '').slice(0, 160));
  } catch (e) {
    console.warn('recordings.uploadCloud error:', e);
  }
  return null;
}

/** Return a local uri for playback/retry, downloading from the cloud if needed. */
export async function ensureLocal(id: string, audioUri?: string, audioUrl?: string): Promise<string | null> {
  if (audioUri) {
    try {
      const info = await FileSystem.getInfoAsync(audioUri);
      if (info.exists) return audioUri;
    } catch { /* fall through */ }
  }
  if (audioUrl) {
    try {
      await ensureDir();
      const dest = `${DIR}${id}.${extOf(audioUrl)}`;
      const r = await FileSystem.downloadAsync(audioUrl, dest);
      if (r.status === 200) return dest;
    } catch (e) {
      console.warn('recordings.ensureLocal download failed:', e);
    }
  }
  return audioUri || null;
}

export async function remove(uri?: string) {
  if (!uri) return;
  try { await FileSystem.deleteAsync(uri, { idempotent: true }); } catch { /* ignore */ }
}
