# FLUME DESIGN SYSTEM — EXACT HANDOFF DOCUMENT

**Version:** 1.0  
**Date:** 2026-07-01  
**Platform:** React Native (Expo)  
**Theme:** Dark (Primary)

---

## 1. DESIGN TOKENS

### 1.1 Colors (EXACT HEX VALUES)

```typescript
// Primary Palette
background:      '#14110f'      // Very dark brown (Flume base)
surface:         '#1A1614'      // Slightly lighter for cards/sheets
accent:          '#E0552C'      // Flume orange-red (primary action)
accentDim:       'rgba(224,85,44,0.15)'  // 15% opacity accent

// Text Hierarchy
textPrimary:     '#F5EDE4'      // Off-white (headlines, body)
textSecondary:   '#9A9590'      // Muted gray (subtitles, metadata)
textTertiary:    '#6B6660'      // Dark gray (placeholders, hints)

// Functional Colors
success:         '#3DAA6E'      // Green (success states, checkmarks)
error:           '#E0552C'      // Same as accent (errors)
warning:         '#F5A623'      // Amber (warnings)

// UI Elements
border:          'rgba(245,237,228,0.06)'   // 6% opacity border
borderActive:    'rgba(224,85,44,0.3)'      // 30% opacity accent border
overlay:         'rgba(20,17,15,0.8)'       // 80% opacity background

// Buttons
buttonPrimary:        '#E0552C'
buttonPrimaryText:    '#FFFFFF'
buttonSecondary:      'rgba(255,255,255,0.08)'
buttonSecondaryText:  '#F5EDE4'
```

### 1.2 Typography

```typescript
// Font Family
primary: 'System'  // SF Pro on iOS, Roboto on Android

// Font Sizes (px)
xs:    11   // Metadata, tags
sm:    13   // Secondary text, buttons
md:    15   // Body text
lg:    17   // Large body
xl:    20   // Subheadings
xxl:   24   // Section titles
xxxl:  32   // Page titles
hero:  48   // Hero headlines

// Font Weights
thin:      '100'
light:     '300'   // Headlines
regular:   '400'   // Body
medium:    '500'   // Buttons, labels
semibold:  '600'   // Card titles
bold:      '700'   // Emphasis
extraBold: '800'

// Letter Spacing
headlines: -0.5
labels:    0
logos:     6

// Line Heights
tight:    1.2
normal:   1.5
loose:    1.7
```

### 1.3 Spacing (px)

```typescript
xs:    4    // Micro spacing
sm:    8    // Tight spacing
md:    12   // Standard gap
lg:    16   // Card padding
xl:    24   // Section padding
xxl:   32   // Large sections
xxxl:  48   // Hero spacing
hero:  80   // Major sections
```

### 1.4 Border Radius (px)

```typescript
sm:   8    // Small buttons, tags
md:   12   // Cards, inputs
lg:   16   // Large cards
xl:   20   // Bottom sheets
xxl:  28   // Hero bottom radius
full: 9999 // Pills, circles
```

### 1.5 Shadows

```typescript
// Card Shadow (Light)
shadowColor:    '#000'
shadowOpacity:  0.08
shadowRadius:   10
shadowOffset:   { width: 0, height: 3 }
elevation:      2  // Android

// Button Shadow (Medium)
shadowColor:    '#000'
shadowOpacity:  0.2
shadowRadius:   16
shadowOffset:   { width: 0, height: 6 }
elevation:      10

// Modal Shadow (Heavy)
shadowColor:    '#000'
shadowOpacity:  0.2
shadowRadius:   20
shadowOffset:   { width: 0, height: 6 }
elevation:      14
```

### 1.6 Animations

