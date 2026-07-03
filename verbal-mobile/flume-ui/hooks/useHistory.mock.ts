/**
 * useHistory — transcription history.
 * Wire to your persistent store (SQLite / WatermelonDB / your backend).
 */
import { useState } from 'react';

export type HistoryItem = {
  id: string;
  text: string;
  deviceTag: string;            // "MacBook", "Work PC", "Local"
  dayLabel: string;             // "Today" | "Yesterday" | "Monday" | "Jun 24"
  timeOfDay: string;            // "9:24 AM"
  relativeTime: string;         // "12 min ago"
  durationLabel: string;        // "14s"
  wordCount: number;
  audioUri?: string;
};

const MOCK: HistoryItem[] = [
  {
    id: 'h1',
    text: "Let's reschedule the design review to Thursday afternoon and pull in marketing for the second half.",
    deviceTag: 'MacBook',
    dayLabel: 'Today',
    timeOfDay: '9:24 AM',
    relativeTime: '12 min ago',
    durationLabel: '14s',
    wordCount: 38,
  },
  {
    id: 'h2',
    text: 'Reply to Sarah — yes I can join the call at noon and bring the proposal draft.',
    deviceTag: 'Work PC',
    dayLabel: 'Today',
    timeOfDay: '8:51 AM',
    relativeTime: '1 hour ago',
    durationLabel: '9s',
    wordCount: 22,
  },
  {
    id: 'h3',
    text: 'Grocery list — eggs, oat milk, bread, garlic, lemons, parmesan, coffee beans.',
    deviceTag: 'Local',
    dayLabel: 'Yesterday',
    timeOfDay: '6:12 PM',
    relativeTime: 'yesterday',
    durationLabel: '6s',
    wordCount: 14,
  },
  {
    id: 'h4',
    text: 'Long note on the new onboarding flow — three things I want to validate this sprint.',
    deviceTag: 'MacBook',
    dayLabel: 'Yesterday',
    timeOfDay: '2:08 PM',
    relativeTime: 'yesterday',
    durationLabel: '52s',
    wordCount: 120,
  },
];

export function useHistory() {
  const [items, setItems] = useState<HistoryItem[]>(MOCK);

  const add = (item: HistoryItem) => setItems(prev => [item, ...prev]);
  const remove = (id: string) => setItems(prev => prev.filter(i => i.id !== id));

  return { items, add, remove };
}
