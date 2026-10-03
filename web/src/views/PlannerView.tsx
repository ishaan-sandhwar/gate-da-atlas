import { Fragment, useEffect, useMemo, useState } from 'react';
import { TrashIcon } from '../components/Icons';
import { SHORT_SECTION, atlas, questionName } from '../data';
import { LEVELS, estimateMastery, marginalValue } from '../planner/allocate';
import { todayIso } from '../planner/dates';
import { planMarkdown } from '../planner/markdown';
import { MOCK_REVIEW_HOURS, MOCK_TEST_HOURS, makePlan, plannedHours, projectedMastery, securedMarks } from '../planner/schedule';
import type { Plan, Profile, Unit } from '../planner/types';
import { readStored, writeStored } from '../storage';

const STORE_KEY = 'gate-da-atlas:profile';
const LEVEL_NAMES: [string, string][] = [
  ['not_started', 'None'],
  ['weak', 'Weak'],
  ['basic', 'Basic'],
  ['okay', 'Okay'],
  ['good', 'Good'],
  ['strong', 'Strong'],
];
const SECTION_KEYS = ['DA.PS', 'DA.PD', 'DA.ML', 'DA.DB', 'DA.LA', 'DA.AI', 'DA.CO', 'GA'];
const units = atlas.units as Unit[];

/** The shipped example profile, starting today. */
function exampleProfile(): Profile {
  const today = todayIso();
  return {
    name: 'My GATE DA 2027 plan',
    exam_date: '2027-02-06',
    start_date: today < '2027-02-06' ? today : '2027-02-01',
    hours_per_day: 3,
    study_days_per_week: 6,
    final_weeks: 4,
    reserve_papers_for_mocks: [2026],
    ratings: { default: 'basic', 'DA.LA': 'good', 'DA.PD:Python programming': 'strong', 'DA.ML': 'okay', 'DA.DB': 'weak', 'DA.AI': 'not_started', GA: 'okay' },
    progress: [],
    mocks: [],
  };
}

function Levels({ value, onChange, label }: { value: string | undefined; onChange: (level: string) => void; label: string }) {
  return (
    <div className="levels" role="group" aria-label={label}>
      {LEVEL_NAMES.map(([level, name]) => (
        <button key={level} type="button" aria-pressed={value === level} onClick={() => onChange(level)} title={`${level === 'not_started' ? 'Not started' : name} (mastery ${LEVELS[level]})`}>
          {name}
        </button>
      ))}
    </div>
  );
}

/** "2026-10-03" -> "3 Oct". */
function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

function unitLabel(id: string): string {
  const unit = units.find((u) => u.id === id);
  return unit ? `${unit.title} (${unit.section_id.split('.')[1]})` : id;
}

