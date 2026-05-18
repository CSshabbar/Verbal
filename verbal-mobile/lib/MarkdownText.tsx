import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts } from './theme';

interface Props {
  children: string;
  style?: any;
  numberOfLines?: number;
}

export default function MarkdownText({ children: text, style, numberOfLines }: Props) {
  if (!text) return null;

  const lines: React.ReactNode[] = [];

  text.split('\n').forEach((rawLine, lineKey) => {
    let line = rawLine;
    const key = `${lineKey}-${text.length}`;

    // Code blocks
    if (line.startsWith('```')) {
      lines.push(<Text key={key} style={[st.code, style]}>{line.replace(/```/g, '')}</Text>);
      return;
    }

    // Headings
    if (line.startsWith('### ')) {
      const content = line.replace(/^### /, '');
      lines.push(<Text key={key} style={[st.h3, style]}>{content}</Text>);
      return;
    }
    if (line.startsWith('## ')) {
      const content = line.replace(/^## /, '');
      lines.push(<Text key={key} style={[st.h2, style]}>{content}</Text>);
      return;
    }
    if (line.startsWith('# ')) {
      const content = line.replace(/^# /, '');
      lines.push(<Text key={key} style={[st.h1, style]}>{content}</Text>);
      return;
    }

    // Checkbox
    if (line.trim().startsWith('- [ ]')) {
      line = '☐' + line.replace(/^- \[ \]/, '');
    } else if (line.trim().startsWith('- [x]')) {
      line = '☑' + line.replace(/^- \[x\]/, '');
    }

    // Inline formatting: bold, italic, inline code
    const parts = line.split(/(\*\*.*?\*\*|__.*?__|_.*?_|\*.*?\*|`.*?`)/g);

    lines.push(
      <Text key={key} style={[st.line, style]}>
        {parts.map((part, i) => {
          if (!part) return null;
          if (part.startsWith('**') && part.endsWith('**')) {
            return <Text key={i} style={st.bold}>{part.slice(2, -2)}</Text>;
          }
          if (part.startsWith('__') && part.endsWith('__')) {
            return <Text key={i} style={st.bold}>{part.slice(2, -2)}</Text>;
          }
          if (part.startsWith('`') && part.endsWith('`')) {
            return <Text key={i} style={st.code}>{part.slice(1, -1)}</Text>;
          }
          if ((part.startsWith('_') && part.endsWith('_')) || (part.startsWith('*') && part.endsWith('*'))) {
            return <Text key={i} style={st.italic}>{part.slice(1, -1)}</Text>;
          }
          return <Text key={i}>{part}</Text>;
        })}
      </Text>
    );
  });

  return (
    <View>
      <Text numberOfLines={numberOfLines} style={style}>
        {lines}
      </Text>
    </View>
  );
}

const st = StyleSheet.create({
  h1:     { fontSize: 22, fontWeight: fonts.bold, color: colors.cardText, marginTop: 12, marginBottom: 4 },
  h2:     { fontSize: 18, fontWeight: fonts.bold, color: colors.cardText, marginTop: 10, marginBottom: 3 },
  h3:     { fontSize: 15, fontWeight: fonts.semibold, color: colors.cardText, marginTop: 8, marginBottom: 2 },
  bold:   { fontWeight: fonts.bold as any },
  italic: { fontStyle: 'italic' as any },
  code:   { fontFamily: 'monospace', backgroundColor: colors.iconGray, paddingHorizontal: 4, borderRadius: 3, fontSize: 12 },
  line:   { fontSize: 15, color: colors.cardText, lineHeight: 24 },
});