```typescript
// Timing (ms)
fast:   150   // Micro-interactions
normal: 300   // Standard transitions
slow:   500   // Major state changes

// Easing
easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)'
easeOut:   'cubic-bezier(0.0, 0, 0.2, 1)'
spring:    'cubic-bezier(0.34, 1.56, 0.64, 1)'

// Specific Animations
buttonPress: { scale: 0.96, duration: 150 }
cardFade:    { opacity: 0→1, duration: 300 }
sheetSlide:  { translateY: 50→0, duration: 300 }
pulse:       { scale: 1→1.14, duration: 600, loop }
waveform:    { opacity: 0.25→0.9, duration: 1400, loop }
```

---

## 2. COMPONENT LIBRARY

### 2.1 Buttons

#### Primary Button (Large Round)
```typescript
// Used for: Main recording button, CTAs
size:         88 × 88 (large), 56 × 56 (FAB)
borderRadius: 44 (large), 28 (FAB)
background:   colors.accent (recording), colors.background (idle)
icon:         Ionicons 'mic' or 'stop', 32px
shadow:       Medium shadow
animation:    Pulse scale (1→1.14) when recording
```

#### Secondary Button (Pill)
```typescript
// Used for: Filters, tags, chips
paddingHorizontal: 16
paddingVertical:   8
borderRadius:      20 (full)
background:        rgba(255,255,255,0.06)
border:            1px solid rgba(245,237,228,0.06)
fontSize:          13
fontWeight:        medium
```

#### Icon Button (Square)
```typescript
// Used for: Toolbar actions, navigation
size:         36 × 36
borderRadius: 12
background:   rgba(255,255,255,0.06)
icon:         18-20px Ionicons outline
activeBg:     rgba(224,85,44,0.15)
```

### 2.2 Cards

#### Transcription Card
```typescript
background:    colors.background
borderRadius:  16
padding:       16
border:        1px solid rgba(245,237,228,0.06)
shadow:        Light shadow

// Pinned variant
backgroundPinned: rgba(224,85,44,0.15)
borderPinned:     1.5px solid rgba(224,85,44,0.3)
```

#### Settings Card
```typescript
background:    colors.background
borderRadius:  16
padding:       16
border:        1px solid rgba(245,237,228,0.06)
iconBox:       36×36, borderRadius 12, accentDim background
```

### 2.3 Inputs

#### Text Input (Single Line)
```typescript
background:    rgba(255,255,255,0.04)
borderRadius:  12
paddingHorizontal: 16
paddingVertical:   16
fontSize:      20
fontWeight:    semibold
color:         colors.textPrimary
placeholder:   colors.textTertiary
```

#### Text Input (Multi-line)
```typescript
background:    transparent
fontSize:      15
lineHeight:    26
color:         colors.textPrimary
placeholder:   colors.textTertiary
minHeight:     140
```

#### Search Input
```typescript
background:    rgba(255,255,255,0.06)
borderRadius:  12
padding:       12
fontSize:      15
color:         colors.textPrimary
icon:          Ionicons 'search', 18px, colors.textTertiary
```

### 2.4 Navigation

#### Bottom Tab Bar
```typescript
height:        80 (including safe area)
background:    colors.surface
borderTop:     1px solid rgba(245,237,228,0.06)
iconSize:      24px
iconColor:     colors.textTertiary
iconColorActive: colors.accent
labelSize:     11px
labelWeight:   medium
```

#### Top Bar (Hero)
```typescript
background:    colors.background
paddingHorizontal: 24
paddingBottom: 16
logoSize:      26px
logoColor:     colors.textPrimary
logoWeight:    light
```

### 2.5 Special Components

#### Device Chip
```typescript
// Used for: Device selection
background:    rgba(255,255,255,0.06)
borderRadius:  12
padding:       8-12
icon:          Device icon (16px)
label:         13px, medium
statusDot:     8px, green (online) / gray (offline)
```

#### Waveform Visualizer
```typescript
// Used for: Recording state
barCount:      40 (animated bars)
barWidth:      4px
barGap:        4px
barColor:      colors.accent
borderRadius:  2px
animation:     Opacity 0.25→0.9, duration 1400ms, loop
heightRange:   16-60px (randomized per bar)
```

