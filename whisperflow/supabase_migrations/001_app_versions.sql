-- Run this in the Supabase SQL Editor to set up auto-updates

-- 1. Create the app_versions table
CREATE TABLE IF NOT EXISTS app_versions (
  id          BIGSERIAL PRIMARY KEY,
  platform    TEXT NOT NULL,          -- 'mac', 'win', 'ios'
  version     TEXT NOT NULL,          -- semver: '1.2.0'
  changelog   TEXT,
  file_url    TEXT NOT NULL,          -- Supabase Storage public URL
  file_hash   TEXT,                   -- SHA256 for integrity
  file_size   BIGINT,
  released_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(platform, version)
);

-- 2. Enable RLS
ALTER TABLE app_versions ENABLE ROW LEVEL SECURITY;

-- 3. Anyone can read versions (needed for auto-update)
CREATE POLICY "Versions are publicly readable"
  ON app_versions FOR SELECT
  USING (true);

-- 4. Only service_role can insert (use service_role key in release script)
-- No INSERT policy for anon - you'll use the service_role key when running release.sh

-- 5. Create the releases storage bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('releases', 'releases', true)
ON CONFLICT (id) DO NOTHING;

-- 6. Allow public read access to release files
CREATE POLICY "Release files are publicly readable"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'releases');
