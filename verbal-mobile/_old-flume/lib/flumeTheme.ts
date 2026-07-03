// EXACT Flume Design System from Wireframes

export const flumeColors = {
  // Primary palette - EXACT from wireframes
  background: '#14110f',      // Very dark brown (Flume bg)
  surface: '#1A1614',         // Slightly lighter for cards
  accent: '#E0552C',          // Flume orange-red
  accentDim: 'rgba(224,85,44,0.15)',
  
  // Text colors
  textPrimary: '#F5EDE4',     // Off-white text
  textSecondary: '#9A9590',   // Muted text
  textTertiary: '#6B6660',    // Subtle text
  
  // Functional colors
  success: '#3DAA6E',         // Green for success states
  error: '#E0552C',           // Same as accent
  warning: '#F5A623',         // Amber
  
  // UI elements
  border: 'rgba(245,237,228,0.06)',
  borderActive: 'rgba(224,85,44,0.3)',
  overlay: 'rgba(20,17,15,0.8)',
  
  // Buttons
  buttonPrimary: '#E0552C',
  buttonPrimaryText: '#FFFFFF',
  buttonSecondary: 'rgba(255,255,255,0.08)',
  buttonSecondaryText: '#F5EDE4',
};

export const flumeFonts = {
  // Font weights
  thin: '100' as const,
  light: '300' as const,
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
  extraBold: '800' as const,
  
  // Font sizes (increased by 2px for sizes ≤17)
  xs: 13,  // was 11
  sm: 15,  // was 13
  md: 17,  // was 15
  lg: 19,  // was 17
  xl: 20,  // unchanged (>17)
  xxl: 24, // unchanged (>17)
  xxxl: 32,// unchanged (>17)
  hero: 48,// unchanged (>17)
};

export const flumeSpacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
  hero: 80,
};

export const flumeRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  full: 9999,
};

export const flumeAnimations = {
  // Timing
  fast: 150,
  normal: 300,
  slow: 500,
  
  // Easing
  easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  easeOut: 'cubic-bezier(0.0, 0, 0.2, 1)',
  spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
};

export const flumeLogo = {
  text: 'FLUME',
  letterSpacing: 6,
  fontSize: 28,
  fontWeight: '700' as const,
  color: '#F5EDE4',
};
