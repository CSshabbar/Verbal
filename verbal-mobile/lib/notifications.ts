/**
 * Push + local notifications for meetings.
 *
 * DEFENSIVE BY DESIGN: expo-notifications is a NATIVE module. If the running dev
 * client was built before it was added, calling into it throws — so every entry
 * point here lazy-requires the module and swallows failure (fails closed, never
 * crashes the app). Remote push fully lights up on the next native build; the
 * in-app / local path works wherever the native module is present.
 *
 * Flow: registerForMeetingPush() stores an Expo push token in `push_tokens`
 * (keyed by user_id); the desktop calls the notify-meeting-start edge function
 * when a meeting begins, which pushes to those tokens.
 */
import { Platform } from 'react-native';
import { supabase } from './supabase';
import { getUserId, getDeviceName } from './storage';

// Lazy, guarded module handles — never import at top level (avoids a hard crash
// if the native side is missing from the current build).
function notif(): any | null {
  try {
    return require('expo-notifications');
  } catch {
    return null;
  }
}
function device(): any | null {
  try {
    return require('expo-device');
  } catch {
    return null;
  }
}

let _handlerSet = false;

/** Show notifications while the app is foregrounded too (banner + sound). */
export function configureNotificationHandler() {
  const N = notif();
  if (!N || _handlerSet) return;
  try {
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    _handlerSet = true;
  } catch {
    /* older SDK shape — ignore */
  }
}

/** Ask permission, get the Expo push token, upsert it to push_tokens. Safe to
 *  call on every launch; a no-op when the native module isn't available. */
export async function registerForMeetingPush(): Promise<string | null> {
  const N = notif();
  if (!N) return null;
  try {
    const Dev = device();
    if (Dev && Dev.isDevice === false) return null; // simulators can't get real push

    const settings = await N.getPermissionsAsync();
    let granted = settings.granted || settings.ios?.status === 3; // AUTHORIZED
    if (!granted) {
      const req = await N.requestPermissionsAsync();
      granted = req.granted || req.ios?.status === 3;
    }
    if (!granted) return null;

    if (Platform.OS === 'android') {
      await N.setNotificationChannelAsync('meetings', {
        name: 'Meetings',
        importance: N.AndroidImportance?.HIGH ?? 4,
        sound: 'default',
      });
    }

    // projectId comes from EAS config; fall back to undefined (Expo infers it).
    let projectId: string | undefined;
    try {
      const Constants = require('expo-constants').default;
      projectId = Constants?.expoConfig?.extra?.eas?.projectId
        || Constants?.easConfig?.projectId;
    } catch { /* ignore */ }

    const tokenRes = await N.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    const token = tokenRes?.data;
    if (!token) return null;

    const userId = await getUserId();
    if (userId) {
      await supabase.from('push_tokens').upsert(
        {
          user_id: userId,
          token,
          platform: Platform.OS,
          device_name: (await getDeviceName().catch(() => null)) || null,
          updated_at: new Date().toISOString(),
        },
        { onConflict: 'user_id,token' },
      );
    }
    return token;
  } catch {
    return null; // fail closed — never break app launch
  }
}

/** Fire a LOCAL notification (works without the remote push path, e.g. when the
 *  app catches a realtime meeting-start while foregrounded/backgrounded). */
export async function notifyMeetingStartedLocal(title: string, source: string) {
  const N = notif();
  if (!N) return;
  try {
    await N.scheduleNotificationAsync({
      content: {
        title: 'Meeting started',
        body: `${title || 'A meeting'} is recording on ${source || 'your Mac'} — tap to follow live.`,
        sound: 'default',
        data: { type: 'meeting_start' },
      },
      trigger: null, // immediately
    });
  } catch {
    /* ignore */
  }
}

/** Subscribe to notification taps → route to a meeting. Returns an unsubscribe. */
export function onNotificationResponse(cb: (meetingId: string | null) => void): () => void {
  const N = notif();
  if (!N) return () => {};
  try {
    const sub = N.addNotificationResponseReceivedListener((resp: any) => {
      const data = resp?.notification?.request?.content?.data;
      if (data?.type === 'meeting_start') cb(data.meeting_id ?? null);
    });
    return () => { try { sub.remove(); } catch { /* ignore */ } };
  } catch {
    return () => {};
  }
}
