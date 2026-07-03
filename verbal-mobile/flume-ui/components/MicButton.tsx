import React, { useEffect } from 'react';
import { Pressable, View, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withRepeat, withTiming, withSequence,
  cancelAnimation,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { colors, motion, shadowMicActive } from '../theme';

export type MicButtonProps = {
  /** 'idle' = pre-record on Home (3c) — soft halo rings. 'recording' = stop control (3d). */
  state: 'idle' | 'recording';
  onPress?: () => void;
  size?: number;
};

/**
 * The mic. Idle = 120px round, primary fill, two outer pulse rings.
 * Recording = 92px stop button with drop shadow.
 */
export const MicButton: React.FC<MicButtonProps> = ({
  state,
  onPress,
  size = state === 'idle' ? 120 : 92,
}) => {
  // Idle haloed rings — two concentric Views, slowly pulsing.
  const ringScale = useSharedValue(1);
  const ringOpacity = useSharedValue(0.6);

  useEffect(() => {
    if (state === 'idle') {
      ringScale.value = withRepeat(
        withSequence(
          withTiming(1.15, { duration: motion.pulse.duration, easing: motion.pulse.easing }),
          withTiming(1, { duration: motion.pulse.duration, easing: motion.pulse.easing }),
        ),
        -1,
        false,
      );
      ringOpacity.value = withRepeat(
        withSequence(
          withTiming(0.25, { duration: motion.pulse.duration, easing: motion.pulse.easing }),
          withTiming(0.6, { duration: motion.pulse.duration, easing: motion.pulse.easing }),
        ),
        -1,
        false,
      );
    }
    return () => {
      cancelAnimation(ringScale);
      cancelAnimation(ringOpacity);
    };
  }, [state, ringScale, ringOpacity]);

  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: ringScale.value }],
    opacity: ringOpacity.value,
  }));

  return (
    <Pressable onPress={onPress} hitSlop={12} style={styles.center}>
      {state === 'idle' && (
        <>
          <Animated.View
            style={[
              styles.ring,
              {
                width: size + 16,
                height: size + 16,
                borderRadius: (size + 16) / 2,
                backgroundColor: 'rgba(200, 90, 62, 0.08)',
              },
              ringStyle,
            ]}
          />
          <Animated.View
            style={[
              styles.ring,
              {
                width: size + 36,
                height: size + 36,
                borderRadius: (size + 36) / 2,
                backgroundColor: 'rgba(200, 90, 62, 0.04)',
              },
              ringStyle,
            ]}
          />
        </>
      )}
      <View
        style={[
          styles.btn,
          state === 'recording' && shadowMicActive,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: colors.primary,
          },
        ]}
      >
        <Ionicons
          name={state === 'idle' ? 'mic' : 'square'}
          size={state === 'idle' ? 36 : 22}
          color={colors.primaryInk}
        />
      </View>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute' },
  btn: { alignItems: 'center', justifyContent: 'center' },
});

export default MicButton;