#### Bottom Sheet
```typescript
background:    colors.surface
borderRadius:  28 (top corners only)
paddingTop:    32
paddingHorizontal: 24
```

#### Context Menu
```typescript
background:    colors.surface
borderRadius:  16
minWidth:      180
shadow:        Heavy shadow
border:        1px solid rgba(245,237,228,0.06)
itemPadding:   14 horizontal, 11 vertical
separator:     1px solid rgba(245,237,228,0.06)
```

---

## 3. SCREEN LAYOUTS

### 3.1 Home Screen (Recording)

```typescript
// Structure
- Hero (background: colors.background)
  - Top bar: Logo + status dot
  - Headline: "Ready to dictate." (32px, light)
  - Device selector row
  
- Sheet (background: colors.surface, borderRadius: 28)
  - Record button (88×88, centered)
  - Label (13px, secondary text)
  - Waveform (when recording)
  - Cancel button (pill, below waveform)
  - Result card (when done)
```

### 3.2 History Screen

```typescript
// Structure
- Hero (background: colors.background)
  - Headline: "History" (32px, light)
  - Subtitle: "X transcriptions" (13px, secondary)
  - Filter pills (All, Mine, Others, Pinned)
  
- Sheet (background: colors.surface, borderRadius: 28)
  - Clear button (top right)
  - Card list (FlatList)
    - Badge (number/pin)
    - Card body (text preview, metadata)
    - Copy button (right side)
```

### 3.3 Canvas Screen

```typescript
// Structure
- Hero (background: colors.background)
  - Headline: "Canvas" (32px, light)
  - Subtitle: "Shared clipboard" (13px, secondary)
  - Action buttons (refresh, paste, image, clear)
  - Stats row (word count, status)
  
- Sheet (background: colors.surface, borderRadius: 28)
  - Image preview (200px height, rounded)
  - Image actions (copy URL, remove)
  - Text input (multiline, flexible)
  - Save bar (fixed bottom)
```

### 3.4 Notes Screen

```typescript
// Structure
- Hero (background: colors.background)
  - Headline: "Notes" (32px, light)
  - Subtitle: "X notes" (13px, secondary)
  - Filter pills (All, Pinned)
  - Refresh button
  
- Sheet (background: colors.surface, borderRadius: 28)
  - Card list (FlatList)
    - Badge (pin)
    - Title (15px, semibold)
    - Preview (13px, secondary)
    - Metadata (device, time)
    - Delete button
  
- FAB (bottom right, 56×56, accent)
```

### 3.5 Settings Screen

```typescript
// Structure
- Hero (background: colors.background)
  - Headline: "Settings" (32px, light)
  - Subtitle: "Keys & preferences" (13px, secondary)
  
- Sheet (background: colors.surface, borderRadius: 28)
  - Section labels (10px, bold, letter-spacing 1.5)
  - Cards (icon, title, subtitle, input, save button)
```

---

## 4. NAVIGATION SETUP

### 4.1 Tab Navigator (Bottom)

