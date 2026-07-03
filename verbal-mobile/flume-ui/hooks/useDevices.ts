/**
 * useDevices — registers THIS device and lists the user's other online devices,
 * using the same working scheme as the original app (lib/useDeviceSelector):
 *   - upsert self into `devices` (user_id, device_id, device_name, device_type, last_seen)
 *   - heartbeat every 60s
 *   - "online" = last_seen within 5 min; self is excluded from the list
 *
 * Exposes the Flume UI contract:
 *   { devices, target, setTarget, pair, unpair, makeDefault }
 * `target` is the device new recordings are sent to (persisted locally).
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase } from '../../lib/supabase';
import { getUserId, getDeviceName, getDeviceId } from '../../lib/storage';

export type DevicePlatform = 'macos' | 'windows' | 'linux';
export type DeviceStatus = 'online' | 'offline';

export type Device = {
  id: string;            // = device_id
  name: string;
  platform: DevicePlatform;
  status: DeviceStatus;
  isDefault: boolean;
  lastSeen?: string;
};

const TARGET_KEY = 'flume_target_device';
const MY_TYPE = Platform.OS === 'ios' ? 'iphone' : 'android';
const PRESENCE_MS = 5 * 60 * 1000;

function toPlatform(deviceType?: string): DevicePlatform {
  const v = String(deviceType ?? '').toLowerCase();
  if (v.includes('win')) return 'windows';
  if (v.includes('linux')) return 'linux';
  return 'macos'; // mac / iphone / android / unknown → mac glyph
}

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [target, setTargetState] = useState<Device | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const targetIdRef = useRef<string | null>(null);

  const loadDevices = useCallback(async () => {
    try {
      const userId = await getUserId();
      const myId = await getDeviceId();
      const cutoff = new Date(Date.now() - PRESENCE_MS).toISOString();
      const { data } = await supabase
        .from('devices')
        .select('device_id, device_name, device_type, last_seen')
        .eq('user_id', userId)
        .neq('device_id', myId)
        .gte('last_seen', cutoff);

      const list: Device[] = (data ?? []).map((r: any) => ({
        id: r.device_id,
        name: r.device_name || 'Device',
        platform: toPlatform(r.device_type),
        status: 'online',
        isDefault: r.device_id === targetIdRef.current,
      }));
      setDevices(list);

      // Keep the target valid; fall back to the first available device.
      setTargetState(prev => {
        const stillThere = list.find(d => d.id === targetIdRef.current);
        const next = stillThere ?? list[0] ?? null;
        targetIdRef.current = next?.id ?? null;
        return next;
      });
    } catch (err) {
      console.error('Failed to load devices:', err);
    }
  }, []);

  const registerSelf = useCallback(async () => {
    try {
      const userId = await getUserId();
      const deviceId = await getDeviceId();
      const deviceName = await getDeviceName();
      await supabase.from('devices').upsert(
        {
          user_id: userId,
          device_id: deviceId,
          device_name: deviceName,
          device_type: MY_TYPE,
          last_seen: new Date().toISOString(),
        },
        { onConflict: 'user_id,device_id' },
      );
    } catch (err) {
      console.error('Failed to register device:', err);
    }
  }, []);

  useEffect(() => {
    (async () => {
      targetIdRef.current = await AsyncStorage.getItem(TARGET_KEY);
      await registerSelf();
      await loadDevices();
      heartbeatRef.current = setInterval(() => {
        registerSelf();
        loadDevices();
      }, 60_000);
    })();
    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    };
  }, [registerSelf, loadDevices]);

  const setTarget = useCallback((d: Device | null) => {
    targetIdRef.current = d?.id ?? null;
    setTargetState(d);
    setDevices(prev => prev.map(x => ({ ...x, isDefault: x.id === d?.id })));
    if (d) AsyncStorage.setItem(TARGET_KEY, d.id).catch(() => {});
    else AsyncStorage.removeItem(TARGET_KEY).catch(() => {});
  }, []);

  const makeDefault = useCallback((id: string) => {
    setDevices(prev => {
      const next = prev.map(d => ({ ...d, isDefault: d.id === id }));
      const chosen = next.find(d => d.id === id) ?? null;
      if (chosen) {
        targetIdRef.current = chosen.id;
        setTargetState(chosen);
        AsyncStorage.setItem(TARGET_KEY, chosen.id).catch(() => {});
      }
      return next;
    });
  }, []);

  const pair = useCallback((d: Device) => {
    // Devices self-register via the desktop app; expose add for manual/local use.
    setDevices(prev => (prev.some(x => x.id === d.id) ? prev : [...prev, d]));
  }, []);

  const unpair = useCallback(async (id: string) => {
    setDevices(prev => prev.filter(d => d.id !== id));
    setTargetState(prev => (prev?.id === id ? null : prev));
    try {
      await supabase.from('devices').delete().eq('device_id', id);
    } catch (err) {
      console.error('Failed to unpair device:', err);
    }
  }, []);

  return { devices, target, setTarget, pair, unpair, makeDefault };
}
