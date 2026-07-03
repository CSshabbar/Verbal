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
  };
  /** Settings — pushed from the Home header. */
  Settings: undefined;
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
};

export type HistoryStackParamList = {
  HistoryList: undefined;
  HistoryDetail: { itemId: string };
};

export type SettingsStackParamList = {
  Settings: undefined;
  Devices: undefined;
  PairDevice: undefined;
};
