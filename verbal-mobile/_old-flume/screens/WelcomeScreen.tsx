import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image,
  SafeAreaView, StatusBar, Platform,
} from 'react-native';
import { colors, fonts } from '../lib/theme';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  onSignIn: (method: 'google' | 'apple' | 'email') => void;
};

export default function WelcomeScreen({ onSignIn }: Props) {
  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={colors.heroBg} />
      <SafeAreaView style={s.safe}>
        {/* Header */}
        <View style={s.header}>
          <Text style={s.logo}>FLUME</Text>
        </View>

        {/* Hero */}
        <View style={s.hero}>
          <View style={s.iconContainer}>
            <Ionicons name="mic" size={64} color={colors.accent} />
          </View>
          <Text style={s.title}>Welcome to Flume</Text>
          <Text style={s.subtitle}>
            Voice typing that lands in your computer's clipboard.
          </Text>
        </View>

        {/* Sign-in Buttons */}
        <View style={s.buttons}>
          <TouchableOpacity
            style={[s.button, s.googleBtn]}
            onPress={() => onSignIn('google')}
          >
            <Ionicons name="logo-google" size={20} color="#fff" />
            <Text style={[s.btnText, s.btnTextLight]}>Continue with Google</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[s.button, s.appleBtn]}
            onPress={() => onSignIn('apple')}
          >
            <Ionicons name="logo-apple" size={20} color="#fff" />
            <Text style={[s.btnText, s.btnTextLight]}>Continue with Apple</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[s.button, s.emailBtn]}
            onPress={() => onSignIn('email')}
          >
            <Ionicons name="mail" size={20} color={colors.accent} />
            <Text style={[s.btnText, { color: colors.accent }]}>
              Use email instead
            </Text>
          </TouchableOpacity>

          <Text style={s.terms}>
            By continuing you agree to our{' '}
            <Text style={s.link}>Terms</Text> and{' '}
            <Text style={s.link}>Privacy</Text>.
          </Text>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.heroBg,
  },
  safe: {
    flex: 1,
    paddingHorizontal: 24,
  },
  header: {
    paddingTop: 20,
    paddingBottom: 40,
  },
  logo: {
    fontSize: 28,
    fontWeight: fonts.bold,
    color: colors.heroText,
    letterSpacing: 4,
  },
  hero: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 40,
  },
  iconContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: 'rgba(224, 90, 43, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 32,
  },
  title: {
    fontSize: 32,
    fontWeight: fonts.bold,
    color: colors.heroText,
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 18,
    fontWeight: fonts.light,
    color: colors.heroMuted,
    textAlign: 'center',
    lineHeight: 24,
  },
  buttons: {
    gap: 12,
    marginBottom: 40,
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
  },
  googleBtn: {
    backgroundColor: '#4285F4',
  },
  appleBtn: {
    backgroundColor: '#000',
  },
  emailBtn: {
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  btnText: {
    fontSize: 18,
    fontWeight: fonts.medium,
  },
  btnTextLight: {
    color: '#fff',
  },
  terms: {
    fontSize: 14,
    color: colors.heroMuted,
    textAlign: 'center',
    marginTop: 20,
    lineHeight: 18,
  },
  link: {
    color: colors.accent,
    textDecorationLine: 'underline',
  },
});
