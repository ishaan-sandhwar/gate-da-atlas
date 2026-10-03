/** Shared app state (context and hook); the provider lives in state.tsx. */
import { createContext, useContext } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

export interface AppState {
  itemFilter: string | null;
  setItemFilter: (item: string | null) => void;
  theme: ThemeChoice;
  cycleTheme: () => void;
}

export const AppStateContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const value = useContext(AppStateContext);
  if (!value) throw new Error('useAppState needs AppStateProvider');
  return value;
}
