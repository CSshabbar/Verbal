import { useState, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { supabase } from './supabase';
import { getUserId, getDeviceName, getDeviceId } from './storage';

export interface Device {
  device_id:   string;
  device_name: string;
  device_type: string;
}

export const TARGET_NONE = '__none__';
export const TARGET_ALL  = null;

const DEVICE_TYPE = Platform.OS === 'ios' ? 'iphone' : 'android';

/** Register this device and return list of other online devices. */
export function useDeviceSelector() {
  const [devices,        setDevices]        = useState<Device[]>([]);
  const [targetDeviceId, setTargetDeviceId] = useState<string | null>(null);
  const [myDeviceId,     setMyDeviceId]     = useState('');
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const uid = await getUserId();
      const dn  = await getDeviceName();
      const did = await getDeviceId();
      if (!mounted) return;
      setMyDeviceId(did);

      // Register this device
      await registerDevice(uid, did, dn);

      // Load other devices
      await loadDevices(uid, did, mounted ? setDevices : () => {});

      // Heartbeat every 60s
      heartbeatRef.current = setInterval(() => {
        registerDevice(uid, did, dn);
        loadDevices(uid, did, setDevices);
      }, 60_000);
    })();

    return () => {
      mounted = false;
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    };
  }, []);

  const refresh = async () => {
    const uid = await getUserId();
    await loadDevices(uid, myDeviceId, setDevices);
  };

  return { devices, targetDeviceId, setTargetDeviceId, myDeviceId, refresh };
}

async function registerDevice(userId: string, deviceId: string, deviceName: string) {
  await supabase.from('devices').upsert({
    user_id:     userId,
    device_id:   deviceId,
    device_name: deviceName,
    device_type: DEVICE_TYPE,
    last_seen:   new Date().toISOString(),
  }, { onConflict: 'user_id,device_id' });
}

async function loadDevices(
  userId: string,
  myDeviceId: string,
  setDevices: (d: Device[]) => void
) {
  const cutoff = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  const { data } = await supabase
    .from('devices')
    .select('device_id, device_name, device_type')
    .eq('user_id', userId)
    .neq('device_id', myDeviceId)
    .gte('last_seen', cutoff);
  if (data) setDevices(data);
}
