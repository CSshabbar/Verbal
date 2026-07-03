import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

// 10 bars with deterministic heights and staggered delays
const BARS = [
  { height: 28, delay: 0 },
  { height: 56, delay: 120 },
  { height: 90, delay: 240 },
  { height: 70, delay: 360 },
  { height: 110, delay: 480 },
  { height: 80, delay: 600 },
  { height: 100, delay: 720 },
  { height: 60, delay: 840 },
  { height: 90, delay: 960 },
  { height: 40, delay: 100 },
];

export default function RecordingScreen({ navigation }: { navigation: any }) {
  const [elapsed, setElapsed] = React.useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const barAnims = useRef(BARS.map(() => new Animated.Value(0.18))).current;

  useEffect(() => {
    // Timer
    timerRef.current = setInterval(() => {
      setElapsed(prev => prev + 1);
    }, 1000);

    // Animate bars
    const animations = barAnims.map((anim, i) => {
      return Animated.loop(
        Animated.sequence([
          Animated.timing(anim, {
            toValue: 1.0,
            duration: 1100,
            useNativeDriver: true,
            delay: BARS[i].delay,
          }),
          Animated.timing(anim, {
            toValue: 0.18,
            duration: 1100,
            useNativeDriver: true,
          }),
        ])
      );
    });

    Animated.parallel(animations).start();

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleStop = () => {
    navigation.navigate('Confirmation');
  };

  return (
    <View style={s.root}>
      {/* Gradient Background */}
      <LinearGradient
        colors={['rgba(224,85,44,0.12)', '#0b0908']}
        locations={[0, 0.6]}
        style={s.gradient}
      />

      <SafeAreaView style={s.safeArea} edges={['top']}>
        {/* Status Row */}
        <View style={s.statusRow}>
          <Text style={s.time}>9:41</Text>
          <View style={s.recIndicator}>
            <View style={s.recDot} />
            <Text style={s.recText}>REC</Text>
          </View>
        </View>

        <View style={s.content}>
          {/* Target Chip */}
          <View style={s.targetChip}>
            <Ionicons name="arrow-forward" size={12} color={colors.primaryAccent} />
            <Text style={s.targetChipText}>MacBook Pro</Text>
          </View>

          {/* Center Column */}
          <View style={s.centerColumn}>
            {/* Visualizer */}
            <View style={s.visualizer}>
              {BARS.map((bar, i) => (
                <Animated.View
                  key={i}
                  style={[
                    s.bar,
                    {
                      height: bar.height,
                      transform: [{ scaleY: barAnims[i] }],
                    },
                  ]}
                />
              ))}
            </View>

            {/* Timer */}
            <Text style={s.timer}>{formatTime(elapsed)}</Text>

            {/* Hint */}
            <Text style={s.hint}>Listening — tap stop when done</Text>
          </View>

          {/* Controls */}
          <View style={s.controls}>
            {/* Cancel */}
            <TouchableOpacity style={s.controlBtn} activeOpacity={0.7}>
              <Ionicons name="close" size={18} color={colors.textSecondary} />
              <Text style={s.controlLabel}>Cancel</Text>
            </TouchableOpacity>

            {/* Stop */}
            <TouchableOpacity 
              style={s.stopButton}
              onPress={handleStop}
              activeOpacity={0.7}
            >
              <Ionicons name="stop" size={28} color={colors.primaryInk} />
            </TouchableOpacity>

            {/* Pause */}
            <TouchableOpacity style={s.controlBtn} activeOpacity={0.7}>
              <Ionicons name="pause" size={18} color={colors.textSecondary} />
              <Text style={s.controlLabel}>Pause</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
  },
  gradient: {
    ...StyleSheet.absoluteFillObject,
  },
  safeArea: {
    flex: 1,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.l,
    paddingTop: space.s,
  },
  time: {
    ...type.meta,
    color: colors.textPrimary,
  },
  recIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  recDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.recording,
  },
  recText: {
    ...type.meta,
    color: colors.recording,
  },
  content: {
    flex: 1,
    paddingTop: space.s,
    paddingHorizontal: space.l,
  },
  targetChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 11,
    borderWidth: 1,
    borderColor: colors.primaryBorder,
    alignSelf: 'center',
    marginBottom: 30,
  },
  targetChipText: {
    ...type.label,
    color: colors.primaryAccent,
  },
  centerColumn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 26,
  },
  visualizer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 110,
  },
  bar: {
    width: 4,
    backgroundColor: colors.primary,
    borderRadius: 2,
    transformOrigin: 'center',
  },
  timer: {
    ...type.timer,
    color: colors.textPrimary,
  },
  hint: {
    ...type.bodySm,
    color: colors.textSubtle,
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingVertical: 16,
    paddingBottom: 20,
  },
  controlBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.surface1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderDefault,
    gap: 4,
  },
  controlLabel: {
    ...type.caption,
    color: colors.textSecondary,
  },
  stopButton: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.35,
    shadowRadius: 28,
    elevation: 12,
  },
});
