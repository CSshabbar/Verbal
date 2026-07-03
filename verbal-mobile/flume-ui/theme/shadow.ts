import { ViewStyle } from 'react-native';

// Drop shadow for the recording mic button.
export const shadowMicActive: ViewStyle = {
  shadowColor: 'rgba(200, 90, 62, 1)',
  shadowOpacity: 0.35,
  shadowOffset: { width: 0, height: 12 },
  shadowRadius: 28,
  elevation: 12,
};

// Shadow for floating toast / bottom sheet.
export const shadowToast: ViewStyle = {
  shadowColor: '#000',
  shadowOpacity: 0.55,
  shadowOffset: { width: 0, height: 14 },
  shadowRadius: 40,
  elevation: 16,
};

// FAB shadow (Notes "+", Canvas saves).
export const shadowFab: ViewStyle = {
  shadowColor: 'rgba(200, 90, 62, 1)',
  shadowOpacity: 0.4,
  shadowOffset: { width: 0, height: 10 },
  shadowRadius: 24,
  elevation: 10,
};

// The mic-idle "double halo" — CSS rings can't be done with native shadow.
// PulseRing component draws these as two absolute Views; values here for reference.
export const idleMicRings = [
  { size: 8,  color: 'rgba(200, 90, 62, 0.08)' },
  { size: 18, color: 'rgba(200, 90, 62, 0.04)' },
] as const;
