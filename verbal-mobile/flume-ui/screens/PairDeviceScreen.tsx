import React, { useRef, useState } from 'react';
import { View, StyleSheet, Pressable, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Text, Button } from '../components';
import { colors, radius } from '../theme';

type Props = {
  onBack: () => void;
  onUseCode?: () => void;
  /** Called once with the scanned QR payload or a manually-entered code. */
  onScan?: (payload: string) => void;
};

/**
 * Screen 3h — Pair a computer. QR scan by default; "Enter code instead" flips to
 * a manual code field (the claim path — lib/pairing.extractToken — accepts a raw
 * code too). On the first read we fire `onScan(payload)` exactly once.
 */
export const PairDeviceScreen: React.FC<Props> = ({ onBack, onScan }) => {
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const handled = useRef(false);
  const granted = !!permission?.granted;
  const [mode, setMode] = useState<'scan' | 'code'>('scan');
  const [code, setCode] = useState('');

  const handleScan = (payload: string) => {
    if (handled.current) return;
    handled.current = true;
    onScan?.(payload);
  };
  const submitCode = () => {
    const c = code.trim();
    if (c) handleScan(c);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 10, paddingBottom: insets.bottom + 14 }]}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
          <Text variant="button">Pair a computer</Text>
        </Pressable>
      </View>

      <Text variant="bodySm" color={colors.textSecondary} style={{ marginBottom: 18 }}>
        {mode === 'scan'
          ? 'Open Flume on your computer → Devices → Pair a device, and point your camera at the code.'
          : 'Open Flume on your computer → Devices → Pair a device, and type the code shown there.'}
      </Text>

      {mode === 'scan' ? (
        <>
          <View style={styles.viewfinder}>
            {granted ? (
              <CameraView
                style={StyleSheet.absoluteFill}
                facing="back"
                barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
                onBarcodeScanned={({ data }) => handleScan(data)}
              />
            ) : (
              <View style={styles.permBlock}>
                <Ionicons name="camera-outline" size={30} color={colors.textMuted} />
                <Text variant="bodyXs" color={colors.textMuted} style={{ textAlign: 'center', marginVertical: 10 }}>
                  Camera access is needed to scan the pairing code.
                </Text>
                <Button label="Allow camera" variant="ghost" onPress={requestPermission} />
              </View>
            )}
            <View pointerEvents="none" style={styles.frame} />
            <View pointerEvents="none" style={[styles.corner, { top: 18, left: 18, borderTopLeftRadius: 12, borderTopWidth: 3, borderLeftWidth: 3 }]} />
            <View pointerEvents="none" style={[styles.corner, { top: 18, right: 18, borderTopRightRadius: 12, borderTopWidth: 3, borderRightWidth: 3 }]} />
            <View pointerEvents="none" style={[styles.corner, { bottom: 18, left: 18, borderBottomLeftRadius: 12, borderBottomWidth: 3, borderLeftWidth: 3 }]} />
            <View pointerEvents="none" style={[styles.corner, { bottom: 18, right: 18, borderBottomRightRadius: 12, borderBottomWidth: 3, borderRightWidth: 3 }]} />
            {granted && <View pointerEvents="none" style={styles.scanLine} />}
          </View>
          <View style={{ flex: 1 }} />
          <Button label="Enter code instead" variant="ghost" onPress={() => setMode('code')} />
        </>
      ) : (
        <>
          <TextInput
            style={styles.codeInput}
            value={code}
            onChangeText={setCode}
            placeholder="Pairing code"
            placeholderTextColor={colors.textDisabled}
            autoCapitalize="none"
            autoCorrect={false}
            autoFocus
            returnKeyType="done"
            onSubmitEditing={submitCode}
          />
          <View style={{ flex: 1 }} />
          <Button label="Pair" onPress={submitCode} style={{ marginBottom: 10 }} />
          <Button label="Scan a QR code instead" variant="ghost" onPress={() => setMode('scan')} />
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  topBar: { marginBottom: 20 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  codeInput: {
    backgroundColor: colors.surface1,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    paddingHorizontal: 14,
    paddingVertical: 14,
    color: colors.textPrimary,
    fontFamily: 'Geist_500Medium',
    fontSize: 16,
    letterSpacing: 1,
  },
  permBlock: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 30,
  },
  viewfinder: {
    aspectRatio: 1,
    borderRadius: radius.xxl,
    backgroundColor: '#0e1012',
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: 18,
    overflow: 'hidden',
    position: 'relative',
  },
  frame: {
    position: 'absolute',
    top: 18, left: 18, right: 18, bottom: 18,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: 14,
  },
  corner: {
    position: 'absolute',
    width: 32, height: 32,
    borderColor: colors.primary,
  },
  scanLine: {
    position: 'absolute',
    left: 24, right: 24, top: '50%',
    height: 2,
    backgroundColor: colors.primary,
    shadowColor: colors.primary,
    shadowOpacity: 0.9,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
});

export default PairDeviceScreen;