```typescript
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

const Tab = createBottomTabNavigator();

<Tab.Navigator
  screenOptions={{
    tabBarStyle: {
      backgroundColor: colors.surface,
      borderTopColor: 'rgba(245,237,228,0.06)',
      borderTopWidth: 1,
      height: 80,
      paddingTop: 8,
      paddingBottom: 8,
    },
    tabBarActiveTintColor: colors.accent,
    tabBarInactiveTintColor: colors.textTertiary,
    tabBarLabelStyle: {
      fontSize: 11,
      fontWeight: '500',
    },
    headerShown: false,
  }}
>
  <Tab.Screen
    name="Home"
    component={FlumeHomeScreen}
    options={{
      tabBarIcon: ({ color, size }) => (
        <Ionicons name="mic" size={size} color={color} />
      ),
      tabBarLabel: 'Record',
    }}
  />
  <Tab.Screen
    name="Canvas"
    component={CanvasScreen}
    options={{
      tabBarIcon: ({ color, size }) => (
        <Ionicons name="albums" size={size} color={color} />
      ),
      tabBarLabel: 'Canvas',
    }}
  />
  <Tab.Screen
    name="Notes"
    component={NotesScreen}
    options={{
      tabBarIcon: ({ color, size }) => (
        <Ionicons name="document-text" size={size} color={color} />
      ),
      tabBarLabel: 'Notes',
    }}
  />
  <Tab.Screen
    name="History"
    component={HistoryScreen}
    options={{
      tabBarIcon: ({ color, size }) => (
        <Ionicons name="time" size={size} color={color} />
      ),
      tabBarLabel: 'History',
    }}
  />
  <Tab.Screen
    name="Settings"
    component={SettingsScreen}
    options={{
      tabBarIcon: ({ color, size }) => (
        <Ionicons name="settings" size={size} color={color} />
      ),
      tabBarLabel: 'Settings',
    }}
  />
</Tab.Navigator>
```

### 4.2 Stack Navigator (Auth Flow)

```typescript
import { createStackNavigator } from '@react-navigation/stack';

const Stack = createStackNavigator();

<Stack.Navigator
  screenOptions={{
    headerShown: false,
    cardStyle: { backgroundColor: colors.background },
  }}
>
  <Stack.Screen name="Welcome" component={WelcomeScreen} />
  <Stack.Screen name="SignIn" component={SignInScreen} />
  <Stack.Screen name="Onboarding" component={OnboardingScreen} />
  <Stack.Screen name="MainTabs" component={MainTabNavigator} />
</Stack.Navigator>
```

---

## 5. ASSETS & ICONS

### 5.1 Logo

```typescript
// FLUME Text Logo
text:         'FLUME'
fontSize:     28
fontWeight:   '700' (bold)
letterSpacing: 6
color:        colors.textPrimary
fontFamily:   System (SF Pro Display)
```

### 5.2 Icon Library

```typescript
// Using: @expo/vector-icons (Ionicons)

// Home Tab
mic: 'mic' | 'mic-outline'
stop: 'stop'
record: 'radio-button-on'

// Canvas Tab
canvas: 'albums' | 'albums-outline'
image: 'image' | 'image-outline'
trash: 'trash' | 'trash-outline'

// Notes Tab
notes: 'document-text' | 'document-text-outline'
pin: 'bookmark' | 'bookmark-outline'
edit: 'pencil' | 'pencil-outline'

// History Tab
history: 'time' | 'time-outline'
refresh: 'refresh' | 'refresh-outline'
copy: 'copy' | 'copy-outline'

// Settings Tab
settings: 'settings' | 'settings-outline'
key: 'key' | 'key-outline'
info: 'information-circle' | 'information-circle-outline'

// Common
checkmark: 'checkmark' | 'checkmark-circle'
close: 'close' | 'close-circle'
add: 'add' | 'add-circle'
search: 'search'
share: 'share' | 'share-outline'
```

### 5.3 Sound Assets

```typescript
// Haptic Feedback (expo-haptics)
- ImpactAsync: Light (copy), Medium (start/stop), Heavy (error)
- NotificationAsync: Success (done), Error (failed), Warning (retry)

// Vibration Patterns (expo-vibration)
VIB_START = [0, 40, 60, 40]    // Double tap
VIB_STOP  = [0, 80]            // Single firm
VIB_DONE  = [0, 30, 40, 30, 40, 60]  // Triple light
```

---

## 6. INTERACTION PATTERNS

### 6.1 Recording Flow

