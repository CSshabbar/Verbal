/**
 * MarkdownNote — a fresh, dependency-free markdown → React Native renderer for
 * the Notes v2 formatted-content view (NOTES_ENHANCEMENT_SWARM.md, Feature 3).
 *
 * Deliberately NOT a revival of the legacy `lib/MarkdownText.tsx` (which pulls in
 * the stale `lib/theme.ts`). Everything here is styled from `flume-ui/theme`
 * tokens only — no new colors.
 *
 * Scope (matches the desktop hand-rolled parser): ATX headings (#/##/###),
 * unordered bullets (- / *), GFM task-list items (- [ ] / - [x]) rendered as
 * real, interactive checkboxes, **bold** inline emphasis, and plain paragraphs.
 * Anything it doesn't recognise falls through as a paragraph so text is never
 * dropped (fail-closed).
 *
 * Checkbox interactivity: each task item reports its ORIGINAL source-line index
 * back via `onToggleLine`, so the parent can flip `- [ ]` ↔ `- [x]` on that exact
 * line of the underlying content and persist it. Each checkbox exposes a real
 * accessibility role/label/state for VoiceOver + TalkBack.
 */
import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Text } from './Text';
import { colors, fonts, pressedStyle } from '../theme';

type Block =
  | { kind: 'h1' | 'h2' | 'h3'; text: string }
  | { kind: 'bullet'; text: string }
  | { kind: 'checkbox'; text: string; checked: boolean; line: number }
  | { kind: 'paragraph'; text: string }
  | { kind: 'spacer' };

const CHECK_OPEN = /^\s*[-*]\s+\[\s\]\s+(.*)$/;
const CHECK_DONE = /^\s*[-*]\s+\[[xX]\]\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const H1 = /^#\s+(.*)$/;
const H2 = /^##\s+(.*)$/;
const H3 = /^###\s+(.*)$/;

function parse(content: string): Block[] {
  const lines = (content || '').split('\n');
  const blocks: Block[] = [];
  lines.forEach((raw, i) => {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) {
      // Collapse runs of blank lines into a single spacer.
      if (blocks.length && blocks[blocks.length - 1].kind !== 'spacer') blocks.push({ kind: 'spacer' });
      return;
    }
    let m: RegExpMatchArray | null;
    if ((m = line.match(CHECK_OPEN))) blocks.push({ kind: 'checkbox', text: m[1], checked: false, line: i });
    else if ((m = line.match(CHECK_DONE))) blocks.push({ kind: 'checkbox', text: m[1], checked: true, line: i });
    else if ((m = line.match(H3))) blocks.push({ kind: 'h3', text: m[1] });
    else if ((m = line.match(H2))) blocks.push({ kind: 'h2', text: m[1] });
    else if ((m = line.match(H1))) blocks.push({ kind: 'h1', text: m[1] });
    else if ((m = line.match(BULLET))) blocks.push({ kind: 'bullet', text: m[1] });
    else blocks.push({ kind: 'paragraph', text: line });
  });
  return blocks;
}

/** Render **bold** spans inline; everything else is plain body text. */
function inline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(s => s.length > 0);
  if (parts.length === 1 && !parts[0].startsWith('**')) return parts[0];
  return parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <Text key={i} style={{ fontFamily: fonts.semibold }}>{p.slice(2, -2)}</Text>
      : <Text key={i}>{p}</Text>,
  );
}

export type MarkdownNoteProps = {
  content: string;
  /** Called with the source-line index of a tapped checkbox. Omit to render read-only. */
  onToggleLine?: (lineIndex: number) => void;
};

export const MarkdownNote: React.FC<MarkdownNoteProps> = ({ content, onToggleLine }) => {
  const blocks = parse(content);
  return (
    <View>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case 'spacer':
            return <View key={i} style={{ height: 10 }} />;
          case 'h1':
            return <Text key={i} variant="subtitle" style={styles.h1}>{inline(b.text)}</Text>;
          case 'h2':
            return <Text key={i} style={styles.h2}>{inline(b.text)}</Text>;
          case 'h3':
            return <Text key={i} style={styles.h3}>{inline(b.text)}</Text>;
          case 'bullet':
            return (
              <View key={i} style={styles.row}>
                <Text style={styles.bulletDot} color={colors.textMuted}>•</Text>
                <Text variant="bodyXs" style={styles.rowText} color={colors.textSecondary}>{inline(b.text)}</Text>
              </View>
            );
          case 'checkbox': {
            const label = `${b.text}, ${b.checked ? 'checked' : 'not checked'}`;
            const Box = (
              <View style={[styles.box, b.checked && styles.boxChecked]}>
                {b.checked ? <Ionicons name="checkmark" size={14} color={colors.primaryInk} /> : null}
              </View>
            );
            const inner = (
              <>
                {Box}
                <Text
                  variant="bodyXs"
                  style={[styles.rowText, b.checked && styles.checkedText]}
                  color={b.checked ? colors.textMuted : colors.textSecondary}
                >
                  {inline(b.text)}
                </Text>
              </>
            );
            return onToggleLine ? (
              <Pressable
                key={i}
                onPress={() => onToggleLine(b.line)}
                style={({ pressed }) => [styles.row, pressed && pressedStyle]}
                hitSlop={6}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: b.checked }}
                accessibilityLabel={label}
              >
                {inner}
              </Pressable>
            ) : (
              <View
                key={i}
                style={styles.row}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: b.checked }}
                accessibilityLabel={label}
              >
                {inner}
              </View>
            );
          }
          case 'paragraph':
          default:
            return (
              <Text key={i} variant="bodyXs" style={styles.paragraph} color={colors.textSecondary}>
                {inline(b.text)}
              </Text>
            );
        }
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  h1: { marginTop: 8, marginBottom: 6 },
  h2: { fontFamily: fonts.semibold, fontSize: 18, lineHeight: 24, color: colors.textPrimary, marginTop: 10, marginBottom: 4 },
  h3: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 20, color: colors.textPrimary, marginTop: 8, marginBottom: 3 },
  paragraph: { marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 8, paddingVertical: 1 },
  rowText: { flex: 1 },
  bulletDot: { fontSize: 15, lineHeight: 21, width: 12, textAlign: 'center' },
  box: {
    width: 20, height: 20, borderRadius: 6,
    borderWidth: 1.5, borderColor: colors.borderStrong,
    alignItems: 'center', justifyContent: 'center',
    marginTop: 1,
  },
  boxChecked: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkedText: { textDecorationLine: 'line-through' },
});

export default MarkdownNote;
