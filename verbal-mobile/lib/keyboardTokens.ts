// keyboardTokens — SINGLE source of truth for the Flume keyboard's colors/fonts.
// Values lifted from the real Flume design system (design project
// e550b2e0…: flume-ui/theme/colors.ts + FLUME_DESIGN_HANDOFF.md). The keyboard
// mockups (turns 26/27/28) show a light variant too, so we ship both.
//
// The native keyboards mirror these in their applyTheme() fallbacks — keep in sync.

export const KEYBOARD_ACCENT = '#C85A3E';   // terracotta — THE Flume accent (F logo, triggers, mic dot, +)
export const KEYBOARD_GREEN  = '#4ad15a';   // online / SENT
export const KEYBOARD_ACCENT_SOFT = '#f0b39a'; // text on primarySoft chips

export interface KeyboardPalette {
  bg: string;
  keyBg: string;
  keyText: string;
  modBg: string;      // shift / backspace / ?123 / comma / period
  barBg: string;
  iconTint: string;
  mutedText: string;
  returnBg: string;   // inverts vs theme
  returnText: string;
  micBg: string;
  micFg: string;
  cardBg: string;     // overlay rows / chips (surface1/2)
  highlightBg: string; // active Flume-bar icon
}

// DARK — canonical "Minimalist dark" tokens (flume-ui/theme/colors.ts +
// CLAUDE_CODE_PROMPT.md). Near-black cool bg (#0e1012), subtle grey keys, darker
// modifiers, white return/mic, terracotta accent. barBg == bg so the Flume bar
// blends seamlessly into the app bottom (no floating grey card). cardBg/panel use
// the overlay surfaces (surface3 #26282b rows, surface2 #1a1c1f panel).
export const KEYBOARD_DARK: KeyboardPalette = {
  bg: '#0e1012', keyBg: '#2a2d31', keyText: '#f2f2f2', modBg: '#1e2124',
  barBg: '#0e1012', iconTint: '#8b8d90', mutedText: '#8b8d90',
  returnBg: '#f2f2f2', returnText: '#0e1012', micBg: '#f2f2f2', micFg: '#0e1012',
  cardBg: '#26282b', highlightBg: '#26282b',
};

// LIGHT — from the keyboard mockups (light gray bg, white keys, warm near-black
// text, near-black return/mic).
export const KEYBOARD_LIGHT: KeyboardPalette = {
  bg: '#ECEBEA', keyBg: '#FFFFFF', keyText: '#14110f', modBg: '#CBCBCD',
  barBg: '#ECEBEA', iconTint: '#6b6b6b', mutedText: '#8a857f',
  returnBg: '#14110f', returnText: '#FFFFFF', micBg: '#14110f', micFg: '#FFFFFF',
  cardBg: '#FFFFFF', highlightBg: '#E1E0DF',
};

// Geist (UI) + JetBrains Mono (numerals, section labels, triggers, phonetics, times).
export const KEYBOARD_FONTS = { ui: 'Geist', mono: 'JetBrains Mono' };

export const KEYBOARD_THEME = {
  accent: KEYBOARD_ACCENT,
  green: KEYBOARD_GREEN,
  accentSoft: KEYBOARD_ACCENT_SOFT,
  light: KEYBOARD_LIGHT,
  dark: KEYBOARD_DARK,
  fonts: KEYBOARD_FONTS,
};
