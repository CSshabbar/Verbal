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

/**
 * Delete the CLOUD copy of a recording (IDI-172). `stored` is whatever the row
 * carried in `audio_url` — a bare object path (post-MER-27) or a legacy public
 * URL — so it goes through extractObjectPath() like every other consumer.
 *
 * Best-effort by design: tombstoning the transcription is the operation that
 * matters, and a bucket that briefly keeps an orphan object is far better than
 * a delete that fails because storage was unreachable. Returns whether the
 * object was actually removed, for logging.
 */
export async function removeCloud(stored?: string | null, bucket = BUCKET): Promise<boolean> {
  if (!stored) return false;
  try {
    const path = extractObjectPath(stored, bucket);
    if (!path) return false;
    const { error } = await supabase.storage.from(bucket).remove([path]);
    if (error) {
      console.warn('recordings.removeCloud failed:', error);
      return false;
    }
    return true;
  } catch (e) {
    console.warn('recordings.removeCloud error:', e);
    return false;
  }
}

/**
 * Delete every locally-persisted recording (IDI-170).
 *
 * `delete-account` erases the cloud copies, and clearAccountData() erases the
 * AsyncStorage rows that point at them — but the audio files themselves sat in
 * documentDirectory/recordings/ forever, surviving deletion and account
 * switches. Removing the whole directory is enough: ensureDir() recreates it
 * lazily on the next persist()/ensureLocal().
 *
 * Called from useAuth on account DELETION and on an account SWITCH (so the new
 * account can't inherit the previous one's audio). Deliberately NOT called on a
 * plain sign-out — signing back into the same account should still be able to
 * retry/play a failed local dictation.
 */
export async function removeAll() {
  try { await FileSystem.deleteAsync(DIR, { idempotent: true }); } catch { /* ignore */ }
}

/* ── Bounded cleanup of the local recordings cache (IDI-180) ───────────────── */

/** Filename of a local uri / cloud object path / legacy public URL.
 *  `file:///…/recordings/rec_1.m4a`, `<uid>/rec_1.m4a` and `rec_1.m4a` all
 *  collapse to `rec_1.m4a`, so ONE basename set covers every way a recording can
 *  be referenced. */
export function baseName(uri: string): string {
  if (!uri) return '';
  const clean = uri.split('?')[0].split('#')[0];
  const i = clean.lastIndexOf('/');
  return i >= 0 ? clean.slice(i + 1) : clean;
}

export interface SweepOptions {
  /** Max files to retain in total, newest first (default 100). */
  keep?: number;
  /** Delete unreferenced files older than this many days (default 30). */
  maxAgeDays?: number;
  /**
   * Uris/paths whose files must NEVER be deleted. lib may not import hooks, so
   * the keep-list is data: pass it in, or leave it out and sweep() reads the
   * lib-level caches itself (history + note audio segments).
   */
  referenced?: string[];
}

/**
 * Pure decision half of sweep() — which files to delete. Exported so it can be
 * exercised without a filesystem.
 *
 * Rules, in order:
 *   1. A referenced file is NEVER deleted (it still backs a history entry or a
 *      note's audio segment), and it counts against the `keep` budget.
 *   2. Unreferenced files older than `maxAgeDays` go.
 *   3. Whatever unreferenced files remain are kept newest-first until the total
 *      retained hits `keep`; the rest go.
 */
export function planSweep(
  files: { name: string; mtimeMs: number }[],
  opts: { keep: number; maxAgeDays: number; referenced: Set<string>; now: number },
): string[] {
  const { keep, maxAgeDays, referenced, now } = opts;
  const maxAgeMs = maxAgeDays * 86_400_000;
  const kept = files.filter((f) => referenced.has(f.name));
  const loose = files
    .filter((f) => !referenced.has(f.name))
    .sort((a, b) => b.mtimeMs - a.mtimeMs);   // newest first

  // Referenced files are retained no matter what, so they eat the budget first.
  let budget = Math.max(0, keep - kept.length);
  const doomed: string[] = [];
  for (const f of loose) {
    const tooOld = maxAgeMs > 0 && now - f.mtimeMs > maxAgeMs;
    if (tooOld || budget <= 0) doomed.push(f.name);
    else budget -= 1;
  }
  return doomed;
}

/**
 * Basenames of every recording the app still needs: history entries' local files
 * (and their cloud objects, same basename) plus notes' audio segments.
 *
 * Returns null if EITHER cache could not be read — an unreadable cache is not an
 * empty one, and sweeping against a half-built keep-list would delete audio that
 * is still linked. The caller aborts on null.
 */
async function referencedBaseNames(): Promise<Set<string> | null> {
  const out = new Set<string>();
  const add = (u?: string | null) => { const b = baseName(u || ''); if (b) out.add(b); };
  // lib → lib only (storage/notesStorage read AsyncStorage; neither imports this
  // module), so there is no cycle and no hook dependency.
  try {
    const { getHistory } = await import('./storage');
    for (const e of await getHistory()) { add(e.audio_uri); add(e.audio_url); }
    const { getCachedNotes } = await import('./notesStorage');
    for (const n of await getCachedNotes()) {
      for (const s of n.audio_segments || []) add(s.url);
    }
  } catch (e) {
    console.warn('recordings.sweep: keep-list unreadable, skipping sweep:', e);
    return null;
  }
  return out;
}

/**
 * Prune `documentDirectory/recordings/` so the local audio cache stays bounded
 * (IDI-180). Recordings are persisted forever today — only account deletion
 * (removeAll) and an explicit dictation delete ever removed one — so a heavy
 * user's cache grows without limit.
 *
 * Peripheral and fully fail-closed (Hard Rule #1): any error, and it simply does
 * nothing. Called once per launch, fire-and-forget.
 */
export async function sweep(
  opts: SweepOptions = {},
): Promise<{ scanned: number; deleted: number }> {
  const { keep = 100, maxAgeDays = 30 } = opts;
  try {
    const dirInfo = await FileSystem.getInfoAsync(DIR);
    if (!dirInfo.exists) return { scanned: 0, deleted: 0 };

    const names = await FileSystem.readDirectoryAsync(DIR);
    if (!names.length) return { scanned: 0, deleted: 0 };

    const referenced = opts.referenced
      ? new Set(opts.referenced.map(baseName).filter(Boolean))
      : await referencedBaseNames();
    if (!referenced) return { scanned: names.length, deleted: 0 };  // fail closed

    const files: { name: string; mtimeMs: number }[] = [];
    for (const name of names) {
      try {
        const info: any = await FileSystem.getInfoAsync(DIR + name);
        if (!info.exists || info.isDirectory) continue;
        // modificationTime is in SECONDS; a missing one is treated as "now" so an
        // un-dateable file is never aged out, only ever evicted by the count bound.
        files.push({ name, mtimeMs: info.modificationTime ? info.modificationTime * 1000 : Date.now() });
      } catch { /* skip the ones we can't stat */ }
    }

    const doomed = planSweep(files, { keep, maxAgeDays, referenced, now: Date.now() });
    let deleted = 0;
    for (const name of doomed) {
      try {
        await FileSystem.deleteAsync(DIR + name, { idempotent: true });
        deleted += 1;
      } catch { /* best effort */ }
    }
    if (deleted) console.log(`recordings.sweep: removed ${deleted}/${files.length} cached recordings`);
    return { scanned: files.length, deleted };
  } catch (e) {
    console.warn('recordings.sweep failed:', e);
    return { scanned: 0, deleted: 0 };
  }
}
