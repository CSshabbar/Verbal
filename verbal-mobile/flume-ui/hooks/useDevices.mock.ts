/**
 * useDevices — MOCK (contract reference, never imported at runtime).
 * Same exported shape as ./useDevices, backed by in-memory state.
 *
 * The real hook is a SINGLETON store (IDI-177): one registration, one 60s poll,
 * one `target`, shared by every screen — so a setTarget() on Home is visible to
 * RootNavigator (which stamps `target_device_id`) on the same tick. The list is
 * OTHER devices only; you never send a dictation to the phone you're on.
 */
import { useState, useCallback } from 'react';

export type DevicePlatform = 'macos' | 'windows' | 'linux';
export type DeviceStatus = 'online' | 'offline';

/** Where a finished dictation goes (v2, 2026-08-16):
 *  'device' → the picked target only · 'all' → broadcast (null target row) ·
 *  'none' → this phone only, no cloud push. Persisted in `flume_target_device`
 *  as a device id or the desktop-matching sentinels '__all__' / '__none__'. */
export type SendMode = 'device' | 'all' | 'none';

export type Device = {
  id: string;            // = device_id
  name: string;
  platform: DevicePlatform;
  status: DeviceStatus;
  isDefault: boolean;
  /** ISO timestamp of the last heartbeat (rendered as "4h ago"). */
  lastSeen?: string;
};

const MOCK: Device[] = [
  { id: 'd1', name: "Aman's MacBook Pro", platform: 'macos',   status: 'online',  isDefault: true },
  { id: 'd2', name: 'Work PC',            platform: 'windows', status: 'online',  isDefault: false },
  { id: 'd3', name: 'Studio iMac',        platform: 'macos',   status: 'offline', isDefault: false,
    lastSeen: new Date(Date.now() - 4 * 3600_000).toISOString() },
];

export function useDevices() {
  const [devices, setDevices] = useState<Device[]>(MOCK);
  const [target, setTargetState] = useState<Device | null>(MOCK.find(d => d.isDefault) ?? null);
  const [mode, setMode] = useState<SendMode>('device');
  /** First register+load landed — before this the UI says "Finding devices…",
   *  never "No device" (a lie that let the store adopt a target mid-recording). */
  const ready = true;

  /** Choose the device new dictations are sent to. `null` = "All" (broadcast). */
  const setTarget = useCallback((d: Device | null): void => {
    setDevices(prev => prev.map(x => ({ ...x, isDefault: x.id === (d?.id ?? null) })));
    setTargetState(d);
    setMode(d ? 'device' : 'all');
  }, []);

  /** 'all' | 'none' — a device target is picked via setTarget instead. */
  const setSendMode = useCallback((m: SendMode): void => {
    if (m === 'device') return;
    setMode(m);
    setTargetState(null);
    setDevices(prev => prev.map(x => ({ ...x, isDefault: false })));
  }, []);

  /** Devices self-register via their own app; kept for the local/manual add path. */
  const pair = useCallback((d: Device): void => {
    setDevices(prev => (prev.some(x => x.id === d.id) ? prev : [...prev, d]));
  }, []);

  /**
   * Remove another device from the account list. Optimistic locally, then a
   * user_id-scoped delete. The device itself keeps working and re-appears on its
   * next heartbeat if it is still signed in — which is what the confirm copy says.
   */
  const removeDevice = useCallback(async (id: string): Promise<boolean> => {
    setDevices(prev => prev.filter(d => d.id !== id));
    setTargetState(prev => (prev?.id === id ? null : prev));
    return true;
  }, []);

  const makeDefault = useCallback((id: string): void => {
    setDevices(prev => prev.map(d => ({ ...d, isDefault: d.id === id })));
    setTargetState(prev => devices.find(d => d.id === id) ?? prev);
  }, [devices]);

  /** One heartbeat tick: re-register this device, then re-read the others. */
  const refresh = useCallback(async (): Promise<void> => {}, []);

  return {
    devices,
    target,
    mode,
    ready,
    setTarget,
    setSendMode,
    pair,
    /** @deprecated alias for removeDevice — kept for older call sites. */
    unpair: removeDevice,
    removeDevice,
    makeDefault,
    refresh,
  };
}
