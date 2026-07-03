import React, { useEffect } from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withRepeat, withTiming,
  withSequence, withDelay, cancelAnimation,
} from 'react-native-reanimated';
import { colors, motion } from '../theme';

export type PulseRingProps = {
  /** Diameter of the inner anchor — rings sit just outside it. */
  size: number;
  /** Ring color. */
  color?: string;
  /** Render two staggered rings instead of one. */
  double?: boolean;
  children?: React.ReactNode;
  style?: ViewStyle;
};

/**
 * Pulses one or two soft rings around its children.
 * Used for: bird-listening glow (recording), pair-search bird (devices flow).
 */
export const PulseRing: React.FC<PulseRingProps> = ({
  size,
  color = colors.primaryBorder,
  double = true,
  children,
  style,
}) => {
  return (
    <View style={[styles.center, style]}>
      <Ring size={size + 20} color={color} delayMs={0} />
      {double ? <Ring size={size + 44} color={color} delayMs={motion.pulse.duration / 2} /> : null}
      <View>{children}</View>
    </View>
  );
};

const Ring: React.FC<{ size: number; color: string; delayMs: number }> = ({
  size, color, delayMs,
}) => {
  const scale = useSharedValue(0.6);
  const opacity = useSharedValue(0);

  useEffect(() => {
    scale.value = withDelay(
      delayMs,
      withRepeat(
        withSequence(
          withTiming(1, { duration: motion.pulse.duration, easing: motion.pulse.easing }),
          withTiming(0.6, { duration: 0 }),
        ),
        -1,
        false,
      ),
    );
    opacity.value = withDelay(
      delayMs,
      withRepeat(
        withSequence(
          withTiming(0.4, { duration: motion.pulse.duration / 3, easing: motion.pulse.easing }),
          withTiming(0,   { duration: motion.pulse.duration * 2 / 3, easing: motion.pulse.easing }),
        ),
        -1,
        false,
      ),
    );
    return () => {
      cancelAnimation(scale);
      cancelAnimation(opacity);
    };
  }, [delayMs, scale, opacity]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));

  return (
    <Animated.View
      style={[
        styles.ring,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          borderColor: color,
          borderWidth: 1.5,
        },
        animatedStyle,
      ]}
    />
  );
};

const styles = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute' },
});

export default PulseRing;
