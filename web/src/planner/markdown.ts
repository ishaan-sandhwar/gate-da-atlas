/** Plain-text (Markdown) version of a plan, for copying into notes. */
import { marginalValue } from './allocate';
import { plannedHours, projectedMastery, securedMarks } from './schedule';
import type { Plan } from './types';

const hours = (h: number) => `${Number(h.toFixed(1))} h`;
const pct = (v: number) => `${Math.round(v * 100)}%`;

export function planMarkdown(plan: Plan): string {
  const byId = new Map(plan.units.map((u) => [u.id, u]));
  const label = (id: string) => {
    const unit = byId.get(id)!;
    return `${unit.title} (${unit.section_id.split('.')[1]})`;
  };
  const projected = projectedMastery(plan);
  const capacity = plan.weeks.reduce((a, w) => a + w.capacity, 0);
  const lines = [
    `# ${plan.profile.name}`,
    '',
    `Exam ${plan.profile.exam_date}, start ${plan.profile.start_date}, ${plan.profile.hours_per_day} h a day, ${plan.profile.study_days_per_week} days a week, ${plan.weeks.length} weeks, ${Math.round(capacity)} h available.`,
    `Value of the last planned hour: ${plan.lambda.toFixed(3)} marks. Model estimate of marks secured: ${Math.round(securedMarks(plan, false))} now, ${Math.round(securedMarks(plan, true))} after the plan (a yardstick, not a score prediction).`,
    '',
    '## Where the hours go',
    '',
    ...plan.units
      .filter((u) => plan.hours[u.id] > 0)
      .sort((a, b) => plan.hours[b.id] - plan.hours[a.id])
      .map((u) => `- ${label(u.id)}: ${hours(plan.hours[u.id])}, mastery ${pct(plan.mastery[u.id])} → ${pct(projected[u.id])}`),
    '',
    '## Strategic skips',
    '',
    ...plan.units
      .filter((u) => plan.hours[u.id] === 0)
      .sort((a, b) => marginalValue(b, plan.mastery[b.id]) - marginalValue(a, plan.mastery[a.id]))
      .map((u) => `- ${label(u.id)}`),
    '',
    '## Week by week',
    '',
  ];
  for (const week of plan.weeks) {
    lines.push(`### Week ${week.index + 1} (${week.start} to ${week.end}), ${hours(plannedHours(week))} of ${hours(week.capacity)}`);
    const learn = Object.entries(week.learning).map(([id, h]) => `${label(id)} ${hours(h)}`);
    if (learn.length) lines.push(`- Learn: ${learn.join(', ')}`);
    const revise = Object.entries(week.revision).map(([id, h]) => `${label(id)} ${hours(h)}`);
    if (revise.length) lines.push(`- Revise: ${revise.join(', ')}`);
    for (const mock of week.mocks) lines.push(`- Mock: ${mock.name} (3 h test + 2 h review)`);
    const targeted = Object.entries(week.targeted).map(([id, h]) => `${label(id)} ${hours(h)}`);
    if (targeted.length) lines.push(`- Targeted revision: ${targeted.join(', ')}`);
    for (const [id, qs] of Object.entries(week.practice)) if (qs.length) lines.push(`- After ${label(id)}, solve: ${qs.join(', ')}`);
    lines.push('');
  }
  return lines.join('\n');
}
