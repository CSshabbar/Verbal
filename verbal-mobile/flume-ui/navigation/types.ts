import { HistoryItem } from '../hooks/useHistory';
import { Note } from '../hooks/useNotes';

/** Root stack — auth + onboarding + the main app shell. */
export type RootStackParamList = {
  Welcome: undefined;
  Onboarding: undefined;
  Main: undefined;
  /** Modal — opened from anywhere. */
  Recording: undefined;
  Confirmation: {
    transcript: string;
    deviceName: string;
    durationSeconds: number;
    wordCount: number;
    transcribeMs: number;
    /**
     * Truthful outcome (IDI-159 — the screen previously claimed "Pasted to X"
     * unconditionally, even for failures and with sync off):
     *  - 'sent'   → pushed to the selected target device (sync on + target set)
     *  - 'saved'  → saved to local history + clipboard only
     *  - 'failed' → transcription failed; audio kept for retry
     *  - 'empty'  → no speech detected
     */
    variant: 'sent' | 'saved' | 'failed' | 'empty';
  };
  /** Menu — the navigation hub, opened from the Home header ☰. */
  Menu: undefined;
};

/** Bottom tabs — mic is the center action (opens the Recording modal). */
export type TabsParamList = {
  HomeTab:     undefined;
  NotesTab:    undefined;
  RecordTab:   undefined;
  CanvasTab:   undefined;
  HistoryTab:  undefined;
};

/** Stacks inside each tab. */
export type NotesStackParamList = {
  NotesList: undefined;
  NoteEditor: { noteId: string | null };
  /** Meetings live inside Notes — read-only views of desktop-captured meetings. */
  MeetingList: undefined;
  MeetingDetail: { meetingId: string };
  MeetingPlayback: { meetingId: string };
  MeetingNotes: { meetingId: string };
  MeetingLive: { meetingId: string };
};

export type HistoryStackParamList = {
  HistoryList: undefined;
  HistoryDetail: { itemId: string };
};

export type MenuStackParamList = {
  Menu: undefined;
  Settings: undefined;
  Dictionary: undefined;
  Devices: undefined;
  PairDevice: undefined;
  Snippets: undefined;
};
