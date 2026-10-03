import { useEffect } from 'react';
import { ThemeIcon } from './components/Icons';
import { atlas } from './data';
import { useRoute, type Route } from './router';
import { useAppState } from './appState';
import { AppStateProvider } from './state';
import { MapView } from './views/MapView';
import { MethodView } from './views/MethodView';
import { PlannerView } from './views/PlannerView';
import { QuestionsView } from './views/QuestionsView';
import { TrendsView } from './views/TrendsView';

const NAV: { view: Route['view']; label: string }[] = [
  { view: 'map', label: 'Map' },
  { view: 'questions', label: 'Questions' },
  { view: 'trends', label: 'Trends' },
  { view: 'planner', label: 'Planner' },
  { view: 'method', label: 'Method' },
];

const THEME_LABEL = { system: 'Theme follows your system', dark: 'Dark theme', light: 'Light theme' } as const;

function TopBar({ route }: { route: Route }) {
  const { theme, cycleTheme } = useAppState();
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <a className="wordmark" href="#map" aria-label="GATE DA Atlas, home">
          <span className="wordmark__tiles" aria-hidden="true">
            <span style={{ background: 'var(--ramp-4)' }} />
            <span style={{ background: 'var(--ramp-2)' }} />
            <span style={{ background: 'var(--ramp-1)' }} />
            <span className="tile--never" />
          </span>
          GATE DA Atlas
        </a>
        <nav className="nav" aria-label="Main">
          {NAV.map((entry) => (
            <a key={entry.view} href={`#${entry.view}`} aria-current={route.view === entry.view ? 'page' : undefined}>
              {entry.label}
            </a>
          ))}
        </nav>
        <button className="theme-toggle" type="button" onClick={cycleTheme} aria-label={`${THEME_LABEL[theme]}. Change theme`} title={THEME_LABEL[theme]}>
          <ThemeIcon theme={theme} />
        </button>
      </div>
    </header>
  );
}

function CurrentView({ route }: { route: Route }) {
  switch (route.view) {
    case 'questions':
      return <QuestionsView questionId={route.question} />;
    case 'trends':
      return <TrendsView />;
    case 'planner':
      return <PlannerView />;
    case 'method':
      return <MethodView />;
    default:
      return <MapView itemId={route.item} />;
  }
}

function Shell() {
  const route = useRoute();
  // A new view starts at the top; moving within a view (another item or question) keeps the scroll.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.view]);
  return (
    <div className="shell">
      <TopBar route={route} />
      <main className="page" id="main">
        <CurrentView route={route} />
      </main>
      <footer className="footer">
        <div className="footer__inner">
          <span>Built from the official GATE DA papers, answer keys and syllabi of 2024–2026.</span>
          <span>Data generated {atlas.generated_at.slice(0, 10)}</span>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AppStateProvider>
      <Shell />
    </AppStateProvider>
  );
}
