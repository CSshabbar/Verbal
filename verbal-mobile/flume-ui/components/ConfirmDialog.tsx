/**
 * ConfirmDialog — a Flume-styled replacement for the native Alert.
 *
 * Usage (from anywhere, incl. hooks):
 *   import { confirm, notify } from '../components/ConfirmDialog';
 *   const ok = await confirm({ title, message, confirmLabel, cancelLabel, destructive });
 *   await notify('Title', 'message');   // single OK button
 *
 * Mount <ConfirmHost /> once near the app root.
 */
import React, { useEffect, useState } from 'react';
import { Modal, View, Pressable, StyleSheet } from 'react-native';
import { Text } from './Text';
import { colors, pressedStyle } from '../theme';

type Opts = {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string | null;   // null hides the cancel button (notify)
  destructive?: boolean;
};

let _enqueue: ((o: Opts) => Promise<boolean>) | null = null;

export function confirm(opts: Opts): Promise<boolean> {
  return _enqueue ? _enqueue(opts) : Promise.resolve(false);
}
export function notify(title: string, message?: string): Promise<boolean> {
  return confirm({ title, message, confirmLabel: 'OK', cancelLabel: null });
}

export const ConfirmHost: React.FC = () => {
  const [req, setReq] = useState<{ opts: Opts; resolve: (v: boolean) => void } | null>(null);

  useEffect(() => {
    _enqueue = (opts) => new Promise<boolean>((resolve) => setReq({ opts, resolve }));
    return () => { _enqueue = null; };
  }, []);

  const done = (v: boolean) => { req?.resolve(v); setReq(null); };
  if (!req) return null;

  const { title, message, confirmLabel, cancelLabel, destructive } = req.opts;
  const showCancel = cancelLabel !== null;

  return (
    <Modal transparent animationType="fade" visible onRequestClose={() => done(false)}>
      {/* Backdrop = tap-to-dismiss scrim, card = tap swallower. Neither gets a
          pressed state on purpose — dimming the whole dialog would read as a bug. */}
      <Pressable style={styles.backdrop} onPress={() => done(false)}>
        <Pressable style={styles.card} onPress={() => {}}>
          <Text variant="subtitle" style={styles.title}>{title}</Text>
          {message ? (
            <Text variant="bodyXs" color={colors.textMuted} style={styles.message}>{message}</Text>
          ) : null}
          <View style={styles.actions}>
            {showCancel ? (
              <Pressable style={({ pressed }) => [styles.btn, styles.cancelBtn, pressed && pressedStyle]} onPress={() => done(false)}>
                <Text variant="button" color={colors.textSecondary}>{cancelLabel || 'Cancel'}</Text>
              </Pressable>
            ) : null}
            <Pressable
              style={({ pressed }) => [styles.btn, destructive ? styles.destructiveBtn : styles.confirmBtn, pressed && pressedStyle]}
              onPress={() => done(true)}
            >
              <Text variant="button" color={destructive ? colors.primaryAccent : colors.primaryInk}>
                {confirmLabel || 'OK'}
              </Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 28,
  },
  card: {
    width: '100%',
    maxWidth: 360,
    backgroundColor: colors.surface1,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.borderDefault,
    padding: 22,
  },
  title: { fontSize: 20, lineHeight: 25, marginBottom: 8 },
  message: { marginBottom: 20 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 4 },
  btn: { flex: 1, borderRadius: 12, paddingVertical: 13, alignItems: 'center', justifyContent: 'center' },
  cancelBtn: { backgroundColor: colors.surface2 },
  confirmBtn: { backgroundColor: colors.primary },
  destructiveBtn: { backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primaryBorder },
});