function Setup({ profile, setProfile }: { profile: Profile; setProfile: (p: Profile) => void }) {
  const update = (patch: Partial<Profile>) => setProfile({ ...profile, ...patch });
  const rating = (key: string) => profile.ratings[key];
  const setRating = (key: string, level: string) => update({ ratings: { ...profile.ratings, [key]: level } });
  const sectionOptions = SECTION_KEYS.filter((k) => k !== 'GA');

  return (
    <form className="setup" onSubmit={(event) => event.preventDefault()} aria-label="Your setup">
      <h2 style={{ fontSize: 'var(--step-2)' }}>Your setup</h2>
      <div className="setup__row">
        <div className="field">
          <label htmlFor="p-exam">Exam date</label>
          <input id="p-exam" type="date" value={profile.exam_date} onChange={(e) => e.target.value && update({ exam_date: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="p-start">Start date</label>
          <input id="p-start" type="date" value={profile.start_date} onChange={(e) => e.target.value && update({ start_date: e.target.value })} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="p-hours">
          Hours a day: <span className="num">{profile.hours_per_day}</span>
        </label>
        <input id="p-hours" type="range" min={0.5} max={10} step={0.5} value={profile.hours_per_day} onChange={(e) => update({ hours_per_day: Number(e.target.value) })} />
      </div>
      <div className="field">
        <span className="field__label">Study days a week</span>
        <div className="segmented segmented--small" role="group" aria-label="Study days a week">
          {[3, 4, 5, 6, 7].map((d) => (
            <button key={d} type="button" aria-pressed={profile.study_days_per_week === d} onClick={() => update({ study_days_per_week: d })}>
              {d}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label">How well do you know each section?</span>
        <p className="note">Example ratings are filled in. Change them to yours; the plan updates as you click.</p>
      </div>
      {SECTION_KEYS.map((key) => (
        <div className="rating" key={key}>
          <div className="rating__name">
            <span>{key === 'GA' ? 'General Aptitude' : SHORT_SECTION[key]}</span>
          </div>
          <Levels label={`Level for ${key}`} value={rating(key) ?? rating('default')} onChange={(level) => setRating(key, level)} />
        </div>
      ))}

      <details>
        <summary className="field__label" style={{ cursor: 'pointer' }}>
          Fine-tune single units
        </summary>
        <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
          {units.map((unit) => (
            <div className="rating" key={unit.id}>
              <div className="rating__name">
                <span>{unitLabel(unit.id)}</span>
                {profile.ratings[unit.id] && (
                  <button
                    className="btn btn--quiet"
                    type="button"
                    style={{ padding: '0 6px', fontSize: '0.8rem' }}
                    onClick={() => {
                      const next = { ...profile.ratings };
                      delete next[unit.id];
                      update({ ratings: next });
                    }}
                  >
                    Use section level
                  </button>
                )}
              </div>
              <Levels
                label={`Level for ${unit.title}`}
                value={profile.ratings[unit.id] ?? profile.ratings[unit.section_id] ?? profile.ratings[unit.part] ?? profile.ratings.default}
                onChange={(level) => setRating(unit.id, level)}
              />
            </div>
          ))}
        </div>
      </details>

      <div className="logs">
        <span className="field__label">Mock test results</span>
        <p className="note">Correct and attempted questions per section. Each result shifts the plan toward where you lost marks.</p>
        {profile.mocks.map((mock, k) => {
          const [key, [correct, attempted]] = Object.entries(mock.results)[0] ?? ['DA.PS', [0, 0]];
          const setMock = (nextKey: string, c: number, a: number) => {
            const mocks = [...profile.mocks];
            mocks[k] = { date: mock.date, results: { [nextKey]: [c, a] } };
            update({ mocks });
          };
          return (
            <div className="log-row" key={k}>
              <select aria-label="Section" value={key} onChange={(e) => setMock(e.target.value, correct, attempted)}>
                {sectionOptions.map((s) => (
                  <option key={s} value={s}>
                    {SHORT_SECTION[s]}
                  </option>
                ))}
              </select>
              <input aria-label="Correct" type="number" min={0} value={correct} onChange={(e) => setMock(key, Math.max(0, Number(e.target.value)), Math.max(attempted, Number(e.target.value)))} />
              <input aria-label="Attempted" type="number" min={0} value={attempted} onChange={(e) => setMock(key, Math.min(correct, Number(e.target.value)), Math.max(0, Number(e.target.value)))} />
              <button className="icon-btn" type="button" aria-label="Remove this result" onClick={() => update({ mocks: profile.mocks.filter((_, j) => j !== k) })}>
                <TrashIcon />
              </button>
            </div>
          );
        })}
        <button className="btn btn--quiet" type="button" onClick={() => update({ mocks: [...profile.mocks, { date: todayIso(), results: { 'DA.PS': [5, 10] } }] })}>
          Add a mock result
        </button>
      </div>

      <div className="logs">
        <span className="field__label">Hours already studied</span>
        {profile.progress.map((entry, k) => (
          <div className="log-row" key={k} style={{ gridTemplateColumns: '1fr 0.6fr auto' }}>
            <select
              aria-label="Unit"
              value={entry.unit}
              onChange={(e) => update({ progress: profile.progress.map((p, j) => (j === k ? { ...p, unit: e.target.value } : p)) })}
            >
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {unitLabel(u.id)}
                </option>
              ))}
            </select>
            <input
              aria-label="Hours"
              type="number"
              min={0}
              step={0.5}
              value={entry.hours}
              onChange={(e) => update({ progress: profile.progress.map((p, j) => (j === k ? { ...p, hours: Math.max(0, Number(e.target.value)) } : p)) })}
            />
            <button className="icon-btn" type="button" aria-label="Remove this entry" onClick={() => update({ progress: profile.progress.filter((_, j) => j !== k) })}>
              <TrashIcon />
            </button>
          </div>
        ))}
        <button className="btn btn--quiet" type="button" onClick={() => update({ progress: [...profile.progress, { unit: units[0].id, hours: 5 }] })}>
          Log study hours
        </button>
      </div>

      <div className="field">
        <span className="field__label">Keep these papers unseen for full mocks</span>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          {atlas.years.map((year) => (
            <label className="check" key={year}>
              <input
                type="checkbox"
                checked={profile.reserve_papers_for_mocks.includes(year)}
                onChange={(e) =>
                  update({
                    reserve_papers_for_mocks: e.target.checked
                      ? [...profile.reserve_papers_for_mocks, year].sort()
                      : profile.reserve_papers_for_mocks.filter((y) => y !== year),
                  })
                }
              />
              {year}
            </label>
          ))}
        </div>
      </div>
      <button className="btn btn--quiet" type="button" onClick={() => setProfile(exampleProfile())}>
        Reset to the example
      </button>
    </form>
  );
}

function PlanOutput({ plan, inputNotes }: { plan: Plan; inputNotes: number }) {
  const [open, setOpen] = useState<number | null>(0);
  const [copied, setCopied] = useState<string>('');
  const projected = projectedMastery(plan);
  const capacity = plan.weeks.reduce((a, w) => a + w.capacity, 0);
  const learn = plan.weeks.reduce((a, w) => a + Object.values(w.learning).reduce((x, y) => x + y, 0), 0);
  const revise = plan.weeks.reduce((a, w) => a + [...Object.values(w.revision), ...Object.values(w.targeted)].reduce((x, y) => x + y, 0), 0);
  const mocks = plan.weeks.reduce((a, w) => a + w.mocks.reduce((x, m) => x + m.hours, 0), 0);
  const total = learn + revise + mocks || 1;
  const funded = plan.units.filter((u) => plan.hours[u.id] > 0).sort((a, b) => plan.hours[b.id] - plan.hours[a.id]);
  const skipped = plan.units.filter((u) => plan.hours[u.id] === 0).sort((a, b) => marginalValue(b, plan.mastery[b.id]) - marginalValue(a, plan.mastery[a.id]));
  const maxHours = Math.max(...funded.map((u) => plan.hours[u.id]), 1);
  const maxCapacity = Math.max(...plan.weeks.map((w) => w.capacity), 1);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(planMarkdown(plan));
      setCopied('Copied the plan as Markdown.');
    } catch {
      setCopied('Copying is blocked here. Select the plan text instead.');
    }
  };

  return (
    <section className="plan-summary" aria-label="Your plan">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <h2 style={{ fontSize: 'var(--step-2)' }}>
          {plan.weeks.length} weeks, {Math.round(capacity)} hours
        </h2>
        <button className="btn btn--quiet" type="button" onClick={copy}>
          Copy plan as Markdown
        </button>
      </div>
      {copied && (
        <p className="note" role="status">
          {copied}
        </p>
      )}
      <div className="split" aria-hidden="true">
        <span style={{ width: `${(learn / total) * 100}%`, background: 'var(--phase-learn)' }} />
        <span style={{ width: `${(revise / total) * 100}%`, background: 'var(--phase-revise)' }} />
        <span style={{ width: `${(mocks / total) * 100}%`, background: 'var(--phase-mock)' }} />
      </div>
      <div className="split-legend">
        <span>
          <span className="dot" style={{ background: 'var(--phase-learn)' }} />
          Learning {Math.round(learn)} h
        </span>
        <span>
          <span className="dot" style={{ background: 'var(--phase-revise)' }} />
          Revision {Math.round(revise)} h
        </span>
        <span>
          <span className="dot" style={{ background: 'var(--phase-mock)' }} />
          Full mocks {Math.round(mocks)} h
        </span>
      </div>
      <p>
        The last hour planned is worth <strong className="num">{plan.lambda === 0 ? 'less than you have time for' : `${plan.lambda.toFixed(3)} marks`}</strong>
        {plan.lambda === 0 ? ': every unit fits.' : '. Every unit that gets time earns at least that much per hour; the skipped ones earn less.'} Model estimate of
        marks secured: <strong className="num">{Math.round(securedMarks(plan, false))}</strong> now, <strong className="num">{Math.round(securedMarks(plan, true))}</strong>{' '}
        after the plan. Use it to compare plans, not as a score prediction.
      </p>
      {plan.notes.slice(inputNotes).map((note) => (
        <p className="note" key={note}>
          {units.reduce((text, unit) => text.replaceAll(unit.id, unitLabel(unit.id)), note)}
        </p>
      ))}

      <div className="section-head" style={{ marginTop: 18 }}>
        <h2 style={{ fontSize: 'var(--step-1)' }}>Where the hours go</h2>
        <span className="muted">learning hours, and mastery now and after</span>
      </div>
      <div className="alloc">
        {funded.map((unit) => (
          <div className="alloc__row" key={unit.id}>
            <span>{unitLabel(unit.id)}</span>
            <span className="alloc__bar" aria-hidden="true">
              <span style={{ width: `${(plan.hours[unit.id] / maxHours) * 100}%` }} />
            </span>
            <span className="num">{plan.hours[unit.id]} h</span>
            <span className="num muted alloc__mastery">
              {Math.round(plan.mastery[unit.id] * 100)}% to {Math.round(projected[unit.id] * 100)}%
            </span>
          </div>
        ))}
      </div>
      {skipped.length > 0 && (
        <p className="skips">
          <strong>Strategic skips:</strong> {skipped.map((u) => unitLabel(u.id)).join(', ')}. They earn less per hour than the last unit planned;
          add them first if you find more time.
        </p>
      )}

      <div className="section-head" style={{ marginTop: 18 }}>
        <h2 style={{ fontSize: 'var(--step-1)' }}>Week by week</h2>
        <span className="muted">Select a week for details</span>
      </div>
      <div className="weeks">
        {plan.weeks.map((week) => {
          const learnH = Object.values(week.learning).reduce((a, b) => a + b, 0);
          const reviseH = [...Object.values(week.revision), ...Object.values(week.targeted)].reduce((a, b) => a + b, 0);
          const mockH = week.mocks.reduce((a, m) => a + m.hours, 0);
          const scale = (h: number) => `${(h / maxCapacity) * 100}%`;
          const isOpen = open === week.index;
          return (
            <Fragment key={week.index}>
              <button
                className="week"
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : week.index)}
                aria-label={`Week ${week.index + 1}, ${week.start} to ${week.end}: ${learnH} hours learning, ${reviseH} hours revision, ${mockH} hours mocks`}
              >
                <span className="week__name">Week {week.index + 1}</span>
                <span className="week__dates num">
                  {shortDate(week.start)} to {shortDate(week.end)}
                </span>
                <span className="week__bar" aria-hidden="true">
                  {learnH > 0 && <span style={{ width: scale(learnH), background: 'var(--phase-learn)' }} />}
                  {reviseH > 0 && <span style={{ width: scale(reviseH), background: 'var(--phase-revise)' }} />}
                  {mockH > 0 && <span style={{ width: scale(mockH), background: 'var(--phase-mock)' }} />}
                </span>
              </button>
              {isOpen && (
                <div className="week-detail">
                  <div className="muted">
                    {shortDate(week.start)} to {shortDate(week.end)}: {plannedHours(week)} of {week.capacity} hours planned
                    {week.phase === 'final' ? ', mock phase' : ''}
                  </div>
                  {Object.keys(week.learning).length > 0 && (
                    <div>
                      <strong>Learn</strong>
                      <ul>
                        {Object.entries(week.learning).map(([id, h]) => (
                          <li key={id}>
                            {unitLabel(id)}: {h} h{week.finished.includes(id) ? ', finish it this week' : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {Object.keys(week.revision).length > 0 && (
                    <div>
                      <strong>Revise</strong> {Object.entries(week.revision).map(([id, h]) => `${unitLabel(id)} ${h} h`).join(', ')}
                    </div>
                  )}
                  {week.mocks.map((mock, k) => (
                    <div key={k}>
                      <strong>Mock</strong> {mock.name}: {MOCK_TEST_HOURS} h test, then {MOCK_REVIEW_HOURS} h going through every mistake
                    </div>
                  ))}
                  {Object.keys(week.targeted).length > 0 && (
                    <div>
                      <strong>Targeted revision</strong> {Object.entries(week.targeted).map(([id, h]) => `${unitLabel(id)} ${h} h`).join(', ')}
                    </div>
                  )}
                  {Object.entries(week.practice)
                    .filter(([, qs]) => qs.length)
                    .map(([id, qs]) => (
                      <div key={id}>
                        <strong>After {unitLabel(id)}, solve</strong>{' '}
                        {qs.map((q, k) => (
                          <Fragment key={q}>
                            {k > 0 && ', '}
                            <a href={`#q-${q}`}>{questionName(q)}</a>
                          </Fragment>
                        ))}
                      </div>
                    ))}
                </div>
              )}
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}

export function PlannerView() {
  const [profile, setProfileState] = useState<Profile>(() => readStored<Profile>(STORE_KEY, exampleProfile()));
  const setProfile = (next: Profile) => setProfileState(next);
  useEffect(() => {
    writeStored(STORE_KEY, profile);
  }, [profile]);

  const result = useMemo(() => {
    try {
      if (profile.exam_date <= profile.start_date) return { error: 'The exam date must come after the start date.' };
      const { mastery, notes } = estimateMastery(units, profile);
      return { plan: makePlan(units, mastery, profile, notes), inputNotes: notes.length };
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'This setup cannot be planned.' };
    }
  }, [profile]);

  return (
    <>
      <div className="hero" style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: 'var(--step-3)' }}>Planner</h1>
        <p className="lede">
          A week-by-week plan from your exam date, your hours and how well you know each section. Hours go first where the marks are high, you are
          weak and the topic is quick to learn. Log mock results and it replans.
        </p>
      </div>
      <div className="planner">
        <Setup profile={profile} setProfile={setProfile} />
        {'plan' in result && result.plan ? (
          <PlanOutput plan={result.plan} inputNotes={result.inputNotes} />
        ) : (
          <p className="result result--bad">{result.error}</p>
        )}
      </div>
    </>
  );
}
