import React from 'react';
import { View, StyleSheet, ImageBackground, Image } from 'react-native';
import { colors } from '../theme';

export type LogoMarkProps = {
  size?: number;
  /** True = no circular crop, render the asset square (for splash). */
  square?: boolean;
};

/**
 * The Flume cockatoo mark, circle-masked by default.
 * Asset lives at flume-ui/assets/flume-mark.png — already on a black background.
 */
export const LogoMark: React.FC<LogoMarkProps> = ({ size = 96, square = false }) => (
  <View
    style={[
      styles.wrap,
      {
        width: size,
        height: size,
        borderRadius: square ? 0 : size / 2,
      },
    ]}
  >
    <Image
      source={require('../assets/flume-mark.png')}
      style={{ width: size, height: size }}
      resizeMode="cover"
    />
  </View>
);

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: '#000',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default LogoMark;
