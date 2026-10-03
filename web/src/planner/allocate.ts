/**
 * Mastery estimates and the hour allocation that maximises expected marks.
 * Port of src/gate_atlas/planner/allocate.py; see its docstring for the KKT derivation.
 */
import { sum } from './numbers';
import type { Profile, Unit } from './types';

export const TIME_CONSTANT_FRACTION = 0.5;
export const MASTERY_CAP = 0.95;
export const EVIDENCE_STRENGTH = 8;
const BISECTION_STEPS = 200;

export const LEVELS: Record<string, number> = {
  not_started: 0.05,
  weak: 0.2,
  basic: 0.35,
  okay: 0.5,
  good: 0.7,
  strong: 0.85,
};
const DEFAULT_LEVEL = 'basic';

/** Prior mastery from the most specific rating: unit > section > part > default. */
export function ratingMastery(profile: Profile, unit: Unit): number {
  for (const key of [unit.id, unit.section_id, unit.part, 'default']) {
    const level = profile.ratings[key];
    if (level !== undefined) {
      if (!(level in LEVELS)) throw new Error(`rating ${level} for ${key} is not a known level`);
      return LEVELS[level];
    }
  }
  return LEVELS[DEFAULT_LEVEL];
}

/** Learning-curve time constant T (hours). */
export function timeConstant(unit: Unit): number {
  return unit.hours * TIME_CONSTANT_FRACTION;
}

/** Mastery after `hours` of study from `start`: 1 - (1 - start) e^(-h/T). */
export function masteryAfter(start: number, hours: number, tau: number): number {
  return 1 - (1 - start) * Math.exp(-hours / tau);
}

/** Hours needed to reach MASTERY_CAP from `start`. */
export function hoursCap(start: number, tau: number): number {
  if (start >= MASTERY_CAP) return 0;
  return tau * Math.log((1 - start) / (1 - MASTERY_CAP));
}

/** Expected marks gained per extra hour after `hours` of study. */
export function marginalValue(unit: Unit, start: number, hours = 0): number {
  const tau = timeConstant(unit);
  return (unit.expected_marks * (1 - start) * Math.exp(-hours / tau)) / tau;
}

/** Current mastery: rating prior, then logged hours on the learning curve, then mock evidence (Beta counts). */
export function estimateMastery(units: Unit[], profile: Profile): { mastery: Record<string, number>; notes: string[] } {
  const byId = new Map(units.map((u) => [u.id, u]));
  const alpha = new Map<string, number>();
  const beta = new Map<string, number>();
  for (const unit of units) {
    const prior = ratingMastery(profile, unit);
    alpha.set(unit.id, prior * EVIDENCE_STRENGTH);
    beta.set(unit.id, (1 - prior) * EVIDENCE_STRENGTH);
  }
  const notes: string[] = [];
  for (const entry of profile.progress) {
    const unit = byId.get(entry.unit);
    if (!unit) throw new Error(`progress refers to unknown unit ${entry.unit}`);
    const a = alpha.get(unit.id)!;
    const b = beta.get(unit.id)!;
    const strength = a + b;
    const mean = masteryAfter(a / strength, entry.hours, timeConstant(unit));
    alpha.set(unit.id, mean * strength);
    beta.set(unit.id, (1 - mean) * strength);
    notes.push(`${unit.id}: +${entry.hours}h studied`);
  }
  const mocks = [...profile.mocks].sort((x, y) => String(x.date ?? '').localeCompare(String(y.date ?? '')));
  for (const mock of mocks) {
    for (const [key, [correct, attempted]] of Object.entries(mock.results)) {
      if (!(correct >= 0 && correct <= attempted)) throw new Error(`mock result for ${key} needs 0 <= correct <= attempted`);
      const direct = byId.get(key);
      const targets = direct ? [direct] : units.filter((u) => u.section_id === key);
      if (targets.length === 0) throw new Error(`mock result key ${key} is neither a unit nor a section id`);
      const total = sum(targets.map((u) => u.expected_marks));
      for (const unit of targets) {
        const share = total ? unit.expected_marks / total : 1 / targets.length;
        alpha.set(unit.id, alpha.get(unit.id)! + share * correct);
        beta.set(unit.id, beta.get(unit.id)! + share * (attempted - correct));
      }
      notes.push(`${mock.date ?? 'mock'}: ${key} ${correct}/${attempted}`);
    }
  }
  const mastery: Record<string, number> = {};
  for (const unit of units) mastery[unit.id] = alpha.get(unit.id)! / (alpha.get(unit.id)! + beta.get(unit.id)!);
  return { mastery, notes };
}

/** Hours per unit maximising expected marks for a learning budget; returns hours and lambda. */
export function allocate(units: Unit[], mastery: Record<string, number>, budget: number): { hours: Record<string, number>; lambda: number } {
  const caps: Record<string, number> = {};
  for (const unit of units) caps[unit.id] = hoursCap(mastery[unit.id], timeConstant(unit));
  if (budget <= 0) return { hours: Object.fromEntries(units.map((u) => [u.id, 0])), lambda: Infinity };
  if (sum(Object.values(caps)) <= budget) return { hours: { ...caps }, lambda: 0 };

  const hoursAt = (lam: number): Record<string, number> => {
    const out: Record<string, number> = {};
    for (const unit of units) {
      const firstHour = marginalValue(unit, mastery[unit.id]);
      const raw = firstHour > lam ? timeConstant(unit) * Math.log(firstHour / lam) : 0;
      out[unit.id] = Math.min(Math.max(raw, 0), caps[unit.id]);
    }
    return out;
  };

  let low = 1e-12;
  let high = Math.max(...units.map((u) => marginalValue(u, mastery[u.id])));
  for (let step = 0; step < BISECTION_STEPS; step += 1) {
    const middle = Math.sqrt(low * high);
    if (sum(Object.values(hoursAt(middle))) > budget) low = middle;
    else high = middle;
  }
  return { hours: hoursAt(high), lambda: high };
}

/** Model estimate of marks secured: expected marks times mastery (after optional hours). */
export function expectedSecured(units: Unit[], mastery: Record<string, number>, hours?: Record<string, number>): number {
  let total = 0;
  for (const unit of units) {
    let level = mastery[unit.id];
    if (hours) level = masteryAfter(level, hours[unit.id] ?? 0, timeConstant(unit));
    total += unit.expected_marks * level;
  }
  return total;
}
