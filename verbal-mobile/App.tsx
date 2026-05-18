import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors } from './lib/theme';

import HomeScreen    from './screens/HomeScreen';
import HistoryScreen from './screens/HistoryScreen';
import CanvasScreen  from './screens/CanvasScreen';
import NotesScreen   from './screens/NotesScreen';
import SettingsScreen from './screens/SettingsScreen';

const Tab = createBottomTabNavigator();

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
            <Text style={ebStyles.stack}>
              {this.state.error?.stack ?? ''}
            </Text>
          </ScrollView>
        </View>
      );
    }
    return this.props.children;
  }
}

const ebStyles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1A1917', padding: 20, paddingTop: 80 },
  title:     { fontSize: 24, fontWeight: '700', color: '#E05A2B', marginBottom: 16 },
  scroll:    { flex: 1 },
  error:     { fontSize: 16, color: '#F2EFE9', marginBottom: 12, lineHeight: 24 },
  stack:     { fontSize: 11, color: '#7A7570', fontFamily: 'monospace', lineHeight: 16 },
});

export default function App() {
  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <NavigationContainer>
          <Tab.Navigator
            screenOptions={({ route }) => ({
              headerShown: false,
              tabBarStyle: {
                backgroundColor: colors.heroBg,
                borderTopColor: 'rgba(255,255,255,0.06)',
                borderTopWidth: 1,
                height: 84,
                paddingBottom: 24,
                paddingTop: 10,
              },
              tabBarActiveTintColor:   colors.accent,
              tabBarInactiveTintColor: colors.heroMuted,
              tabBarLabelStyle: { fontSize: 11, fontWeight: '500', marginTop: 2 },
              tabBarIcon: ({ focused, color }) => {
                const icons: Record<string, [string, string]> = {
                  Home:     ['mic',            'mic-outline'],
                  Canvas:   ['albums',         'albums-outline'],
                  Notes:    ['document-text',  'document-text-outline'],
                  History:  ['time',           'time-outline'],
                  Settings: ['settings',       'settings-outline'],
                };
                const [active, inactive] = icons[route.name] ?? ['ellipse', 'ellipse-outline'];
                return <Ionicons name={(focused ? active : inactive) as any} size={22} color={color} />;
              },
            })}
          >
            <Tab.Screen name="Home"     component={HomeScreen} />
            <Tab.Screen name="Canvas"   component={CanvasScreen} />
            <Tab.Screen name="Notes"    component={NotesScreen} />
            <Tab.Screen name="History"  component={HistoryScreen} />
            <Tab.Screen name="Settings" component={SettingsScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}
