// Flume color tokens — "Minimalist dark" (Wireframes turn 8, the settled direction).
// Near-black cool bg, neutral text, terracotta as the single brand accent,
// white primary buttons, solid cool cards. Token names are stable so every
// screen re-skins by changing values here.

export const colors = {
  // Surfaces
  bgCanvas:      '#0e1012',
  bgScreen:      '#0e1012',
  surface1:      '#17191c',                    // solid cards (history/canvas/notes rows)
  surface2:      'rgba(240, 240, 240, 0.06)',  // icon tiles, small circles
  surface3:      'rgba(240, 240, 240, 0.09)',
  scrim:         'rgba(0, 0, 0, 0.55)',

  // Lines
  borderSubtle:  'rgba(240, 240, 240, 0.05)',
  borderDefault: 'rgba(240, 240, 240, 0.08)',
  borderStrong:  'rgba(240, 240, 240, 0.12)',
  borderDashed:  'rgba(240, 240, 240, 0.16)',

  // Text
  textPrimary:   '#f2f2f2',
  textSecondary: 'rgba(240, 240, 240, 0.75)',
  textMuted:     'rgba(240, 240, 240, 0.55)',
  textSubtle:    'rgba(240, 240, 240, 0.48)',
  textDisabled:  'rgba(240, 240, 240, 0.35)',

  // Brand — terracotta, the only accent
  primary:       '#C85A3E',
  primaryInk:    '#0e1012',
  primarySoft:   'rgba(200, 90, 62, 0.14)',
  primarySofter: 'rgba(200, 90, 62, 0.08)',
  primaryBorder: 'rgba(200, 90, 62, 0.35)',
  primaryDashed: 'rgba(200, 90, 62, 0.35)',
  primaryGlow:   'rgba(200, 90, 62, 0.35)',
  primaryAccent: '#f0b39a',

  // Primary buttons are near-white with dark ink (minimalist-dark CTA)
  inkLight:      '#f2f2f2',

  // Per-device tag colors (History cards, device rows)
  tagMac:        '#C85A3E',
  tagMacInk:     '#fff5ea',
  tagPC:         '#4a6494',
  tagPCInk:      '#eaf1ff',

  // Status
  online:        '#4ad15a',
  recording:     '#C85A3E',
  offline:       'rgba(240, 240, 240, 0.30)',
} as const;

export type ColorToken = keyof typeof colors;
