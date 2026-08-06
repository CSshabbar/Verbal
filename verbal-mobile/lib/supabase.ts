import { createClient } from '@supabase/supabase-js';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState } from 'react-native';

export const SUPABASE_URL = 'https://ovpcthjingugwvpxlsna.supabase.co';
export const SUPABASE_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28';

// React Native: persist the session in AsyncStorage; don't read it from a URL
// (we exchange the OAuth code manually). PKCE is the default flow.
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
    flowType: 'pkce',
  },
});

// React Native requirement (IDI-166): the auto-refresh timer is throttled or
// suspended while the app is backgrounded, so a phone left closed >1h could
// resume with an expired token. Drive it from AppState per the supabase-js
// RN docs: refresh only while active.
AppState.addEventListener('change', (state) => {
  if (state === 'active') supabase.auth.startAutoRefresh();
  else supabase.auth.stopAutoRefresh();
});
supabase.auth.startAutoRefresh();

export interface Transcription {
  id: string;
  user_id: string;
  device_id: string;
  device_name: string;
  text: string;
  created_at: string;
}
