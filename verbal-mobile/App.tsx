import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors } from './lib/theme';

import HomeScreen    from './screens/HomeScreen';
import HistoryScreen from './screens/HistoryScreen';
import CanvasScreen  from './screens/CanvasScreen';
import SettingsScreen from './screens/SettingsScreen';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
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
          <Tab.Screen name="History"  component={HistoryScreen} />
          <Tab.Screen name="Settings" component={SettingsScreen} />
        </Tab.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
