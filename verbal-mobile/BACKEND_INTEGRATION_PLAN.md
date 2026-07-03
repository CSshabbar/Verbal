# Backend Integration Plan - Flume UI

This document maps the existing backend (verbal-mobile/lib) to the Flume UI hooks.

## Existing Backend Components

### 1. Groq Transcription (`lib/groq.ts`)
- **Function**: `transcribeAudio(audioUri, apiKey)` - Uploads to Groq Whisper
- **Function**: `formatText(text, apiKey)` - Formats transcription
- **Function**: `formatNotes(text, apiKey)` - Formats notes with markdown
- **API**: Groq Cloud API (whisper-large-v3-turbo)

### 2. Supabase Client (`lib/supabase.ts`)
- **Tables**: transcriptions, notes, canvas, devices
- **Realtime**: Supabase channels for sync
- **Auth**: User sessions via Supabase

### 3. Storage (`lib/storage.ts`)
- **Functions**: getGroqKey, setGroqKey, getUserId, getDeviceName, etc.
- **Storage**: AsyncStorage (expo-secure-store)

### 4. Notes Storage (`lib/notesStorage.ts`)
- **Functions**: CRUD operations for notes with caching

### 5. Device Selector (`lib/useDeviceSelector.ts`)
- **Hook**: Manages device pairing and selection

### 6. Sync (`lib/useSync.ts`)
- **Hook**: Real-time sync via Supabase

## Mapping to Flume UI Hooks

### useAuth → Supabase Auth
**File**: `flume-ui/hooks/useAuth.ts`

Replace mock auth with Supabase:
```typescript
import { supabase } from '../lib/supabase';
import * as SecureStore from 'expo-secure-store';

// Use Supabase auth instead of Google OAuth
const { data: { session } } = await supabase.auth.getSession();
```

### useRecorder → Groq Transcription
**File**: `flume-ui/hooks/useRecorder.ts`

Wire to existing `transcribeAudio`:
```typescript
import { transcribeAudio } from '../lib/groq';
import { Audio } from 'expo-av';

// In stop():
const { uri } = await rec.stopAndUnloadAsync();
const apiKey = await getGroqKey();
const text = await transcribeAudio(uri, apiKey);
```

### useDevices → useDeviceSelector + Supabase
**File**: `flume-ui/hooks/useDevices.ts`

Use existing device management:
```typescript
import { useDeviceSelector } from '../lib/useDeviceSelector';
import { supabase } from '../lib/supabase';

// Query devices table
const { data } = await supabase.from('devices').select('*').eq('user_id', userId);
```

### useHistory → Supabase Transcriptions
**File**: `flume-ui/hooks/useHistory.ts`

Use existing storage:
```typescript
import { getHistory, addToHistory } from '../lib/storage';
import { supabase } from '../lib/supabase';

// Fetch from Supabase
const { data } = await supabase.from('transcriptions')
  .select('*')
  .eq('user_id', userId)
  .order('created_at', { ascending: false });
```

### useNotes → notesStorage + Supabase
**File**: `flume-ui/hooks/useNotes.ts`

Use existing notes system:
```typescript
import { getCachedNotes, addCachedNote, updateCachedNote } from '../lib/notesStorage';
import { supabase } from '../lib/supabase';

// Sync with Supabase notes table
```

### useCanvas → Supabase Canvas
**File**: `flume-ui/hooks/useCanvas.ts`

Wire to canvas table:
```typescript
import { supabase } from '../lib/supabase';

// Load canvas
const { data } = await supabase.from('canvas')
  .select('content, image_url')
  .eq('user_id', userId)
  .single();
```

## Implementation Steps

### Phase 1: Core Recording Flow (Priority)
1. ✅ Wire `useRecorder` to Groq API
2. ✅ Wire `useHistory` to Supabase transcriptions
3. ✅ Wire `useAuth` to Supabase auth (or keep mock for now)

### Phase 2: Device Management
1. ✅ Wire `useDevices` to Supabase devices table
2. ✅ Integrate with existing `useDeviceSelector`
3. ✅ Add device presence detection

### Phase 3: Notes & Canvas
1. ✅ Wire `useNotes` to existing notes system
2. ✅ Wire `useCanvas` to Supabase canvas table
3. ✅ Add image upload support

## File Structure

```
verbal-mobile/
├── flume-ui/              # Design system (DO NOT EDIT)
│   ├── hooks/            # ← WIRE BACKEND HERE
│   ├── screens/
│   ├── components/
│   └── theme/
├── lib/                   # Existing backend
│   ├── groq.ts           # Transcription API
│   ├── supabase.ts       # Database client
│   ├── storage.ts        # AsyncStorage
│   ├── notesStorage.ts   # Notes CRUD
│   ├── useDeviceSelector.ts
│   └── useSync.ts
└── App.tsx               # Mount point
```

## Key Decision: Keep Existing or Migrate?

**Recommendation**: Keep existing backend in `lib/` and wire Flume UI hooks to it.

**Why**:
- Existing backend is proven and working
- Supabase schema is already set up
- Groq integration is tested
- Faster integration (no rewrite needed)

**Alternative**: Migrate everything to Flume UI structure (slower, more risk)

## Next Steps

1. Update each hook in `flume-ui/hooks/` to import from `../lib/`
2. Test each flow end-to-end
3. Add error handling
4. Add loading states
5. Test on device
