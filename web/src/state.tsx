/** Provider for app-wide state: the question filter a map item can preset, and the theme. */
import { useEffect, useState, type ReactNode } from 'react';
import { AppStateContext, type ThemeChoice } from './appState';
import { readStored, writeStored } from './storage';

const THEME_KEY = 'gate-da-atlas:theme';
// A host page (such as an artifact viewer) may set its own theme; "system" hands control back to it.
const HOST_THEME = document.documentElement.getAttribute('data-theme');

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [itemFilter, setItemFilter] = useState<string | null>(null);
  const [theme, setTheme] = useState<ThemeChoice>(() => readStored<ThemeChoice>(THEME_KEY, 'system'));

  useEffect(() => {
    const root = document.documentElement;
    const next = theme === 'system' ? HOST_THEME : theme;
    if (next) root.setAttribute('data-theme', next);
    else root.removeAttribute('data-theme');
    writeStored(THEME_KEY, theme);
  }, [theme]);

  const cycleTheme = () => setTheme((t) => (t === 'system' ? 'dark' : t === 'dark' ? 'light' : 'system'));
  return <AppStateContext.Provider value={{ itemFilter, setItemFilter, theme, cycleTheme }}>{children}</AppStateContext.Provider>;
}
