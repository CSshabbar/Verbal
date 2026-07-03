import 'react-native-reanimated';
import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import {
  Geist_400Regular,
  Geist_500Medium,
  Geist_600SemiBold,
  Geist_700Bold,
} from '@expo-google-fonts/geist';
import {
  JetBrainsMono_500Medium,
  JetBrainsMono_600SemiBold,
} from '@expo-google-fonts/jetbrains-mono';

import { RootNavigator, colors } from './flume-ui';

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <View style={ebStyles.container}>
          <Text style={ebStyles.title}>Something went wrong</Text>
          <ScrollView style={ebStyles.scroll}>
            <Text style={ebStyles.error}>
              {this.state.error?.message ?? 'Unknown error'}
            </Text>
            <Text style={ebStyles.stack}>{this.state.error?.stack ?? ''}</Text>
          </ScrollView>
        </View>
      );
    }
    return this.props.children;
  }
}

const ebStyles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bgScreen, padding: 20, paddingTop: 80 },
  title: { fontSize: 24, fontWeight: '700', color: colors.primary, marginBottom: 16 },
  scroll: { flex: 1 },
  error: { fontSize: 16, color: colors.textPrimary, marginBottom: 12, lineHeight: 24 },
  stack: { fontSize: 11, color: colors.textMuted, fontFamily: 'monospace', lineHeight: 16 },
});

export default function App() {
  const [fontsLoaded] = useFonts({
    Geist_400Regular,
    Geist_500Medium,
    Geist_600SemiBold,
    Geist_700Bold,
    JetBrainsMono_500Medium,
    JetBrainsMono_600SemiBold,
  });

  if (!fontsLoaded) return null;

  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <RootNavigator />
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}
