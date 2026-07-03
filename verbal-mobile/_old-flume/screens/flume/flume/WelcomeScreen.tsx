import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, type, space, radius } from '../../lib/flumeTokens';

export default function WelcomeScreen({ navigation }: { navigation: any }) {
  return (
    <View style={s.root}>
      <SafeAreaView style={s.safeArea} edges={['top']}>
        <ScrollView 
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {/* Logo and Title */}
          <View style={s.topGroup}>
            {/* Bird Logo Circle */}
            <View style={s.logoCircle}>
              <Text style={s.logoEmoji}>🐦</Text>
            </View>
            
            <Text style={s.title}>Welcome to Flume</Text>
            <Text style={s.subtitle}>
              Voice typing that lands in your computer's clipboard.
            </Text>
          </View>

          {/* Sign In Buttons */}
          <View style={s.buttonGroup}>
            {/* Google Button */}
            <TouchableOpacity 
              style={s.googleBtn}
              onPress={() => navigation.navigate('Onboarding')}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-google" size={16} color={colors.primaryInk} />
              <Text style={s.googleBtnText}>Continue with Google</Text>
            </TouchableOpacity>

            {/* Apple Button */}
            <TouchableOpacity 
              style={s.appleBtn}
              onPress={() => navigation.navigate('Onboarding')}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-apple" size={16} color={colors.textPrimary} />
              <Text style={s.appleBtnText}>Continue with Apple</Text>
            </TouchableOpacity>

            {/* Email Link */}
            <TouchableOpacity 
              style={s.emailBtn}
              onPress={() => navigation.navigate('Onboarding')}
              activeOpacity={0.7}
            >
              <Text style={s.emailBtnText}>Use email instead</Text>
            </TouchableOpacity>

            {/* Terms */}
            <Text style={s.termsText}>
              By continuing you agree to our{' '}
              <Text style={s.termsLink}>Terms</Text>
              {' '}and{' '}
              <Text style={s.termsLink}>Privacy</Text>.
            </Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
  },
  safeArea: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingTop: 30,
    paddingBottom: 26,
    paddingHorizontal: 22,
  },
  topGroup: {
    alignItems: 'center',
    marginTop: 12,
    marginBottom: 40,
  },
  logoCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 22,
    overflow: 'hidden',
  },
  logoEmoji: {
    fontSize: 48,
  },
  title: {
    ...type.displaySm,
    color: colors.textPrimary,
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    ...type.body,
    color: colors.textMuted,
    textAlign: 'center',
    maxWidth: 240,
  },
  buttonGroup: {
    gap: 10,
  },
  googleBtn: {
    backgroundColor: '#f5ede4',
    borderRadius: radius.xl,
    paddingVertical: 13,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  googleBtnText: {
    ...type.buttonPrimary,
    color: colors.primaryInk,
  },
  appleBtn: {
    backgroundColor: colors.surface2,
    borderRadius: radius.xl,
    paddingVertical: 13,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: colors.borderDefault,
  },
  appleBtnText: {
    ...type.buttonPrimary,
    color: colors.textPrimary,
  },
  emailBtn: {
    paddingVertical: 13,
    alignItems: 'center',
  },
  emailBtnText: {
    ...type.body,
    color: colors.textSecondary,
  },
  termsText: {
    ...type.bodyXs,
    color: colors.textDisabled,
    textAlign: 'center',
    marginTop: 8,
  },
  termsLink: {
    color: colors.textPrimary,
    opacity: 0.7,
  },
});
