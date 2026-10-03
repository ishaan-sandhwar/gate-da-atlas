/**
 * Hash routing with plain tokens only (#map, #questions, #q-DA2025-Q31, #item-DA.PS.08),
 * because an artifact link only carries a bare #anchor.
 */
import { useEffect, useState } from 'react';

export type Route =
  | { view: 'map'; item?: string }
  | { view: 'questions'; question?: string }
  | { view: 'trends' }
  | { view: 'planner' }
  | { view: 'method' };

export function parseHash(hash: string): Route {
  const token = hash.replace(/^#/, '');
  if (token.startsWith('q-')) return { view: 'questions', question: token.slice(2) };
  if (token.startsWith('item-')) return { view: 'map', item: token.slice(5) };
  if (token === 'questions' || token === 'trends' || token === 'planner' || token === 'method') return { view: token };
  return { view: 'map' };
}

export function routeHash(route: Route): string {
  if (route.view === 'questions' && route.question) return `#q-${route.question}`;
  if (route.view === 'map' && route.item) return `#item-${route.item}`;
  return `#${route.view}`;
}

/** Current route, updated on hashchange. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export function navigate(route: Route): void {
  const next = routeHash(route);
  if (window.location.hash !== next) window.location.hash = next;
}
