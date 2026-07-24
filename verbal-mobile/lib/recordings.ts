/**
 * Recording storage (mobile) — mirrors whisperflow/app/recordings.py.
 *
 * Every recording is persisted to the app's document directory (survives the
 * temp cache) as a local backup + retry cache, and uploaded to the same
 * Supabase Storage `recordings` bucket so any device can play it. Playback
 * prefers the local file and falls back to downloading the cloud URL.
 */
import * as FileSystem from 'expo-file-system/legacy';
import { SUPABASE_URL, SUPABASE_ANON_KEY, supabase } from './supabase';

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

/** Upload a local recording to the cloud bucket. Returns the bare object path
 * (NOT a URL — the bucket is private, MER-27). */
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
      return objectPath;
    }
    console.warn('recordings.uploadCloud failed', res.status, (res.body || '').slice(0, 160));
  } catch (e) {
    console.warn('recordings.uploadCloud error:', e);
  }
  return null;
}

/** `stored` may be a bare object path (new writes, MER-27) or a legacy
 * `.../object/public/<bucket>/<path>` URL (rows written before MER-27) — accept
 * either so old rows keep working without a backfill migration. */
export function extractObjectPath(stored: string, bucket: string): string {
  const marker = `/object/public/${bucket}/`;
  const i = stored.indexOf(marker);
  return i >= 0 ? stored.slice(i + marker.length) : stored;
}

/** Generate a short-lived signed URL for a private-bucket object via the SDK
 * (runs under the signed-in user's JWT when signed in — both buckets' storage
 * policies are `TO public`, Hard Rule #10, so this works signed-in or not). */
export async function signUrl(bucket: string, objectPath: string, expiresIn = 180): Promise<string | null> {
  try {
    const { data, error } = await supabase.storage.from(bucket).createSignedUrl(objectPath, expiresIn);
    if (error || !data?.signedUrl) {
      console.warn('recordings.signUrl failed:', error);
      return null;
    }
    return data.signedUrl;
  } catch (e) {
    console.warn('recordings.signUrl error:', e);
    return null;
  }
}

/** Resolve whatever's stored (bare path or legacy public URL) to a fresh signed
 * URL for immediate playback. Shared by MeetingPlaybackScreen and AudioSegmentPlayer. */
export async function resolvePlaybackUrl(stored: string, bucket: string, expiresIn = 180): Promise<string | null> {
  if (!stored) return null;
  return signUrl(bucket, extractObjectPath(stored, bucket), expiresIn);
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
      const signed = await resolvePlaybackUrl(audioUrl, BUCKET);
      if (signed) {
        await ensureDir();
        const dest = `${DIR}${id}.${extOf(audioUrl)}`;
        const r = await FileSystem.downloadAsync(signed, dest);
        if (r.status === 200) return dest;
      }
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
