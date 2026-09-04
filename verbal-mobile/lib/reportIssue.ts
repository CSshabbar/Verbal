/**
 * reportIssue — sends an in-app "Report an issue" submission to the
 * `report-issue` Edge Function (beta launch, 2026-09). The function saves the
 * row (`issue_reports`, service-role-only) and best-effort emails the founder;
 * a saved report is a successful report even if the email fails.
 *
 * Works signed-in AND signed out: the function's verify_jwt accepts the anon
 * key too, recording the report as anonymous. Mirrors the desktop caller
 * (`shared_dashboard.DashboardApi.report_issue`) — change one, check the other.
 */
import { Platform } from 'react-native';

import { SUPABASE_URL, SUPABASE_ANON_KEY, supabase } from './supabase';
import { getDeviceName } from './storage';

export const REPORT_MESSAGE_MAX = 4000;
export const REPORT_IMAGE_MAX_BYTES = 5 * 1024 * 1024;
// base64 is 4/3 the decoded size; +4 tolerates padding.
const IMAGE_MAX_B64 = Math.ceil(REPORT_IMAGE_MAX_BYTES * 4 / 3) + 4;
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif']);

export type ReportImage = {
  /** Raw base64, no data: prefix (expo-image-picker's asset.base64 shape). */
  base64: string;
  /** File extension: png | jpg | jpeg | webp | gif. */
  ext: string;
};

export async function reportIssue(
  message: string,
  image?: ReportImage | null,
): Promise<{ ok: boolean; error?: string }> {
  const msg = (message ?? '').trim().slice(0, REPORT_MESSAGE_MAX);
  if (!msg) return { ok: false, error: 'Describe the issue first' };

  // The screenshot is optional garnish server-side too, but a picked-then-
  // rejected image would surprise the tester — validate it up front instead
  // of silently dropping it.
  let img: ReportImage | null = null;
  if (image?.base64) {
    const ext = (image.ext || '').toLowerCase();
    if (!IMAGE_EXTS.has(ext)) return { ok: false, error: 'Pick a PNG, JPEG, WebP or GIF image' };
    if (image.base64.length > IMAGE_MAX_B64) {
      return { ok: false, error: 'Image is too large — 5 MB max' };
    }
    img = { base64: image.base64, ext };
  }

  // Metadata is garnish — every read below fails soft so a missing optional
  // module can never block the report itself.
  let appVersion = '';
  try {
    appVersion = require('expo-constants').default?.expoConfig?.version ?? '';
  } catch { /* optional */ }
  let osVersion: string = Platform.OS;
  try {
    const Device = require('expo-device');
    const v = (Device?.osVersion ?? '').toString().trim();
    if (v) osVersion = `${Platform.OS} ${v}`;
  } catch { /* optional */ }
  let deviceName = '';
  try {
    deviceName = await getDeviceName();
  } catch { /* optional */ }

  try {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token || SUPABASE_ANON_KEY;
    const res = await fetch(`${SUPABASE_URL}/functions/v1/report-issue`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        apikey: SUPABASE_ANON_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: msg,
        platform: Platform.OS,
        app_version: appVersion,
        device_name: deviceName,
        os_version: osVersion,
        ...(img ? { image_b64: img.base64, image_type: img.ext } : {}),
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) {
      return {
        ok: false,
        error: body.error === 'empty_message'
          ? 'Describe the issue first'
          : "Couldn't send the report — please try again",
      };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "Couldn't send the report — check your connection" };
  }
}
