import React, { useEffect, useMemo } from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withRepeat, withTiming,
  withSequence, withDelay, cancelAnimation,
} from 'react-native-reanimated';
import { colors, motion, visualizerStagger, visualizerHeights } from '../theme';

export type VisualizerProps = {
  /** Active = animating. False = bars at rest at their from-scale. */
  active?: boolean;
  /** Override the default 10-bar set. Each entry is the base height. */
  heights?: number[];
  /** Bar width in px. */
  barWidth?: number;
  /** Gap between bars in px. */
  gap?: number;
  /** Optional accent color. */
  color?: string;
  style?: ViewStyle;
};

/**
 * Recording visualizer — 10 vertical bars, staggered scaleY animation.
 * Matches the design on screen 3d.
 *
 * Each bar uses Reanimated shared values, NOT React state — no re-renders during animation.
 */
export const Visualizer: React.FC<VisualizerProps> = ({
  active = true,
  heights = visualizerHeights,
  barWidth = 4,
  gap = 5,
  color = colors.primary,
  style,
}) => {
  const containerHeight = Math.max(...heights);
  return (
    <View style={[styles.row, { gap, height: containerHeight }, style]}>
      {heights.map((h, i) => (
        <Bar
          key={i}
          height={h}
          width={barWidth}
          color={color}
          delayMs={visualizerStagger[i % visualizerStagger.length]}
          active={active}
        />
      ))}
    </View>
  );
};

const Bar: React.FC<{
  height: number;
  width: number;
  color: string;
  delayMs: number;
  active: boolean;
}> = ({ height, width, color, delayMs, active }) => {
  const scale = useSharedValue<number>(motion.visualizer.from);

  useEffect(() => {
    if (active) {
      scale.value = withDelay(
        delayMs,
        withRepeat(
          withSequence(
            withTiming(motion.visualizer.to, {
              duration: motion.visualizer.duration / 2,
              easing: motion.visualizer.easing,
            }),
            withTiming(motion.visualizer.from, {
              duration: motion.visualizer.duration / 2,
              easing: motion.visualizer.easing,
            }),
          ),
          -1,
          false,
        ),
      );
    } else {
      cancelAnimation(scale);
      scale.value = withTiming(motion.visualizer.from, { duration: 200 });
    }
    return () => cancelAnimation(scale);
  }, [active, delayMs, scale]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scaleY: scale.value }],
  }));

  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius: width / 2,
          backgroundColor: color,
        },
        animatedStyle,
      ]}
    />
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default Visualizer;
