import React, { useEffect, useState } from 'react';
import { View, StyleSheet, ScrollView, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Text } from '../components';
import { colors, radius, pressedStyle } from '../theme';
import {
  PIPELINES, ASR_MODELS, getPipeline, setPipeline, getAsrModel, setAsrModel,
  type PipelineId,
} from '../../lib/groq';

type Props = { onBack: () => void };

/**
 * Models — which engine hears you, and how many trips it takes to get the words back.
 *
 * Mirrors the desktop Settings → Models pane: the same option ids, the same order,
 * the same one-line descriptions, so the two platforms describe one product rather
 * than two. Both preferences are LOCAL to this device (AsyncStorage) — they are a
 * per-device speed/accuracy trade, not account state, exactly as on desktop.
 *
 * `hybrid` is intentionally absent. It streams audio while you speak; mobile records
 * to a file and uploads afterwards, so offering it would be a switch that does
 * nothing. See lib/groq.ts PIPELINES.
 */
export const ModelsScreen: React.FC<Props> = ({ onBack }) => {
  const insets = useSafeAreaInsets();
  const [pipe, setPipe] = useState<PipelineId>('one');
  const [model, setModel] = useState('auto');

  useEffect(() => {
    let alive = true;
    (async () => {
      const [p, m] = await Promise.all([getPipeline(), getAsrModel()]);
      if (!alive) return;
      setPipe(p);
      setModel(m);
    })();
    return () => { alive = false; };
  }, []);

  // Optimistic: the row lights immediately and the write follows. A failed write
  // leaves the stored default in place, which is the safe direction.
  const pickPipe = (id: PipelineId) => { setPipe(id); void setPipeline(id); };
  const pickModel = (id: string) => { setModel(id); void setAsrModel(id); };

  const Row = ({
    on, title, desc, meta, vendor, onPress,
  }: {
    on: boolean; title: string; desc: string; meta?: string; vendor?: string;
    onPress: () => void;
  }) => (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected: on }}
      accessibilityLabel={`${title}. ${desc}`}
      style={({ pressed }) => [styles.row, on && styles.rowOn, pressed && pressedStyle]}
    >
      <View style={[styles.rail, on && styles.railOn]} />
      <View style={styles.rowTx}>
        <Text variant="button" color={on ? colors.textPrimary : colors.textSecondary}>{title}</Text>
        <Text variant="bodyXs" color={colors.textMuted} numberOfLines={1}>{desc}</Text>
      </View>
      {vendor ? (
        <View style={[styles.vendor, on && styles.vendorOn]}>
          <Text variant="metaSm" color={on ? colors.textSecondary : colors.textSubtle}>
            {vendor.toUpperCase()}
          </Text>
        </View>
      ) : null}
      {meta ? (
        <Text variant="metaSm" color={on ? colors.primary : colors.textSubtle} style={styles.meta}>
          {meta}
        </Text>
      ) : null}
    </Pressable>
  );

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10 }]}>
      <Pressable onPress={onBack} style={({ pressed }) => [styles.backBtn, pressed && pressedStyle]} hitSlop={8}>
        <Ionicons name="chevron-back" size={20} color={colors.textSecondary} />
        <Text variant="button" color={colors.textSecondary}>Settings</Text>
      </Pressable>

      <Text variant="titleSm" style={{ marginTop: 10, marginBottom: 2 }}>Models</Text>
      <Text variant="bodyXs" color={colors.textMuted}>
        Which engine hears you, and how many trips it takes.
      </Text>

      <ScrollView
        style={{ marginTop: 18 }}
        contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}
        showsVerticalScrollIndicator={false}
      >
        <Text variant="metaSm" color={colors.textSubtle} style={styles.sectionLabel}>SPEED</Text>
        <View style={styles.group}>
          {PIPELINES.map(p => (
            <Row
              key={p.id}
              on={pipe === p.id}
              title={p.label}
              desc={p.desc}
              meta={p.wait}
              onPress={() => pickPipe(p.id)}
            />
          ))}
        </View>

        <Text variant="metaSm" color={colors.textSubtle} style={styles.sectionLabel}>
          TRANSCRIPTION MODEL
        </Text>
        <View style={styles.group}>
          {ASR_MODELS.map(m => (
            <Row
              key={m.id}
              on={model === m.id}
              title={m.name}
              desc={m.desc}
              vendor={m.vendor}
              meta={m.wait}
              onPress={() => pickModel(m.id)}
            />
          ))}
        </View>

        <Text variant="bodyXs" color={colors.textSubtle} style={{ marginTop: 14, lineHeight: 17 }}>
          Only Whisper can be biased by your dictionary. On the others your names are
          corrected after transcription instead. If a model is ever unreachable, that
          dictation falls back to Groq on its own.
        </Text>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bgScreen, paddingHorizontal: 18 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 2, marginLeft: -4 },
  sectionLabel: { letterSpacing: 1.4, marginBottom: 8, marginTop: 6 },
  group: {
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
    marginBottom: 18,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingLeft: 14,
    paddingRight: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  rowOn: { backgroundColor: 'rgba(200, 90, 62, 0.09)' },
  // A rail rather than a checkmark: it reads at a glance down the list, and it does
  // not compete with the trailing time for the eye.
  rail: { width: 2, height: 22, borderRadius: 2, backgroundColor: 'transparent' },
  railOn: { backgroundColor: colors.primary },
  rowTx: { flex: 1, minWidth: 0, gap: 2 },
  vendor: {
    borderWidth: 1,
    borderColor: colors.borderDefault,
    borderRadius: radius.sm,
    paddingHorizontal: 5,
    paddingVertical: 2,
  },
  vendorOn: { borderColor: 'rgba(200, 90, 62, 0.35)' },
  meta: { minWidth: 30, textAlign: 'right' },
});
