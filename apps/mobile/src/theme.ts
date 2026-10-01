import { useColorScheme } from 'react-native';

import type { Priority, TicketStatus } from './lib/types';

const light = {
  scheme: 'light' as 'light' | 'dark',
  background: '#F4F5F7',
  card: '#FFFFFF',
  text: '#111827',
  muted: '#5B6472',
  border: '#E1E4EA',
  primary: '#1D4ED8',
  onPrimary: '#FFFFFF',
  danger: '#B91C1C',
  dangerSoft: '#FDECEC',
  inputBackground: '#FFFFFF',
};

const dark: typeof light = {
  scheme: 'dark',
  background: '#0F1115',
  card: '#1A1D23',
  text: '#F3F4F6',
  muted: '#A0A8B5',
  border: '#2B3038',
  primary: '#6C8DF5',
  onPrimary: '#0B1020',
  danger: '#F28B8B',
  dangerSoft: '#3A1F22',
  inputBackground: '#14171C',
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;

// Rozet metni bu renk, arka planı aynı rengin hafif saydam hâlidir. Karanlık temada koyu zemin
// üzerinde okunabilsin diye daha açık tonlar kullanılır.
const BADGE_COLORS = {
  light: {
    status: {
      new: '#64748B',
      needs_review: '#C2410C',
      assigned: '#1D4ED8',
      in_progress: '#7C3AED',
      resolved: '#047857',
      closed: '#475569',
    } satisfies Record<TicketStatus, string>,
    priority: { low: '#64748B', normal: '#1D4ED8', high: '#B91C1C' } satisfies Record<Priority, string>,
    category: '#0F766E',
    neutral: '#475569',
  },
  dark: {
    status: {
      new: '#A8B3C4',
      needs_review: '#FB923C',
      assigned: '#8AACFF',
      in_progress: '#B9A2FF',
      resolved: '#4ADE80',
      closed: '#A8B3C4',
    } satisfies Record<TicketStatus, string>,
    priority: { low: '#A8B3C4', normal: '#8AACFF', high: '#F87171' } satisfies Record<Priority, string>,
    category: '#2DD4BF',
    neutral: '#A8B3C4',
  },
};

export function useBadgeColors() {
  return BADGE_COLORS[useColorScheme() === 'dark' ? 'dark' : 'light'];
}