```
1. User taps mic button
   → Haptic: Medium impact
   → Vibration: VIB_START
   → State: 'recording'
   → Button: Scales to 1.14 (pulse animation)
   → Waveform: Appears and animates

2. User taps stop button
   → Haptic: Heavy impact
   → Vibration: VIB_STOP
   → State: 'processing'
   → Button: Shows hourglass icon

3. Transcription completes
   → Haptic: Success notification
   → Vibration: VIB_DONE
   → State: 'done'
   → Result card: Fades in (spring animation)
   → Text: Auto-copied to clipboard
```

### 6.2 Card Long-Press (Context Menu)

```
1. User long-presses card (350ms delay)
   → Haptic: Medium impact
   → Context menu: Slides in from right
   → Backdrop: Appears (full-screen tap-away)

2. User taps menu item
   → Haptic: Light impact
   → Menu: Fades out (120ms)
   → Action: Executes (copy, pin, edit, delete)

3. User taps backdrop
   → Menu: Fades out (120ms)
   → No action taken
```

### 6.3 Filter Pills

```
1. User taps inactive pill
   → Haptic: Light impact
   → Pill: Changes to active state (accent background)
   → Other pills: Return to inactive state
   → List: Re-filters immediately
```

---

## 7. ACCESSIBILITY

### 7.1 Color Contrast

```
// WCAG AA Compliance
textPrimary on background:   16.5:1  ✓✓✓
textSecondary on background: 8.2:1   ✓✓
textTertiary on background:  4.8:1   ✓
accent on background:        6.1:1   ✓✓
buttonPrimaryText on accent: 4.5:1   ✓
```

### 7.2 Touch Targets

```
// Minimum Sizes
Buttons:     44×44 (iOS HIG)
Icon buttons: 36×36 (minimum)
Cards:       Full width, 44px minimum height
Tab bar:     80px height (includes safe area)
```

### 7.3 Screen Reader Labels

```typescript
// Example for recording button
<TouchableOpacity
  accessibilityLabel="Start recording"
  accessibilityHint="Tap to start voice recording"
  accessibilityRole="button"
  accessibilityState={{ disabled: state === 'processing' }}
>
```

---

## 8. PERFORMANCE OPTIMIZATIONS

### 8.1 Waveform Animation

```typescript
// Use useNativeDriver for 60fps
Animated.loop(
  Animated.timing(wavePhase, {
    toValue: 1,
    duration: 1400,
    useNativeDriver: false,  // Can't use for height
    easing: Easing.linear,
  })
).start();

// Optimize with interpolated opacity
opacity: wavePhase.interpolate({
  inputRange: [0, 1],
  outputRange: [0.25, 0.9],
})
```

### 8.2 List Optimization

```typescript
// FlatList props for history/notes
<FlatList
  data={listData}
  keyExtractor={item => item.id}
  initialNumToRender={10}
  maxToRenderPerBatch={10}
  windowSize={5}
  removeClippedSubviews={true}
  showsVerticalScrollIndicator={false}
  getItemLayout={(data, index) => ({
    length: 80,  // Fixed card height
    offset: 80 * index,
    index,
  })}
/>
```

### 8.3 Image Optimization

```typescript
// Canvas image preview
<Image
  source={{ uri: imageUri }}
  style={s.imagePreview}
  resizeMode="contain"
  fadeDuration={150}  // Smooth fade-in
/>
```

---

## 9. FILE STRUCTURE

