import { Easing } from 'react-native-reanimated';

export const motion = {
  // Recording visualizer (Visualizer.tsx).
  visualizer: {
    duration: 1100,
    easing: Easing.inOut(Easing.sin),
    from: 0.18,
    to: 1.0,
  },
  // Pulse rings (PulseRing.tsx) — idle mic + pair-search bird ring.
  pulse: {
    duration: 1600,
    easing: Easing.inOut(Easing.sin),
    from: 0.18,
    to: 1.0,
  },
  // UI feedback.
  press: {
    duration: 120,
    easing: Easing.out(Easing.quad),
    scale: 0.96,
  },
  micPress: {
    duration: 120,
    easing: Easing.out(Easing.quad),
    scale: 0.94,
  },
  // Toast in/out.
  toast: {
    in:  { duration: 240, easing: Easing.out(Easing.cubic) },
    out: { duration: 180, easing: Easing.in(Easing.cubic) },
  },
  // Auto-dismiss of confirmation screen.
  confirmAutoDismissMs: 3000,
} as const;

/**
 * Deterministic stagger delays (in ms) for the 10-bar recording visualizer.
 * Index 0..9. Negative offsets are folded into withDelay via abs().
 */
export const visualizerStagger = [0, 120, 240, 360, 480, 600, 720, 840, 960, 100];

/** Base heights (px) for each visualizer bar. */
export const visualizerHeights = [28, 56, 90, 70, 110, 80, 100, 60, 90, 40];
