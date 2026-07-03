import { TextStyle } from 'react-native';

// Font family names match expo-google-fonts package exports.
// Install with:
//   npx expo install @expo-google-fonts/geist @expo-google-fonts/jetbrains-mono expo-font expo-splash-screen
//
// Then in App.tsx:
//   import { useFonts, Geist_400Regular, Geist_500Medium, Geist_600SemiBold, Geist_700Bold } from '@expo-google-fonts/geist';
//   import { JetBrainsMono_500Medium, JetBrainsMono_600SemiBold } from '@expo-google-fonts/jetbrains-mono';

export const fonts = {
  // Geist
  regular:  'Geist_400Regular',
  medium:   'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
  bold:     'Geist_700Bold',
  // JetBrains Mono
  mono:        'JetBrainsMono_500Medium',
  monoBold:    'JetBrainsMono_600SemiBold',
} as const;

type Variant = Required<Pick<TextStyle,
  'fontFamily' | 'fontSize' | 'lineHeight'
>> & Pick<TextStyle,
  'letterSpacing' | 'textTransform'
>;

export const type: Record<string, Variant> = {
  // Display
  displayXL:     { fontFamily: fonts.bold,     fontSize: 60, lineHeight: 57,  letterSpacing: -1.8 },
  display:       { fontFamily: fonts.bold,     fontSize: 49, lineHeight: 49,  letterSpacing: -1.5 },
  displaySm:     { fontFamily: fonts.semibold, fontSize: 35, lineHeight: 39,  letterSpacing: -0.7 },
  title:         { fontFamily: fonts.semibold, fontSize: 30, lineHeight: 34 },
  titleSm:       { fontFamily: fonts.semibold, fontSize: 27, lineHeight: 32 },
  subtitle:      { fontFamily: fonts.semibold, fontSize: 24, lineHeight: 30 },
  bodyLg:        { fontFamily: fonts.medium,   fontSize: 19, lineHeight: 27 },
  body:          { fontFamily: fonts.regular,  fontSize: 17, lineHeight: 25 },
  bodySm:        { fontFamily: fonts.regular,  fontSize: 17, lineHeight: 25 },
  bodyXs:        { fontFamily: fonts.regular,  fontSize: 15, lineHeight: 21 },
  buttonPrimary: { fontFamily: fonts.semibold, fontSize: 18, lineHeight: 22 },
  button:        { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 21 },
  buttonSm:      { fontFamily: fonts.medium,   fontSize: 16, lineHeight: 19 },
  label:         { fontFamily: fonts.medium,   fontSize: 15, lineHeight: 19 },
  caption:       { fontFamily: fonts.regular,  fontSize: 14, lineHeight: 18 },
  tabLabel:      { fontFamily: fonts.medium,   fontSize: 12, lineHeight: 14 },

  // Mono
  timer:         { fontFamily: fonts.monoBold, fontSize: 56, lineHeight: 58, letterSpacing: -1 },
  timerXL:       { fontFamily: fonts.mono,     fontSize: 76, lineHeight: 76, letterSpacing: -3 },
  code:          { fontFamily: fonts.mono,     fontSize: 27, lineHeight: 30 },
  meta:          { fontFamily: fonts.mono,     fontSize: 13, lineHeight: 15, letterSpacing: 1.4, textTransform: 'uppercase' },
  metaSm:        { fontFamily: fonts.mono,     fontSize: 12, lineHeight: 14, letterSpacing: 0.6, textTransform: 'uppercase' },

  // Brand wordmark — "FLUME"
  wordmark:      { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 19, letterSpacing: 0.7 },
};

export type TypeVariant = keyof typeof type;
