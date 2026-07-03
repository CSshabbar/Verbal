/**
 * useDevices — paired computer list + the current "target" for new recordings.
 * Wire to your sync/pairing backend.
 */
import { useState, useCallback } from 'react';

export type DevicePlatform = 'macos' | 'windows' | 'linux';
export type DeviceStatus = 'online' | 'offline';

export type Device = {
  id: string;
  name: string;
  platform: DevicePlatform;
  status: DeviceStatus;
  isDefault: boolean;
  /** Human-friendly "last seen" string for offline devices. */
  lastSeen?: string;
};

const MOCK: Device[] = [
  { id: 'd1', name: "Aman's MacBook Pro", platform: 'macos',   status: 'online',  isDefault: true },
  { id: 'd2', name: 'Work PC',            platform: 'windows', status: 'online',  isDefault: false },
  { id: 'd3', name: 'Studio iMac',        platform: 'macos',   status: 'offline', isDefault: false, lastSeen: '4h ago' },
];

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>(MOCK);
  const [target, setTarget] = useState<Device | null>(MOCK.find(d => d.isDefault) ?? null);

  const pair = useCallback((d: Device) => {
    setDevices(prev => [...prev, d]);
  }, []);

  const unpair = useCallback((id: string) => {
    setDevices(prev => prev.filter(d => d.id !== id));
  }, []);

  const makeDefault = useCallback((id: string) => {
    setDevices(prev => prev.map(d => ({ ...d, isDefault: d.id === id })));
    const next = devices.find(d => d.id === id) ?? null;
    if (next) setTarget(next);
  }, [devices]);

  return { devices, target, setTarget, pair, unpair, makeDefault };
}
