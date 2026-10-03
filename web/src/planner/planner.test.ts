/**
 * Parity tests: the TypeScript planner must reproduce the Python planner's plans exactly.
 * Fixtures come from `python -m gate_atlas export-web` (src/planner/fixtures/plans.json).
 */
import { describe, expect, it } from 'vitest';
import fixtures from './fixtures/plans.json';
import { allocate, estimateMastery, hoursCap, marginalValue, timeConstant } from './allocate';
import { roundHalfEven } from './numbers';
import { makePlan, plannedHours } from './schedule';
import type { Profile, Unit } from './types';

const units = fixtures.units as Unit[];
const cases = fixtures.cases as unknown as Array<{
  profile: Profile;
  mastery: Record<string, number>;
  hours: Record<string, number>;
  lambda: number;
  weeks: Array<Record<string, unknown>>;
  notes: string[];
}>;

describe('numbers', () => {
  it('rounds half to even like Python', () => {
    expect([0.5, 1.5, 2.5, 3.5, 2.4, 2.6].map(roundHalfEven)).toEqual([0, 2, 2, 4, 2, 3]);
  });
});

describe.each(cases.map((c) => [c.profile.name, c] as const))('parity with Python: %s', (_name, fixture) => {
  const { mastery, notes } = estimateMastery(units, fixture.profile);
  const plan = makePlan(units, mastery, fixture.profile, notes);

  it('estimates the same mastery', () => {
    for (const [uid, value] of Object.entries(fixture.mastery)) expect(mastery[uid]).toBeCloseTo(value, 12);
  });

  it('allocates the same hours', () => {
    expect(plan.hours).toEqual(fixture.hours);
    expect(plan.lambda).toBeCloseTo(fixture.lambda, 9);
  });

  it('lays out the same weeks', () => {
    expect(plan.weeks.length).toBe(fixture.weeks.length);
    plan.weeks.forEach((week, k) => {
      const expected = fixture.weeks[k];
      expect(week.start).toBe(expected.start);
      expect(week.end).toBe(expected.end);
      expect(week.capacity).toBeCloseTo(expected.capacity as number, 9);
      expect(week.phase).toBe(expected.phase);
      expect(week.learning).toEqual(expected.learning);
      expect(week.revision).toEqual(expected.revision);
      expect(week.targeted).toEqual(expected.targeted);
      expect(week.mocks).toEqual(expected.mocks);
      expect(week.practice).toEqual(expected.practice);
      expect(week.finished).toEqual(expected.finished);
      expect(plannedHours(week)).toBeLessThanOrEqual(week.capacity + 1e-6);
    });
    expect(plan.notes).toEqual(fixture.notes);
  });
});

describe('allocation optimality (KKT)', () => {
  it('equalises marginal value across funded units', () => {
    const mastery = Object.fromEntries(units.map((u) => [u.id, 0.35]));
    const { hours, lambda } = allocate(units, mastery, 150);
    expect(Object.values(hours).reduce((a, b) => a + b, 0)).toBeCloseTo(150, 6);
    for (const unit of units) {
      const h = hours[unit.id];
      const cap = hoursCap(mastery[unit.id], timeConstant(unit));
      if (h > 1e-6 && h < cap - 1e-6) expect(marginalValue(unit, mastery[unit.id], h) / lambda).toBeCloseTo(1, 4);
      if (h <= 1e-9) expect(marginalValue(unit, mastery[unit.id])).toBeLessThanOrEqual(lambda + 1e-12);
    }
  });
});
