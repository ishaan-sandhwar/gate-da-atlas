/** How a syllabus item is shaded on the map for a chosen set of papers. */
import { atlas } from '../data';

export type Scope = 'all' | number;

export interface TileState {
  marks: number;
  secondary: number;
  level: 'never' | 'secondary' | 'l1' | 'l2' | 'l3' | 'l4';
}

const yearOf = (questionId: string) => Number(questionId.slice(2, 6));

/** Marks, secondary uses and shading level of an item within a scope. */
export function tileState(itemId: string, scope: Scope): TileState {
  const stats = atlas.items[itemId];
  const marks = scope === 'all' ? stats.marks.reduce((a, b) => a + b, 0) : stats.marks[atlas.years.indexOf(scope)];
  const secondary = stats.secondary_questions.filter((q) => scope === 'all' || yearOf(q) === scope).length;
  let level: TileState['level'];
  if (marks >= 9) level = 'l4';
  else if (marks >= 5) level = 'l3';
  else if (marks >= 3) level = 'l2';
  else if (marks >= 1) level = 'l1';
  else level = secondary > 0 ? 'secondary' : 'never';
  return { marks, secondary, level };
}

export function describeTile(label: string, state: TileState, scope: Scope): string {
  const where = scope === 'all' ? 'in 2024–2026' : `in ${scope}`;
  if (state.level === 'never') return `${label}: ${scope === 'all' ? 'never asked' : 'not asked'} ${where}`;
  if (state.level === 'secondary') return `${label}: no question of its own ${where}, needed in ${state.secondary} other question${state.secondary > 1 ? 's' : ''}`;
  return `${label}: ${state.marks} mark${state.marks > 1 ? 's' : ''} ${where}`;
}
