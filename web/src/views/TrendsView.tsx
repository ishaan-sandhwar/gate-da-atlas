import { CoverageBars, DotIntervals, GroupedBars } from '../components/charts';
import { SHORT_SECTION, atlas, itemById } from '../data';
import type { SectionRow } from '../types';

const YEAR_COLORS = ['var(--ramp-1)', 'var(--ramp-2)', 'var(--ramp-4)'];
const TREND_TEXT = { rising: 'rising', falling: 'falling', stable: 'steady', mixed: 'swings' } as const;

function SectionTable({ rows }: { rows: SectionRow[] }) {
  const years = atlas.years;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Section</th>
            {years.map((y) => (
              <th className="num" key={y}>
                {y}
              </th>
            ))}
            <th className="num">Mean</th>
            <th className="num">Share</th>
            <th>Trend</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{SHORT_SECTION[row.section_id] ?? row.title}</td>
              {years.map((y) => (
                <td className="num" key={y}>
                  {row[`marks_${y}`]}
                </td>
              ))}
              <td className="num">{row.marks_mean.toFixed(1)}</td>
              <td className="num">{Math.round(row.share_of_part * 100)}%</td>
              <td>
                {TREND_TEXT[row.trend]} ({row.trend_marks_per_year > 0 ? '+' : ''}
                {row.trend_marks_per_year.toFixed(1)} a year)
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TrendsView() {
  const years = atlas.years;
  const da = atlas.sections.primary.filter((s) => s.part === 'DA').sort((a, b) => b.marks_mean - a.marks_mean);
  const ga = atlas.sections.primary.filter((s) => s.part === 'GA').sort((a, b) => b.marks_mean - a.marks_mean);

  const coverage = atlas.syllabus
    .find((p) => p.code === 'DA')!
    .sections.map((section) => {
      const never = section.items.filter((i) => atlas.items[i.id].status === 'never_asked').length;
      return { label: SHORT_SECTION[section.id], asked: section.items.length - never, never };
    })
    .sort((a, b) => b.never / (b.asked + b.never) - a.never / (a.asked + a.never));

  const neverBySection = atlas.syllabus.flatMap((part) =>
    part.sections
      .map((section) => ({ section, items: section.items.filter((i) => atlas.items[i.id].status === 'never_asked') }))
      .filter((group) => group.items.length > 0),
  );

  const forecastRows = Object.entries(atlas.items)
    .filter(([id]) => id.startsWith('DA.'))
    .sort((a, b) => b[1].forecast.expected_marks - a[1].forecast.expected_marks)
    .slice(0, 15)
    .map(([id, stats]) => {
      const perQuestion = stats.forecast.expected_marks / stats.forecast.expected_questions;
      const label = itemById.get(id)!.label;
      return {
        label,
        value: stats.forecast.expected_marks,
        low: stats.forecast.rate_low * perQuestion,
        high: stats.forecast.rate_high * perQuestion,
        note: `${label}: ${stats.forecast.expected_marks.toFixed(2)} marks expected, ${Math.round(stats.forecast.p_asked * 100)}% chance it appears`,
      };
    });

  const mix = new Map<string, Record<string, number>>();
  for (const row of atlas.type_mix.filter((r) => r.part === 'DA')) {
    const counts = mix.get(row.section_id) ?? { MCQ: 0, MSQ: 0, NAT: 0 };
    counts[row.type] += row.questions;
    mix.set(row.section_id, counts);
  }
  const backtest = atlas.forecast.backtest.DA;
  const pairs = atlas.cooccurrence.filter((p) => p.cross_section && p.item_a.startsWith('DA.') && p.item_b.startsWith('DA.')).slice(0, 10);

  return (
    <>
      <div className="hero" style={{ marginBottom: 6 }}>
        <h1 style={{ fontSize: 'var(--step-3)' }}>Trends</h1>
        <p className="lede">
          How the marks moved from {years[0]} to {years[years.length - 1]}, what has never been asked, and what the next paper is likely to hold.
          Three papers are a small sample, so read the trends as history.
        </p>
      </div>

      <div className="section-head">
        <h2>DA marks by section, per paper</h2>
        <span className="muted">Each paper has 85 DA marks</span>
      </div>
      <GroupedBars
        rows={da.map((s) => ({ label: SHORT_SECTION[s.section_id], values: years.map((y) => s[`marks_${y}`]) }))}
        series={years.map(String)}
        colors={YEAR_COLORS}
        unit="marks"
      />
      <details style={{ marginTop: 10 }}>
        <summary className="muted" style={{ cursor: 'pointer' }}>
          Show as a table
        </summary>
        <SectionTable rows={da} />
      </details>

      <div className="section-head">
        <h2>General Aptitude</h2>
        <span className="muted">15 marks a paper</span>
      </div>
      <SectionTable rows={ga} />

      <div className="section-head">
        <h2>How much of each section has been asked</h2>
      </div>
      <CoverageBars rows={coverage} />

      <div className="section-head">
        <h2>Topics never asked so far</h2>
        <span className="muted">with the forecast chance of appearing next time</span>
      </div>
      <div className="two-col">
        {neverBySection.map(({ section, items }) => (
          <div key={section.id}>
            <h3 style={{ fontSize: 'var(--step-1)', marginBottom: 6 }}>{SHORT_SECTION[section.id] ?? section.title}</h3>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {items.map((item) => (
                <a className="chip" key={item.id} href={`#item-${item.id}`}>
                  {item.label} <span className="num muted">{Math.round(atlas.items[item.id].forecast.p_asked * 100)}%</span>
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="section-head">
        <h2>Forecast for the next paper</h2>
        <span className="muted">Top 15 DA syllabus items by expected marks</span>
      </div>
      <DotIntervals rows={forecastRows} unit="marks" />
      <p className="note" style={{ marginTop: 8 }}>
        Dots are expected marks; lines are 80% intervals. The model is empirical Bayes: each item&rsquo;s yearly count is Poisson, with a Gamma prior
        centred on its section&rsquo;s rate. Items differ in size, so plan by section. In a leave-one-paper-out backtest it scored Brier{' '}
        {backtest.bayes.brier.toFixed(3)}, against {backtest.pooled.brier.toFixed(3)} for section rates alone and {backtest.empirical.brier.toFixed(3)} for item
        history alone.
      </p>

      <div className="section-head">
        <h2>Question types by section</h2>
        <span className="muted">All three papers</span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Section</th>
              <th className="num">MCQ</th>
              <th className="num">MSQ</th>
              <th className="num">NAT</th>
              <th className="num">NAT share</th>
            </tr>
          </thead>
          <tbody>
            {[...mix.entries()]
              .sort((a, b) => b[1].NAT / (b[1].MCQ + b[1].MSQ + b[1].NAT) - a[1].NAT / (a[1].MCQ + a[1].MSQ + a[1].NAT))
              .map(([section, counts]) => (
                <tr key={section}>
                  <td>{SHORT_SECTION[section]}</td>
                  <td className="num">{counts.MCQ}</td>
                  <td className="num">{counts.MSQ}</td>
                  <td className="num">{counts.NAT}</td>
                  <td className="num">{Math.round((counts.NAT / (counts.MCQ + counts.MSQ + counts.NAT)) * 100)}%</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p className="note" style={{ marginTop: 8 }}>
        NAT questions have no options to eliminate, so practise solving them to the final number.
      </p>

      {pairs.length > 0 && (
        <>
          <div className="section-head">
            <h2>Topics asked together</h2>
            <span className="muted">Pairs from different sections tagged on the same question</span>
          </div>
          <ul className="qlinks">
            {pairs.map((pair) => (
              <li key={`${pair.item_a}-${pair.item_b}`}>
                <a href={`#item-${pair.item_a}`}>
                  <span style={{ flex: 1 }}>
                    {pair.label_a} with {pair.label_b}
                  </span>
                  <span className="muted num">
                    {pair.questions} question{pair.questions > 1 ? 's' : ''}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
