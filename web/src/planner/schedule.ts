/**
 * Weekly calendar for a plan. Port of src/gate_atlas/planner/schedule.py: same constants,
 * same iteration order and tie-breaking, so both produce identical plans (see planner.test.ts).
 */
import { allocate, expectedSecured, marginalValue, masteryAfter, timeConstant } from './allocate';
import { addDays, daysBetween } from './dates';
import { maxBy, roundHalfEven, roundTo, sum } from './numbers';
import type { Plan, Profile, Unit, Week } from './types';

export const REVISION_SHARE = 0.15;
export const REVISION_OFFSETS_WEEKS = [1, 3, 7];
export const MAX_REVISION_SHARE_OF_WEEK = 0.4;
export const PARALLEL_UNITS = 3;
export const MOCK_TEST_HOURS = 3;
export const MOCK_REVIEW_HOURS = 2;
const MOCKS_BY_WEEKS_LEFT: Record<number, number> = { 4: 1, 3: 1, 2: 2, 1: 1 };
export const PYQ_PER_UNIT = 6;
const TARGETED_UNITS_PER_WEEK = 6;
export const HOUR_STEP = 0.5;
const EPS = 1e-9;
const DAYS_PER_WEEK = 7;
const EXTERNAL_MOCK = 'Full-length mock test (external)';

/** Round to the nearest HOUR_STEP (Python round semantics). */
export function roundHours(value: number): number {
  return roundHalfEven(value / HOUR_STEP) * HOUR_STEP;
}

/** Round down to whole HOUR_STEP blocks. */
export function roundDown(value: number): number {
  return Math.floor(value / HOUR_STEP + EPS) * HOUR_STEP;
}

/** Hours planned in a week. */
export function plannedHours(week: Week): number {
  return sum(Object.values(week.learning)) + sum(Object.values(week.revision)) + sum(Object.values(week.targeted)) + sum(week.mocks.map((m) => m.hours));
}

/** Calendar weeks from the start date to the day before the exam, with capacities. */
export function buildWeeks(profile: Profile): Week[] {
  const weeks: Week[] = [];
  const lastDay = addDays(profile.exam_date, -1);
  let cursor = profile.start_date;
  let index = 0;
  while (daysBetween(cursor, lastDay) >= 0) {
    const fullEnd = addDays(cursor, DAYS_PER_WEEK - 1);
    const end = daysBetween(fullEnd, lastDay) >= 0 ? fullEnd : lastDay;
    const days = daysBetween(cursor, end) + 1;
    const capacity = (profile.hours_per_day * days * profile.study_days_per_week) / DAYS_PER_WEEK;
    weeks.push({ index, start: cursor, end, capacity: roundTo(capacity, 2), phase: 'learn', learning: {}, revision: {}, targeted: {}, mocks: [], practice: {}, finished: [] });
    cursor = addDays(end, 1);
    index += 1;
  }
  const finalCount = Math.min(profile.final_weeks, Math.max(1, Math.floor(weeks.length / 4)));
  for (const week of weeks.slice(weeks.length - finalCount)) week.phase = 'final';
  return weeks;
}

/** Funded units in a prerequisite-respecting order, best marks-per-hour first. */
export function learningOrder(units: Unit[], hours: Record<string, number>, mastery: Record<string, number>): Unit[] {
  const funded = units.filter((u) => hours[u.id] > EPS);
  const fundedIds = new Set(funded.map((u) => u.id));
  const priority = new Map(funded.map((u) => [u.id, marginalValue(u, mastery[u.id])]));
  const done = new Set<string>();
  const order: Unit[] = [];
  while (order.length < funded.length) {
    let ready = funded.filter((u) => !done.has(u.id) && u.prereqs.every((p) => done.has(p) || !fundedIds.has(p)));
    if (ready.length === 0) ready = funded.filter((u) => !done.has(u.id));
    const best = maxBy(ready, (u) => priority.get(u.id)!);
    order.push(best);
    done.add(best.id);
  }
  return order;
}

