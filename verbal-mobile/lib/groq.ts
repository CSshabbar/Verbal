const GROQ_API = 'https://api.groq.com/openai/v1';

export const NOTES_FORMATTER_PROMPT = `You are a NOTE FORMATTER, not an AI assistant.
You receive raw notes (often voice-transcribed) and output well-structured markdown.

DETECT the note's context and format accordingly:
- Brainstorming: Group related ideas under ## headings, use bullet points.
- Todo/Tasks: Format as - [ ] checklist items with clear action verbs.
- Meeting notes: Add ## Key Points, ## Action Items, ## Notes sections.
- Product ideas: Organize as ## Problem, ## Solution, ## Features.
- Code/Technical: Format with \`\`\` code blocks, separate ## Concepts.
- Journal/Personal: Gentle paragraph formatting, preserve voice.
- Study notes: ## Topics with sub-bullets, bold key terms.

RULES:
1. NEVER add, invent, or respond to the content. Only reformat.
2. Fix transcription artifacts (um, uh, repeated words).
3. Add markdown headers (##, ###) to organize sections.
4. Use **bold** for emphasis and key terms naturally.
5. Use bullet points (- ) for lists. Numbered lists (1. ) for steps.
6. Clean up punctuation and capitalization.
7. Keep the original meaning — DO NOT summarize or truncate.
8. Return ONLY the formatted markdown.`;

export async function transcribeAudio(
  audioUri: string,
  apiKey: string
): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'recording.m4a',
  } as any);
  formData.append('model', 'whisper-large-v3-turbo');
  formData.append('language', 'en');
  formData.append('temperature', '0');

  const res = await fetch(`${GROQ_API}/audio/transcriptions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Groq transcription failed: ${err}`);
  }

  const data = await res.json();
  return data.text?.trim() ?? '';
}

export async function formatText(
  text: string,
  apiKey: string
): Promise<string> {
  const SYSTEM = `You are a TEXT FORMATTER, not an AI assistant.
You receive raw voice transcription and output a formatted version.
NEVER add, invent, or respond to the content.
NEVER add headings unless the speaker said them word-for-word.
Only reformat: fix punctuation, capitalization, remove fillers (um, uh),
format lists when speaker says "number one/two", add paragraph breaks on topic changes.
Return ONLY the formatted text.`;

  const res = await fetch(`${GROQ_API}/chat/completions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'llama-3.3-70b-versatile',
      messages: [
        { role: 'system', content: SYSTEM },
        {
          role: 'user',
          content: `TRANSCRIPTION TO FORMAT:\n\`\`\`\n${text}\n\`\`\`\n\nOutput the formatted version only.`,
        },
      ],
      temperature: 0,
      max_tokens: 2048,
    }),
  });

  if (!res.ok) return text; // fallback to raw
  const data = await res.json();
  return data.choices?.[0]?.message?.content?.trim() ?? text;
}

export async function formatNotes(
  text: string,
  apiKey: string
): Promise<string> {
  const res = await fetch(`${GROQ_API}/chat/completions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'llama-3.3-70b-versatile',
      messages: [
        { role: 'system', content: NOTES_FORMATTER_PROMPT },
        { role: 'user', content: `NOTES TO FORMAT:\n\`\`\`\n${text}\n\`\`\`\n\nOutput the formatted markdown only.` },
      ],
      temperature: 0,
      max_tokens: 4096,
    }),
  });
  if (!res.ok) return text;
  const data = await res.json();
  return data.choices?.[0]?.message?.content?.trim() ?? text;
}
