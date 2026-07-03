import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Text, Button, LogoMark, GoogleG } from '../components';
import { colors, space } from '../theme';
import { useAuth } from '../hooks/useAuth';

/**
 * Screen 3a — Welcome / sign-in.
 * Solid bgScreen (no gradient, per the final flow).
 */
export const WelcomeScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const { signInWithGoogle, signInWithApple, signInWithEmail } = useAuth();

  return (
    <View
      style={[
        styles.root,
        {
          paddingTop: insets.top + 30,
          paddingBottom: insets.bottom + 30,
        },
      ]}
    >
      <View style={styles.top}>
        <LogoMark size={128} />
        <View style={{ alignItems: 'center', gap: 8 }}>
          <Text variant="displaySm" align="center">
            Welcome to Flume
          </Text>
          <Text variant="body" color={colors.textMuted} align="center" style={{ paddingHorizontal: 8 }}>
            Voice typing that lands in your computer's clipboard.
          </Text>
        </View>
      </View>

      <View style={{ gap: 10 }}>
        <Button
          label="Continue with Google"
          variant="primaryLight"
          icon={<GoogleG size={16} />}
          onPress={signInWithGoogle}
        />
        <Button label="Continue with Apple" variant="ghost" onPress={signInWithApple} />

        <Pressable
          onPress={signInWithEmail}
          style={({ pressed }) => [styles.textBtn, { opacity: pressed ? 0.7 : 1 }]}
        >
          <Text variant="buttonSm" color={colors.textSecondary}>Use email instead</Text>
        </Pressable>

        <Text variant="caption" color={colors.textDisabled} align="center" style={{ paddingHorizontal: 14, paddingTop: 6 }}>
          By continuing you agree to our{' '}
          <Text variant="caption" color={colors.textSecondary}>Terms</Text>
          {' '}and{' '}
          <Text variant="caption" color={colors.textSecondary}>Privacy</Text>.
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 22,
    justifyContent: 'space-between',
  },
  top: { gap: 22, alignItems: 'center', marginTop: 12 },
  textBtn: { alignItems: 'center', paddingVertical: 12 },
});

export default WelcomeScreen;
