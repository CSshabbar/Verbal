# Flume UI Implementation Plan

## Current App Screens (verbal-mobile)
1. HomeScreen - Main recording interface
2. HistoryScreen - Transcription history
3. CanvasScreen - Canvas/whiteboard
4. NotesScreen - Notes management ⭐
5. SettingsScreen - App settings

## Flume Wireframes Analysis
- Modern dark theme (#14110f background, #E0552C accent)
- Clean minimalist design
- Tab-based navigation
- Focus on audio visualization

## Integration Strategy

### 1. Theme Adaptation
- Use existing verbal-mobile theme (lib/theme.ts)
- Keep colors: #1A1917 (bg), #E05A2B (accent), #F2EFE9 (text)
- Adopt Flume's layout patterns and spacing

### 2. Screen Mapping
- HomeScreen → Update with Flume's main recording UI
- HistoryScreen → Redesign with Flume's list style
- CanvasScreen → Keep existing functionality, update UI
- NotesScreen → CREATE NEW (in current app, not in wireframes)
- SettingsScreen → Keep existing, minor UI updates

### 3. New Components Needed
- AudioVisualizer (Flume-style waveform)
- RecordingButton (Flume's distinctive button)
- TabBar (Flume navigation)
- NoteCard (for Notes screen)

### 4. Navigation Structure
- Bottom tab bar (5 tabs)
  - Home
  - History
  - Canvas
  - Notes ⭐ (added)
  - Settings

## Implementation Priority
1. ✅ Core navigation structure
2. ✅ HomeScreen with audio visualization
3. ✅ HistoryScreen redesign
4. ✅ NotesScreen (from existing app)
5. ✅ CanvasScreen UI update
6. ✅ SettingsScreen polish
7. ✅ Shared components

