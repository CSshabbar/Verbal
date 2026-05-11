import { createClient } from '@supabase/supabase-js';

export const SUPABASE_URL = 'https://ovpcthjingugwvpxlsna.supabase.co';
export const SUPABASE_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export interface Transcription {
  id: string;
  user_id: string;
  device_id: string;
  device_name: string;
  text: string;
  created_at: string;
}
