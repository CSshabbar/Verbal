// Flume Design Tokens - EXACT from handoff document
// Source: Flume Wireframes.dc.html, screens 3a-3i

// ─────────────────────────────────────────────────────────────
// COLORS
// ─────────────────────────────────────────────────────────────
export const colors = {
  // Surfaces
  bgCanvas:      '#14110f',  // outermost page background
  bgScreen:      '#0b0908',  // primary screen background
  surface1:      'rgba(245, 237, 228, 0.04)',  // resting card/tile
  surface2:      'rgba(245, 237, 228, 0.06)',  // chip, icon button bg
  surface3:      'rgba(245, 237, 228, 0.08)',  // emphasized/elevated
  scrim:         'rgba(0, 0, 0, 0.55)',        // bottom-sheet/modal scrim

  // Lines
  borderSubtle:  'rgba(245, 237, 228, 0.06)',
  borderDefault: 'rgba(245, 237, 228, 0.08)',
  borderStrong:  'rgba(245, 237, 228, 0.12)',
  borderDashed:  'rgba(245, 237, 228, 0.16)',

  // Text
  textPrimary:   '#f5ede4',
  textSecondary: 'rgba(245, 237, 228, 0.65)',
  textMuted:     'rgba(245, 237, 228, 0.55)',
  textSubtle:    'rgba(245, 237, 228, 0.45)',
  textDisabled:  'rgba(245, 237, 228, 0.30)',

  // Brand (orange)
  primary:       '#E0552C',
  primaryInk:    '#14110f',
  primarySoft:   'rgba(224, 85, 44, 0.14)',
  primarySofter: 'rgba(224, 85, 44, 0.08)',
  primaryBorder: 'rgba(224, 85, 44, 0.35)',
  primaryDashed: 'rgba(224, 85, 44, 0.30)',
  primaryGlow:   'rgba(224, 85, 44, 0.35)',
  primaryAccent: '#ffb593',

  // Status
  online:        '#4ad15a',
  recording:     '#E0552C',
  offline:       'rgba(245, 237, 228, 0.30)',
} as const;

// ─────────────────────────────────────────────────────────────
// TYPOGRAPHY
// ─────────────────────────────────────────────────────────────
export const fonts = {
  sans: 'System',  // Will use Geist in production
  mono: 'Courier', // Will use JetBrains Mono in production
} as const;

export const type = {
  // Display
  displayXL:    { fontFamily: 'System', fontSize: 44, fontWeight: '700', lineHeight: 42, letterSpacing: -1.3 },
  display:      { fontFamily: 'System', fontSize: 36, fontWeight: '700', lineHeight: 36, letterSpacing: -1.1 },
  displaySm:    { fontFamily: 'System', fontSize: 26, fontWeight: '600', lineHeight: 29, letterSpacing: -0.5 },
  title:        { fontFamily: 'System', fontSize: 22, fontWeight: '600', lineHeight: 25 },
  titleSm:      { fontFamily: 'System', fontSize: 20, fontWeight: '600', lineHeight: 24 },
  subtitle:     { fontFamily: 'System', fontSize: 18, fontWeight: '600', lineHeight: 22 },
  bodyLg:       { fontFamily: 'System', fontSize: 14, fontWeight: '500', lineHeight: 20 },
  body:         { fontFamily: 'System', fontSize: 13, fontWeight: '400', lineHeight: 19 },
  bodySm:       { fontFamily: 'System', fontSize: 12.5, fontWeight: '400', lineHeight: 19 },
  bodyXs:       { fontFamily: 'System', fontSize: 11.5, fontWeight: '400', lineHeight: 16 },
  buttonPrimary:{ fontFamily: 'System', fontSize: 13.5, fontWeight: '600' },
  button:       { fontFamily: 'System', fontSize: 13, fontWeight: '600' },
  buttonSm:     { fontFamily: 'System', fontSize: 12, fontWeight: '500' },
  label:        { fontFamily: 'System', fontSize: 11, fontWeight: '500' },
  caption:      { fontFamily: 'System', fontSize: 11, fontWeight: '400', lineHeight: 14 },
  tabLabel:     { fontFamily: 'System', fontSize: 10, fontWeight: '500' },

  // Mono
  timer:        { fontFamily: 'Courier', fontSize: 36, fontWeight: '600', letterSpacing: -0.7 },
  timerXL:      { fontFamily: 'Courier', fontSize: 56, fontWeight: '300', letterSpacing: -2.2 },
  code:         { fontFamily: 'Courier', fontSize: 20, fontWeight: '500' },
  meta:         { fontFamily: 'Courier', fontSize: 10, fontWeight: '500', letterSpacing: 1.4, textTransform: 'uppercase' as const },
  metaSm:       { fontFamily: 'Courier', fontSize: 9.5, fontWeight: '500', letterSpacing: 0.6 },
} as const;

// ─────────────────────────────────────────────────────────────
// SPACING
// ─────────────────────────────────────────────────────────────
export const space = {
  px:   1,
  xs:   4,
  s:    8,
  m:    12,
  base: 16,
  l:    18,
  lg:   22,
  xl:   28,
  xxl:  36,
  xxxl: 48,
} as const;

// ─────────────────────────────────────────────────────────────
// RADIUS
// ─────────────────────────────────────────────────────────────
export const radius = {
  xs:    6,
  sm:    8,
  md:    10,
  lg:    12,
  xl:    14,
  xxl:   18,
  pill:  999,
  phone: 38,
} as const;

// ─────────────────────────────────────────────────────────────
// MOTION
// ─────────────────────────────────────────────────────────────
export const motion = {
  visualizer: { duration: 1100, easing: 'easeInOut' as const },
  pulse:      { duration: 1600, easing: 'easeInOut' as const },
  micPress:   { duration: 120, easing: 'easeOut' as const },
  cardPress:  { duration: 100, easing: 'easeOut' as const },
  screenTransition: { duration: 280, easing: 'easeInOut' as const },
  toastIn:    { duration: 240, easing: 'easeOut' as const },
  toastOut:   { duration: 180, easing: 'easeIn' as const },
} as const;
