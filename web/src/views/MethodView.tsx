import { CheckIcon, CrossIcon } from '../components/Icons';
import { atlas, questions } from '../data';
import { EVIDENCE_STRENGTH, MASTERY_CAP, TIME_CONSTANT_FRACTION } from '../planner/allocate';
import { MOCK_REVIEW_HOURS, MOCK_TEST_HOURS, PYQ_PER_UNIT, REVISION_OFFSETS_WEEKS, REVISION_SHARE } from '../planner/schedule';

const DOCUMENT_NAME: Record<string, string> = { paper: 'Question paper', key: 'Answer key', syllabus: 'Syllabus' };
const TAGGERS: [string, string][] = [
  ['ml_zero_shot', 'Sentence embeddings only (zero-shot)'],
  ['ml_fewshot_blend', 'Embeddings plus labelled neighbours (few-shot)'],
  ['llm_openai_gpt-oss-120b_full', 'LLM choosing from the whole syllabus'],
  ['llm_openai_gpt-oss-120b_hybrid', 'LLM choosing from the ML model’s top 15 (DA only)'],
];
const FORECASTERS: [string, string][] = [
  ['bayes', 'Item history pulled toward its section (used here)'],
  ['pooled', 'Section rate only'],
  ['empirical', 'Item history only'],
];
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const marksText = (n: number) => `${Number(n.toFixed(1))} mark${n === 1 ? '' : 's'}`;

interface YearSummary {
  questions: number;
  marks: number;
  by_type: Record<string, number>;
  clean: number;
  needs_review: number;
}