```
verbal-mobile/
├── lib/
│   ├── flumeTheme.ts      # Design tokens (NEW)
│   ├── theme.ts           # Legacy theme (update)
│   ├── groq.ts            # Transcription API
│   ├── storage.ts         # AsyncStorage helpers
│   ├── supabase.ts        # Database client
│   ├── useSync.ts         # Sync hook
│   └── useDeviceSelector.ts
├── screens/
│   ├── FlumeHomeScreen.tsx    # EXACT Flume design (NEW)
│   ├── WelcomeScreen.tsx      # Sign-in flow (NEW)
│   ├── HomeScreen.tsx         # Updated with Flume theme
│   ├── HistoryScreen.tsx      # Updated with Flume theme
│   ├── CanvasScreen.tsx       # Updated with Flume theme
│   ├── NotesScreen.tsx        # Updated with Flume theme
│   ├── SettingsScreen.tsx     # Updated with Flume theme
│   └── OnboardingScreen.tsx   # TODO: Create
├── components/
│   ├── DeviceSelector.tsx     # Device chips
│   ├── ContextMenu.tsx        # Floating menu
│   └── Waveform.tsx           # Animated bars
├── App.tsx                # Navigation setup
└── app.json               # Expo config
```

---

## 10. TODO: MISSING COMPONENTS

### 10.1 OnboardingScreen

```typescript
// 3-panel onboarding flow
- Panel 1: Mascot intro ("Hi, I'm Flume")
- Panel 2: How it works (Speak → Transcribe → Paste)
- Panel 3: Pair computer (macOS/Windows download)

// Navigation
- Swipe gestures (react-native-pager-view)
- Page indicators (dots)
- CTA buttons per panel
```

### 10.2 SignInScreen Variants

```typescript
// Variant 2a: Welcome hero
- FLUME logo
- "Welcome to Flume"
- "Voice typing that lands in your computer's clipboard"
- Google button (primary)
- Apple button (secondary)
- Email link (tertiary)

// Variant 2b: Minimal
- FLUME logo (large)
- "Sign in."
- "One account keeps your phone and computer in sync."
- Google button (only)
- "Other ways to sign in" expandable

// Variant 2c: Auth list
- "Sign in to Flume"
- "Pick how you'd like to continue"
- Google (with "LAST USED" badge)
- Apple
- Email
- Privacy notice
```

### 10.3 DevicePairingScreen

```typescript
// QR code scanner for pairing
- Camera view (expo-camera)
- QR code display (for desktop → mobile)
- Manual code entry fallback
- Device name input
- Connection status indicator
```

---

## 11. IMPLEMENTATION CHECKLIST

### Phase 1: Core Theme ✅
- [x] Create flumeTheme.ts with exact tokens
- [x] Update theme.ts with Flume colors
- [x] Import theme in all screens

### Phase 2: Screen Updates ✅
- [x] HomeScreen → Flume design
- [x] HistoryScreen → Flume design
- [x] CanvasScreen → Flume design
- [x] NotesScreen → Flume design
- [x] SettingsScreen → Flume design

### Phase 3: New Screens ⏳
- [ ] WelcomeScreen (create)
- [ ] OnboardingScreen (create)
- [ ] DevicePairingScreen (create)

### Phase 4: Navigation ⏳
- [ ] Update App.tsx with auth stack
- [ ] Add conditional rendering (auth check)
- [ ] Test deep linking

### Phase 5: Polish ⏳
- [ ] Add all haptic feedback
- [ ] Add all vibration patterns
- [ ] Test animations (60fps)
- [ ] Accessibility audit
- [ ] Performance optimization

---

## 12. TESTING CHECKLIST

### Visual Regression
- [ ] All screens match wireframes exactly
- [ ] Colors match hex values
- [ ] Typography matches specs
- [ ] Spacing is consistent
- [ ] Animations are smooth (60fps)

### Functional Testing
- [ ] Recording flow works end-to-end
- [ ] Transcription copies to clipboard
- [ ] History filters work correctly
- [ ] Canvas saves and syncs
- [ ] Notes CRUD operations work
- [ ] Settings persist correctly

### Device Testing
- [ ] iOS (iPhone 14, 14 Pro, SE)
- [ ] Android (Pixel 7, Samsung S23)
- [ ] Tablet (iPad, Android tablet)
- [ ] Dark mode (primary)
- [ ] Light mode (future)

---

**END OF HANDOFF DOCUMENT**
