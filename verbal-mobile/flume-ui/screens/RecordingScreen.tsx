import React, { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Text, Chip, ChipDot, Visualizer, IconButton } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import { useRecorder } from '../hooks/useRecorder';
import { useDevices, SendMode } from '../hooks/useDevices';

/** What the user SAW selected when they stopped — the router must send to
 *  exactly this, never to whatever the device store resolves to later
 *  (the "chip said No device, sent to my laptop anyway" race). */
export type SendChoice = { mode: SendMode; id: string | null; name: string | null };

type Props = {
  onCancel: () => void;
  onComplete: (audioUri: string, durationMs: number, send: SendChoice) => void;
};

/**
 * Screen 3d — Recording. Modal-presented.
 * Visualizer + timer + cancel/stop/pause controls.
 */
export const RecordingScreen: React.FC<Props> = ({ onCancel, onComplete }) => {
  const insets = useSafeAreaInsets();
  const { start, stop, cancel, pause, resume, status, durationMs } = useRecorder();
  const [paused, setPaused] = useState(false);
  // stop() in flight (recording ended, transcription running). Guards double-taps
  // and drives the "Transcribing…" UI state.
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  // The mock's hardcoded "9:41" shipped as-is (IDI-180). Real clock, read once on
  // mount — a recording session is short enough that ticking would only cost a
  // timer.
  const [clock] = useState(() => {
    const d = new Date();
    return `${d.getHours() % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')}`;
  });

  // Refs so the unmount cleanup sees the CURRENT status/cancel — the old
  // `return () => { stop(); }` captured the first render's closure, where
  // status === 'idle' makes stop() a no-op, leaving the mic hot after a
  // hardware-back / navigate-away.
  const statusRef = useRef(status);
  statusRef.current = status;
  const cancelRef = useRef(cancel);
  cancelRef.current = cancel;

  useEffect(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    start();
    return () => {
      // Left without Stop/Cancel (hardware back, modal dismissed): release the
      // mic and discard. Skipped while stop() is in flight — the recorder is
      // already stopped and the pipeline owns the audio.
      if (!busyRef.current && statusRef.current !== 'idle') {
        cancelRef.current().catch(() => {});
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { devices, target, mode, ready, setTarget, setSendMode, refresh } = useDevices();
  const [pickerOpen, setPickerOpen] = useState(false);

  // The choice the chip DISPLAYS is the choice the recording SHIPS with —
  // captured at stop time and handed to the router (see SendChoice).
  const sendChoice = (): SendChoice => {
    if (!ready || mode === 'none') return { mode: 'none', id: null, name: null };
    if (mode === 'all') return { mode: 'all', id: null, name: null };
    if (target) return { mode: 'device', id: target.id, name: target.name };
    return { mode: 'none', id: null, name: null };   // device mode, nobody online
  };

  const chipLabel = !ready ? 'Finding devices…'
    : mode === 'none' ? 'This phone only'
    : mode === 'all' ? '→ All devices'
    : target ? `→ ${target.name}`
    : 'This phone only';

  const openPicker = () => {
    if (busyRef.current) return;
    setPickerOpen(o => !o);
    refresh();   // freshest presence while the sheet is open
  };
  const pick = (fn: () => void) => { fn(); setPickerOpen(false); };

  const handleStop = async () => {
    if (busyRef.current) return;              // double-tap: one pipeline run only
    const send = sendChoice();                // freeze what the user was shown
    setPickerOpen(false);
    busyRef.current = true;
    setBusy(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try {
      // stop() itself plays the status-appropriate cue/haptic (success vs warning)
      const result = await stop();
      if (result) onComplete(result.uri, result.durationMs, send);
      else onCancel();                        // nothing was recorded
    } catch {
      // Hard failure (recorder error, no URI) — never trap the user in the modal.
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      onCancel();
    }
  };

  const handleCancel = async () => {
    if (busyRef.current) return;
    busyRef.current = true;                   // also blocks a late Stop tap
    // cancel() discards without transcribing/uploading — Cancel is silent
    // (no cues, no history entry), per the recording conventions.
    try { await cancel(); } catch { /* never trap the user */ }
    onCancel();
  };

  const handlePause = () => {
    if (busyRef.current) return;
    if (paused) { resume(); setPaused(false); }
    else        { pause();  setPaused(true);  }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom + 4 }]}>
      <LinearGradient
        pointerEvents="none"
        colors={['rgba(200, 90, 62,0.12)', colors.bgScreen]}
        locations={[0, 0.6]}
        style={StyleSheet.absoluteFill}
      />

      <View style={styles.statusBar}>
        <Text variant="caption" color={colors.textSubtle}>{clock}</Text>
        <Text variant="caption" color={colors.primary}>● REC</Text>
      </View>

      <View style={{ alignItems: 'center', marginTop: 14, marginBottom: 30, zIndex: 10 }}>
        <Chip
          label={`${chipLabel} ▾`}
          active
          leading={<ChipDot />}
          onPress={openPicker}
        />
        {pickerOpen ? (
          <View style={styles.picker}>
            <PickRow
              icon="phone-portrait-outline"
              label="This phone only"
              sub="Copy here, send nowhere"
              selected={ready && (mode === 'none' || (mode === 'device' && !target))}
              onPress={() => pick(() => setSendMode('none'))}
            />
            <PickRow
              icon="radio-outline"
              label="All devices"
              sub="Lands in every device's history"
              selected={mode === 'all'}
              onPress={() => pick(() => setTarget(null))}
            />
            {devices.map(d => (
              <PickRow
                key={d.id}
                icon={d.platform === 'windows' ? 'desktop-outline' : 'laptop-outline'}
                label={d.name}
                sub="Online now · pastes there"
                online
                selected={mode === 'device' && target?.id === d.id}
                onPress={() => pick(() => setTarget(d))}
              />
            ))}
            {ready && devices.length === 0 ? (
              <Text variant="caption" color={colors.textSubtle} style={{ padding: 12, textAlign: 'center' }}>
                No other devices online right now.
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>

      <View style={styles.middle}>
        <Visualizer
          active={!busy && !paused && status === 'recording'}
          heights={[38, 76, 120, 94, 148, 108, 134, 80, 120, 54]}
          barWidth={6}
          gap={7}
          color={colors.textPrimary}
        />
        <Text variant="timer">{formatMs(durationMs)}</Text>
        <Text variant="bodySm" color={colors.textSubtle}>
          {busy ? 'Transcribing…'
            : paused ? 'Paused — tap pause to resume'
            : 'Listening — tap stop when done'}
        </Text>
      </View>

      <View style={[styles.controls, { paddingBottom: insets.bottom + 8 }]}>
        <IconButton icon="close" size={48} variant="surface" label="Cancel" onPress={handleCancel} />
        <View style={styles.stopGroup}>
          <Pressable
            onPress={handleStop}
            disabled={busy}
            style={({ pressed }) => [styles.stopBtn, pressed && pressedStyle, busy && { opacity: 0.7 }]}
          >
            {busy
              ? <ActivityIndicator color={colors.primaryInk} />
              : <Ionicons name="square" size={20} color={colors.primaryInk} />}
          </Pressable>
          <Text variant="buttonSm" color={colors.textSubtle}>{busy ? 'Working' : 'Stop'}</Text>
        </View>
        <IconButton
          icon={paused ? 'play' : 'pause'}
          size={48}
          variant="surface"
          label={paused ? 'Resume' : 'Pause'}
          onPress={handlePause}
        />
      </View>
    </View>
  );
};

const PickRow: React.FC<{
  icon: any; label: string; sub: string; selected: boolean; online?: boolean; onPress: () => void;
}> = ({ icon, label, sub, selected, online, onPress }) => (
  <Pressable
    onPress={onPress}
    style={({ pressed }) => [styles.pickRow, selected && styles.pickRowOn, pressed && pressedStyle]}
    accessibilityRole="button"
    accessibilityState={{ selected }}
    accessibilityLabel={label}
  >
    <View style={styles.pickIcon}>
      <Ionicons name={icon} size={15} color={selected ? colors.primary : colors.textMuted} />
    </View>
    <View style={{ flex: 1, minWidth: 0 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        {online ? <View style={styles.onlineDot} /> : null}
        <Text variant="label" style={{ fontSize: 14 }} numberOfLines={1}>{label}</Text>
      </View>
      <Text variant="caption" color={colors.textSubtle} numberOfLines={1}>{sub}</Text>
    </View>
    {selected ? <Ionicons name="checkmark" size={16} color={colors.primary} /> : null}
  </Pressable>
);

function formatMs(ms: number) {
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, '0');
  const s = String(total % 60).padStart(2, '0');
  return `${m}:${s}`;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    height: 32,
    alignItems: 'center',
  },
  middle: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 26,
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingVertical: 16,
  },
  stopGroup: { alignItems: 'center', gap: 6 },
  picker: {
    position: 'absolute', top: 42, alignSelf: 'center', width: 300,
    backgroundColor: colors.surface1, borderWidth: 1, borderColor: colors.borderStrong,
    borderRadius: radius.lg, padding: 6, gap: 2,
    shadowColor: '#000', shadowOpacity: 0.45, shadowRadius: 22, shadowOffset: { width: 0, height: 10 },
    elevation: 12,
  },
  pickRow: {
    flexDirection: 'row', alignItems: 'center', gap: 11,
    paddingVertical: 9, paddingHorizontal: 10, borderRadius: radius.md,
  },
  pickRowOn: { backgroundColor: colors.primarySoft },
  pickIcon: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: colors.surface2,
    alignItems: 'center', justifyContent: 'center',
  },
  onlineDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.online },
  stopBtn: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.inkLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default RecordingScreen;
