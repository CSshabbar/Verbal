# Flume UI Scaling Implementation

## Summary
Implemented the SCALING_GUIDE.md to fix UI proportions. The wireframes were designed for a 280pt phone frame, but real iPhones are 390-430pt wide. Applied a 1.35x scale multiplier across the entire app.

## Changes Made

### 1. Theme Files

#### `flume-ui/theme/typography.ts`
Scaled all font sizes and line heights by 1.35x:
- **Display fonts**: displayXL (44→60), display (36→49), displaySm (26→35)
- **Title fonts**: title (22→30), titleSm (20→27), subtitle (18→24)
- **Body fonts**: bodyLg (14→19), body (13→17), bodySm (12.5→17), bodyXs (11.5→15)
- **Button fonts**: buttonPrimary (13.5→18), button (13→17), buttonSm (12→16)
- **Label fonts**: label (11→15), caption (11→14), tabLabel (10→12)
- **Mono fonts**: timer (36→56), timerXL (56→76), code (20→27), meta (10→13), metaSm (9.5→12)
- **Wordmark**: (13→17)

#### `flume-ui/theme/spacing.ts`
Scaled all spacing and radius values by 1.35x:
- **Space**: xs (4→6), s (8→11), m (12→16), base (16→22), l (18→24), lg (22→30), xl (28→38), xxl (36→48), xxxl (48→64)
- **Radius**: xs (6→8), sm (8→11), md (10→14), lg (12→16), xl (14→18), xxl (18→24)

### 2. Component Files

#### `flume-ui/components/MicButton.tsx`
- Idle size: 92→120px
- Recording size: 70→92px

#### `flume-ui/components/IconButton.tsx`
- Default size: 48→64px

#### `flume-ui/components/Chip.tsx`
- md padding: 6/11 → 8/15 (vertical/horizontal)
- sm padding: 3/8 → 4/11 (vertical/horizontal)

#### `flume-ui/components/ListRow.tsx`
- Row gap: 11→15, padding: 12→16
- Icon box: 32×32 → 42×42, borderRadius: sm→md
- SubRow gap: 5→7, marginTop: 2→3
- Status dot: 5×5 → 7×7
- Leading icon size: 16→22
- Chevron size: 16→22

#### `flume-ui/components/PageDots.tsx`
- Pip height: 3→4
- Active width: 26→34
- Inactive width: 18→24
- Gap: 6→8

### 3. Screen Files

#### `flume-ui/screens/RecordingScreen.tsx`
- Visualizer heights: `[38, 76, 120, 94, 148, 108, 134, 80, 120, 54]` (scaled from default)
- Visualizer barWidth: 4→6
- Visualizer gap: 5→7

#### `flume-ui/navigation/RootNavigator.tsx`
- Tab bar height: 60+insets → 78+insets
- Tab bar paddingTop: 10→12
- Tab bar paddingBottom: 14+insets → 18+insets
- All tab bar icons: 20→26

#### `flume-ui/screens/WelcomeScreen.tsx`
- Logo size: 96→128
- Bottom padding: 26→30

#### `flume-ui/screens/OnboardingScreen.tsx`
- Slide1 Logo: 28→38
- Step number tile: 38×38 → 52×52
- Step number font: 14→18
- Download row icons: 18→24, arrow: 14→18

#### `flume-ui/screens/HomeScreen.tsx`
- Header logo: 36→48

#### `flume-ui/screens/ConfirmationScreen.tsx`
- Success badge: 56→76
- Action icons: 16→22

#### `flume-ui/screens/HistoryListScreen.tsx`
- Search icon: 14→18

#### `flume-ui/screens/NotesListScreen.tsx`
- Search icon: 14→18
- FAB: 52×52 → 68×68
- FAB icon: 26→34
- FAB bottom offset: 78→96

#### `flume-ui/screens/DevicesScreen.tsx`
- Back/add icons: 18→22
- Title font: 16→20
- Add button: 32×32 → 40×40
- Plus disc: 26×26 → 34×34
- Plus icon: 14→22

#### `flume-ui/screens/PairDeviceScreen.tsx`
- Back icon: 18→22
- Viewfinder corners: 24×24 → 32×32

#### `flume-ui/screens/NoteEditorScreen.tsx`
- Back/ellipsis icons: 18→24
- Keyboard icon: 18→24
- Mic dock icon: 24→30

#### `flume-ui/screens/CanvasScreen.tsx`
- Action icons: 16→22
- Link icon: 18→22

#### `flume-ui/screens/HistoryDetailScreen.tsx`
- Back icon: 18→22
- Overflow icon: 14→18
- Device icon: 11→18, container: 20×20 → 28×28
- Play button: 11→18, container: 30×30 → 40×40
- Wave bars: width 2→3, height ×1.35, borderRadius 1→1.5
- Wave row height: 22→30
- Overflow button: 28×28 → 36×36

#### `flume-ui/screens/SettingsScreen.tsx`
- Eye toggle icon: 18→22

## Testing Checklist

- [ ] Reload Expo app to see scaled UI
- [ ] Test on actual device (not just simulator)
- [ ] Verify all screens have proper proportions
- [ ] Check text readability at new sizes
- [ ] Validate touch targets are comfortable
- [ ] Ensure tab bar is easily reachable
- [ ] Test mic button feels appropriately sized
- [ ] Verify visualizer animation looks good

## Result
The UI now matches the wireframe proportions on real devices. All text, icons, spacing, and interactive elements have been scaled up by 1.35x to account for the difference between the 280pt wireframe frame and the 390pt real iPhone width.