/** Allocate hours and lay them out week by week. */
export function makePlan(units: Unit[], mastery: Record<string, number>, profile: Profile, notesIn: string[] = []): Plan {
  const notes = [...notesIn];
  const weeks = buildWeeks(profile);
  const learnWeeks = weeks.filter((w) => w.phase === 'learn');
  const finalWeeks = weeks.filter((w) => w.phase === 'final');
  const budget = sum(learnWeeks.map((w) => w.capacity)) / (1 + REVISION_SHARE);
  const allocation = allocate(units, mastery, budget);
  const hours: Record<string, number> = {};
  for (const [uid, h] of Object.entries(allocation.hours)) hours[uid] = roundHours(h);
  const byId = new Map(units.map((u) => [u.id, u]));

  const queue = learningOrder(units, hours, mastery);
  const remaining = new Map(queue.map((u) => [u.id, hours[u.id]]));
  const finished = new Set<string>();
  const revisionDue = new Map<number, Map<string, number>>();
  const finalRevision = new Map<string, number>();
  const active: string[] = [];
  const reserved = new Set(profile.reserve_papers_for_mocks);

  const canStart = (unit: Unit) => unit.prereqs.every((p) => finished.has(p) || !remaining.has(p));
  const refill = () => {
    while (active.length < PARALLEL_UNITS) {
      const sections = new Set(active.map((a) => byId.get(a)!.section_id));
      const ready = queue.filter((u) => !finished.has(u.id) && !active.includes(u.id) && canStart(u));
      if (ready.length === 0) return;
      const fresh = ready.filter((u) => !sections.has(u.section_id));
      active.push((fresh.length ? fresh : ready)[0].id);
    }
  };
  const finish = (unitId: string, week: Week) => {
    finished.add(unitId);
    active.splice(active.indexOf(unitId), 1);
    week.finished.push(unitId);
    week.practice[unitId] = byId.get(unitId)!.questions.filter((q) => !reserved.has(Number(q.slice(2, 6)))).slice(0, PYQ_PER_UNIT);
    const each = Math.max(HOUR_STEP, roundHours((REVISION_SHARE * hours[unitId]) / REVISION_OFFSETS_WEEKS.length));
    for (const offset of REVISION_OFFSETS_WEEKS) {
      const target = week.index + offset;
      if (target < weeks.length && weeks[target].phase === 'learn') {
        const due = revisionDue.get(target) ?? new Map<string, number>();
        due.set(unitId, (due.get(unitId) ?? 0) + each);
        revisionDue.set(target, due);
      } else {
        finalRevision.set(unitId, (finalRevision.get(unitId) ?? 0) + each);
      }
    }
  };
  const study = (week: Week, freeIn: number): number => {
    let free = freeIn;
    refill();
    while (free >= HOUR_STEP - EPS && active.length) {
      const share = Math.max(HOUR_STEP, roundDown(free / active.length));
      for (const unitId of [...active]) {
        const spend = Math.min(share, remaining.get(unitId)!, roundDown(free));
        if (spend < HOUR_STEP - EPS) continue;
        week.learning[unitId] = (week.learning[unitId] ?? 0) + spend;
        remaining.set(unitId, remaining.get(unitId)! - spend);
        free -= spend;
        if (remaining.get(unitId)! <= EPS) finish(unitId, week);
      }
      refill();
    }
    return free;
  };

  let carry = new Map<string, number>();
  for (const week of learnWeeks) {
    const due = new Map(carry);
    for (const [unitId, h] of revisionDue.get(week.index) ?? new Map<string, number>()) due.set(unitId, (due.get(unitId) ?? 0) + h);
    let room = roundDown(MAX_REVISION_SHARE_OF_WEEK * week.capacity);
    carry = new Map();
    for (const [unitId, h] of due) {
      const take = roundDown(Math.min(h, room));
      if (take > EPS) {
        week.revision[unitId] = take;
        room -= take;
      }
      if (h - take > EPS) carry.set(unitId, h - take);
    }
    study(week, week.capacity - sum(Object.values(week.revision)));
  }
  for (const [unitId, h] of carry) finalRevision.set(unitId, (finalRevision.get(unitId) ?? 0) + h);

  const leftover = [...remaining].filter(([, h]) => h > EPS).map(([uid]) => uid);
  if (leftover.length) notes.push(`${leftover.length} unit(s) spill into the mock phase: ${[...leftover].sort().join(', ')}`);

  const mockNames = profile.reserve_papers_for_mocks.map((year) => `GATE DA ${year} (official paper from this dataset)`);
  let nextMock = 0;
  const projected = new Map(units.map((u) => [u.id, masteryAfter(mastery[u.id], hours[u.id], timeConstant(u))]));
  for (const week of finalWeeks) {
    const weeksLeft = weeks.length - week.index;
    let free = week.capacity;
    const count = MOCKS_BY_WEEKS_LEFT[weeksLeft] ?? 1;
    for (let k = 0; k < count; k += 1) {
      if (free < MOCK_TEST_HOURS + MOCK_REVIEW_HOURS - EPS) break;
      const name = nextMock < mockNames.length ? mockNames[nextMock++] : EXTERNAL_MOCK;
      week.mocks.push({ name, hours: MOCK_TEST_HOURS + MOCK_REVIEW_HOURS });
      free -= MOCK_TEST_HOURS + MOCK_REVIEW_HOURS;
    }
    free = study(week, free);
    if (free > EPS) {
      const atRisk = new Map(units.map((u) => [u.id, u.expected_marks * (1 - projected.get(u.id)!) + (finalRevision.get(u.id) ?? 0)]));
      const focus = [...atRisk.keys()].sort((a, b) => atRisk.get(b)! - atRisk.get(a)!).slice(0, TARGETED_UNITS_PER_WEEK);
      const total = sum(focus.map((uid) => atRisk.get(uid)!));
      const shares = new Map(focus.map((uid) => [uid, roundDown((free * atRisk.get(uid)!) / total)]));
      shares.set(focus[0], shares.get(focus[0])! + roundDown(free - sum(shares.values())));
      for (const unitId of focus) {
        const share = shares.get(unitId)!;
        if (share >= HOUR_STEP) {
          week.targeted[unitId] = share;
          projected.set(unitId, masteryAfter(projected.get(unitId)!, share, timeConstant(byId.get(unitId)!)));
          finalRevision.set(unitId, Math.max(0, (finalRevision.get(unitId) ?? 0) - share));
        }
      }
    }
  }
  const unused = learnWeeks.filter((w) => w.capacity - plannedHours(w) > HOUR_STEP);
  if (allocation.lambda === 0 && unused.length) notes.push('There is more time than the plan needs; spare hours are left for extra practice and mocks.');
  return { profile, units, mastery, hours, lambda: allocation.lambda, weeks, notes };
}

/** Mastery after the planned learning hours. */
export function projectedMastery(plan: Plan): Record<string, number> {
  return Object.fromEntries(plan.units.map((u) => [u.id, masteryAfter(plan.mastery[u.id], plan.hours[u.id], timeConstant(u))]));
}

/** Model estimate of marks secured now or after the plan. */
export function securedMarks(plan: Plan, after: boolean): number {
  return expectedSecured(plan.units, plan.mastery, after ? plan.hours : undefined);
}