export function MethodView() {
  const summary = atlas.validation.summary as unknown as Record<string, YearSummary>;
  const daItems = atlas.syllabus.find((p) => p.code === 'DA')!.sections.reduce((a, s) => a + s.items.length, 0);
  const gaItems = atlas.syllabus.find((p) => p.code === 'GA')!.sections.reduce((a, s) => a + s.items.length, 0);
  const paired = atlas.tagging.paired_tests['llm_openai_gpt-oss-120b_full vs llm_openai_gpt-oss-120b_hybrid'];
  const backtest = atlas.forecast.backtest.DA;
  const studyHours = atlas.units.reduce((a, u) => a + u.hours, 0);
  const passed = atlas.validation.checks.filter((c) => c.passed).length;
  const sharedById = new Map(atlas.sections.shared.map((s) => [s.id, s]));
  const attributionShift = Math.max(
    ...atlas.sections.primary.flatMap((row) => atlas.years.map((y) => Math.abs((sharedById.get(row.id)?.[`marks_${y}`] ?? 0) - row[`marks_${y}`]))),
  );
  const tagShift = atlas.tag_sensitivity['llm_openai_gpt-oss-120b_full'];
  const attributionChecks =
    `splitting marks between the main and the extra items moves a section's marks in one paper by at most ${marksText(attributionShift)}` +
    (tagShift
      ? `, and tagging with the LLM's main items instead moves them by at most ${marksText(tagShift.max_abs_change_marks)} (${tagShift.mean_abs_change_marks} on average)`
      : '');

  return (
    <>
      <div className="hero" style={{ marginBottom: 6 }}>
        <h1 style={{ fontSize: 'var(--step-3)' }}>Method</h1>
        <p className="lede">How every number on this site was made, and where it can be wrong.</p>
      </div>

      <div className="section-head">
        <h2>Only the official papers</h2>
      </div>
      <div className="prose">
        <p>
          Every question, option and answer comes from the official question papers and answer keys. None is written from memory or generated. Each
          paper and key was downloaded from every official copy the organising institutes host, and the copies had to match byte for byte.
        </p>
      </div>
      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table className="data">
          <thead>
            <tr>
              <th>Document</th>
              <th className="num">Year</th>
              <th className="num">Official copies compared</th>
              <th className="num">SHA-256 (start)</th>
            </tr>
          </thead>
          <tbody>
            {atlas.sources.map((source) => (
              <tr key={source.filename}>
                <td>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {DOCUMENT_NAME[source.kind] ?? source.kind}
                    {source.kind === 'syllabus' ? ` (${source.subject === 'GA' ? 'General Aptitude' : 'DA'})` : ''}
                  </a>
                </td>
                <td className="num">{source.year}</td>
                <td className="num">{source.mirrors}</td>
                <td className="num">{source.sha256.slice(0, 12)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-head">
        <h2>From PDF to questions</h2>
      </div>
      <ol className="steps prose">
        <li>
          <p>Remove page furniture: running headers and footers, watermarks and logos.</p>
        </li>
        <li>
          <p>Find the question numbers in the margin and give every piece of text to the question printed above it.</p>
        </li>
        <li>
          <p>Split the stem from the options at the option labels (A) to (D).</p>
        </li>
        <li>
          <p>Rebuild the text line by line from glyph positions: superscripts and subscripts, code indentation, combining marks and symbols.</p>
        </li>
        <li>
          <p>Crop every question from the official page as an image. When the text and the image disagree, the image is right.</p>
        </li>
        <li>
          <p>Take marks, type and answer from the official key, and check marks against the headings printed in the paper.</p>
        </li>
        <li>
          <p>
            Mark a question &ldquo;read the image&rdquo; when its text alone cannot carry it: a figure, a table, stacked maths such as fractions and
            matrices, or symbols the PDF never mapped to text. {questions.filter((q) => q.status === 'needs_review').length} of {questions.length}{' '}
            questions carry this mark. They keep their best-effort text and are tagged from their images.
          </p>
        </li>
      </ol>

      <div className="section-head">
        <h2>Validation</h2>
        <span className="muted">
          {passed} of {atlas.validation.checks.length} checks pass
        </span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Paper</th>
              <th className="num">Questions</th>
              <th className="num">Marks</th>
              <th className="num">MCQ</th>
              <th className="num">MSQ</th>
              <th className="num">NAT</th>
              <th className="num">Clean text</th>
              <th className="num">Read the image</th>
            </tr>
          </thead>
          <tbody>
            {atlas.years.map((year) => {
              const row = summary[String(year)];
              return (
                <tr key={year}>
                  <td>{year}</td>
                  <td className="num">{row.questions}</td>
                  <td className="num">{row.marks}</td>
                  <td className="num">{row.by_type.MCQ}</td>
                  <td className="num">{row.by_type.MSQ}</td>
                  <td className="num">{row.by_type.NAT}</td>
                  <td className="num">{row.clean}</td>
                  <td className="num">{row.needs_review}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <details style={{ marginTop: 10 }}>
        <summary className="muted" style={{ cursor: 'pointer' }}>
          Show every check
        </summary>
        <ul className="qlinks" style={{ marginTop: 8 }}>
          {atlas.validation.checks.map((check) => (
            <li key={check.name} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '3px 0', borderBottom: '1px solid var(--rule)' }}>
              <span style={{ color: check.passed ? 'var(--good)' : 'var(--bad)', alignSelf: 'center' }}>
                {check.passed ? <CheckIcon /> : <CrossIcon />}
                <span className="visually-hidden">{check.passed ? 'Passed' : 'Failed'}</span>
              </span>
              <span style={{ flex: 1 }}>{check.name}</span>
              <span className="muted">{check.detail}</span>
            </li>
          ))}
        </ul>
      </details>

      <div className="section-head">
        <h2>Tagging questions to the syllabus</h2>
      </div>
      <div className="prose">
        <p>
          The official syllabus is one long list per section. It is split into {daItems + gaItems} items ({daItems} DA, {gaItems} General Aptitude),
          and each item keeps the official phrase it comes from. A build check confirms the items cover every official phrase, so none is invented
          or dropped. The syllabus text is identical in the 2024, 2025, 2026 and 2027 editions.
        </p>
        <p>
          Every question has one main item (what it mainly tests) and up to three items it also needs. These reference tags were written by an AI assistant
          that is not one of the taggers scored below, from the question text and images, before any automatic tagger ran. They are one annotator&rsquo;s
          judgement, not ground truth.
        </p>
        <p>Four automatic taggers were then scored against the reference tags:</p>
      </div>
      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table className="data">
          <thead>
            <tr>
              <th>Tagger</th>
              <th className="num">Questions</th>
              <th className="num">Exact item</th>
              <th className="num">Right section</th>
            </tr>
          </thead>
          <tbody>
            {TAGGERS.filter(([key]) => atlas.tagging.methods[key]).map(([key, name]) => {
              const score = atlas.tagging.methods[key];
              return (
                <tr key={key}>
                  <td>{name}</td>
                  <td className="num">{score.n}</td>
                  <td className="num">{pct(score.primary)}</td>
                  <td className="num">{pct(score.section)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note" style={{ marginTop: 8 }}>
        The LLM is openai/gpt-oss-120b on Groq with schema-constrained output, so every answer is a real syllabus id. Giving it only the ML
        model&rsquo;s 15 best candidates beat giving it the whole list
        {paired ? ` (McNemar test on ${paired.n} DA questions: ${paired.only_second_right} wins against ${paired.only_first_right}, p = ${paired.p_value})` : ''}.
        The tags shown on this site are the reference tags; the AI tagger&rsquo;s choice appears next to them on each question.
      </p>

      <div className="section-head">
        <h2>Trends and the forecast</h2>
      </div>
      <div className="prose">
        <p>
          A question&rsquo;s marks count toward its main item. Two checks show that section totals do not hinge on that choice: {attributionChecks}. A
          section is called rising or falling only when its marks moved the same way in every paper, by at least 2 marks a year.
        </p>
        <p>
          The forecast treats each item&rsquo;s number of questions per paper as a Poisson count. Its rate gets a Gamma prior centred on the rate of the
          item&rsquo;s section (empirical Bayes), so an item asked once is pulled toward its section and a never-asked item still gets a fair chance.
          Each method was tested by hiding one paper, fitting on the other two and scoring the hidden one (lower is better):
        </p>
      </div>
      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table className="data">
          <thead>
            <tr>
              <th>Forecast method (DA)</th>
              <th className="num">Brier score</th>
              <th className="num">Log loss</th>
              <th className="num">Count error (RMSE)</th>
            </tr>
          </thead>
          <tbody>
            {FORECASTERS.filter(([key]) => backtest[key]).map(([key, name]) => (
              <tr key={key}>
                <td>{name}</td>
                <td className="num">{backtest[key].brier.toFixed(3)}</td>
                <td className="num">{backtest[key].log_loss.toFixed(3)}</td>
                <td className="num">{backtest[key].count_rmse.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-head">
        <h2>The planner</h2>
      </div>
      <div className="prose">
        <p>
          The syllabus is grouped into {atlas.units.length} study units with an estimated {studyHours} hours to learn each from scratch. A unit&rsquo;s
          expected marks come from the past papers, smoothed toward its section&rsquo;s share.
        </p>
        <p>
          Mastery grows with diminishing returns: after <var>h</var> hours, <var>m</var>(<var>h</var>) = 1 − (1 − <var>m</var>
          <sub>0</sub>) e<sup>−h/T</sup>, where <var>m</var>
          <sub>0</sub> comes from your rating and <var>T</var> is {TIME_CONSTANT_FRACTION === 0.5 ? 'half' : `${TIME_CONSTANT_FRACTION} of`} the
          unit&rsquo;s study hours. Mastery is capped at {Math.round(MASTERY_CAP * 100)}%. An hour on a unit is worth its expected marks times the
          mastery that hour adds.
        </p>
        <p>
          Hours go where the next hour is worth most, until they run out. At the optimum every funded unit&rsquo;s last hour is worth the same amount
          (the value shown as &ldquo;the last hour planned&rdquo;), and units below it are strategic skips. This is the KKT condition of the
          problem, solved by bisection.
        </p>
        <p>
          {Math.round(REVISION_SHARE * 100)}% of the time is kept for revision, {REVISION_OFFSETS_WEEKS.map((w) => `${w}`).join(', ').replace(/, ([^,]*)$/, ' and $1')}{' '}
          weeks after a unit is finished. The last weeks hold full mock tests ({MOCK_TEST_HOURS} hours to sit, {MOCK_REVIEW_HOURS} to review) and
          targeted revision. After each unit you get up to {PYQ_PER_UNIT} past questions from this dataset to solve.
        </p>
        <p>
          Logged hours move a unit along its curve. A mock result counts as evidence worth {EVIDENCE_STRENGTH} questions in a Beta update, so one
          bad section score shifts the plan without overturning it.
        </p>
      </div>

      <div className="section-head">
        <h2>Limits</h2>
      </div>
      <ul className="prose" style={{ paddingLeft: 18 }}>
        <li>Three papers are a small sample. Trends describe what happened, not what the setters plan.</li>
        <li>Syllabus items differ in size, so compare sections rather than single items.</li>
        <li>The tags are one annotator&rsquo;s judgement. Every question links to its image so you can disagree.</li>
        <li>Text marked &ldquo;read the image&rdquo; is lossy; the image is the reference.</li>
        <li>Study hours per unit are editorial estimates, and the learning curve is a model. Use the planner to compare plans, not to predict a score.</li>
      </ul>

      <div className="section-head">
        <h2>Credits</h2>
      </div>
      <p className="prose">
        The question papers, answer keys and syllabi are published by the GATE organising institutes: IISc Bengaluru (2024), IIT Roorkee (2025), IIT
        Guwahati (2026) and IIT Madras (2027 syllabus). Each question image on this site is cropped from those papers, and every document above links to
        its official copy.
      </p>
    </>
  );
}
