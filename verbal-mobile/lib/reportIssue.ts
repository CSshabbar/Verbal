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

export async function reportIssue(message: string): Promise<{ ok: boolean; error?: string }> {
  const msg = (message ?? '').trim().slice(0, REPORT_MESSAGE_MAX);
  if (!msg) return { ok: false, error: 'Describe the issue first' };

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
