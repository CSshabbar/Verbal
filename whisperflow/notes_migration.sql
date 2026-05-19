-- Run this in Supabase SQL Editor to create the notes table
CREATE TABLE IF NOT EXISTS public.notes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id TEXT NOT NULL,
  title TEXT DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  folder TEXT DEFAULT '',
  is_pinned BOOLEAN DEFAULT false,
  device_name TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notes_user_id ON public.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON public.notes(user_id, updated_at DESC);

-- Enable realtime on the notes table
ALTER PUBLICATION supabase_realtime ADD TABLE public.notes;
