import { useEffect, useMemo, useRef, useState } from 'react';
import { FlagIcon } from '../components/Icons';
import { Practice } from '../components/Practice';
import { REASON_TEXT, SHORT_SECTION, atlas, itemById, itemLabel, questionById, questionName, questions } from '../data';
import { navigate } from '../router';
import { useAppState } from '../appState';
import type { Question } from '../types';

interface Filters {
  year: string;
  part: string;
  section: string;
  type: string;
  marks: string;
  quality: string;
  text: string;
}

const EMPTY: Filters = { year: '', part: '', section: '', type: '', marks: '', quality: '', text: '' };
const sections = atlas.syllabus.flatMap((p) => p.sections.map((s) => ({ id: s.id, label: SHORT_SECTION[s.id] ?? s.title, part: p.code })));

function matches(q: Question, f: Filters, item: string | null): boolean {
  if (item && q.tags.primary !== item && !q.tags.secondary.includes(item)) return false;
  if (f.year && String(q.year) !== f.year) return false;
  if (f.part && q.part !== f.part) return false;
  if (f.section && !q.tags.primary.startsWith(`${f.section}.`)) return false;
  if (f.type && q.type !== f.type) return false;
  if (f.marks && String(q.marks) !== f.marks) return false;
  if (f.quality && q.status !== f.quality) return false;
  if (f.text) {
    const needle = f.text.toLowerCase();
    const haystack = `${q.stem} ${Object.values(q.options ?? {}).join(' ')} ${itemLabel(q.tags.primary)} ${q.tags.secondary.map(itemLabel).join(' ')}`.toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

function Select({ id, label, value, onChange, options }: { id: string; label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </div>
  );
}

function Detail({ q }: { q: Question }) {
  const sectionId = q.tags.primary.split('.').slice(0, 2).join('.');
  const source = atlas.sources.find((s) => s.kind === 'paper' && s.year === q.year);
  const aiAgrees = q.ai.hybrid === q.tags.primary;
  return (
    <article className="qdetail" aria-label={`Question ${questionName(q.id)}`}>
      <div className="qdetail__head">
        <h2>{questionName(q.id)}</h2>
        <span className="badge">{q.type}</span>
        <span>
          {q.marks} mark{q.marks > 1 ? 's' : ''}
          {q.negative ? `, wrong answer costs ${q.marks === 1 ? '1/3' : '2/3'}` : ', no negative marking'}
        </span>
        <span className="muted">{q.part === 'GA' ? 'General Aptitude' : SHORT_SECTION[sectionId]}</span>
      </div>

      <figure className="crop" style={{ margin: 0 }}>
        <img src={q.crop} alt={`Question ${questionName(q.id)} as printed in the official paper. ${q.stem.slice(0, 160)}`} loading="lazy" />
      </figure>

      <Practice question={q} key={q.id} />

      <dl className="kv">
        <dt>Main topic</dt>
        <dd>
          <a className="chip chip--strong" href={`#item-${q.tags.primary}`}>
            {itemLabel(q.tags.primary)}
          </a>
        </dd>
        {q.tags.secondary.length > 0 && (
          <>
            <dt>Also needs</dt>
            <dd style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {q.tags.secondary.map((id) => (
                <a className="chip" key={id} href={`#item-${id}`}>
                  {itemLabel(id)}
                </a>
              ))}
            </dd>
          </>
        )}
        <dt>Why</dt>
        <dd>
          {q.tags.rationale}
          {q.tags.fit !== 'direct' && <span className="muted"> ({q.tags.fit === 'outside' ? 'not covered by the syllabus' : 'related, not named in the syllabus'})</span>}
        </dd>
        {q.ai.hybrid && (
          <>
            <dt>AI tagger</dt>
            <dd>
              {aiAgrees ? 'Agrees' : `Suggests ${itemLabel(q.ai.hybrid)}`}
              <span className="muted"> (gpt-oss-120b choosing among the ML model&rsquo;s top 15)</span>
            </dd>
          </>
        )}
        <dt>Source</dt>
        <dd>
          Page {q.pages.join(', ')} of the{' '}
          {source ? (
            <a href={source.url} target="_blank" rel="noreferrer">
              official {q.year} paper
            </a>
          ) : (
            `official ${q.year} paper`
          )}
        </dd>
      </dl>

      <details className="extracted">
        <summary>Text extracted from the PDF{q.status === 'needs_review' ? ' (check the image)' : ''}</summary>
        {q.status === 'needs_review' && <p className="note">The image above is the reference: this question {q.reasons.map((r) => REASON_TEXT[r] ?? r).join('; ')}.</p>}
        <pre>{[q.stem, ...Object.entries(q.options ?? {}).map(([k, v]) => `(${k}) ${v}`)].join('\n')}</pre>
      </details>

      {q.similar.length > 0 && (
        <div>
          <h3 style={{ fontSize: 'var(--step-1)', marginBottom: 6 }}>Questions like this</h3>
          <ul className="qlinks">
            {q.similar.map(([id]) => {
              const other = questionById.get(id)!;
              return (
                <li key={id}>
                  <a href={`#q-${id}`}>
                    <span className="qlinks__id">{questionName(id)}</span>
                    <span style={{ flex: 1, minWidth: 0 }}>{itemLabel(other.tags.primary)}</span>
                  </a>
                </li>
              );
            })}
          </ul>
          <p className="note">Closest first, by the similarity of sentence embeddings (bge-small-en-v1.5) of the question texts.</p>
        </div>
      )}
    </article>
  );
}

export function QuestionsView({ questionId }: { questionId?: string }) {
  const { itemFilter, setItemFilter } = useAppState();
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const set = (key: keyof Filters) => (value: string) => setFilters((f) => ({ ...f, [key]: value }));
  const visible = useMemo(() => questions.filter((q) => matches(q, filters, itemFilter)), [filters, itemFilter]);
  const current = questionId ? questionById.get(questionId) : undefined;
  // Wide screens show the first match when no question is chosen; narrow screens show the list.
  const shown = current ?? visible[0];

  const detailRef = useRef<HTMLDivElement>(null);

  // Bring a newly chosen question into view when its top is off screen (below the sticky header).
  useEffect(() => {
    const element = detailRef.current;
    if (!current || !element) return;
    const header = (document.querySelector('.topbar')?.getBoundingClientRect().height ?? 60) + 12;
    const top = element.getBoundingClientRect().top;
    if (top < header || top > window.innerHeight * 0.6) window.scrollTo({ top: top + window.scrollY - header });
  }, [current]);

  return (
    <>
      <div className="hero" style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 'var(--step-3)' }}>Questions</h1>
        <p className="lede">Every question from the three official papers, with its official image, its syllabus topics and a way to try it.</p>
      </div>
      <div className="filters" role="search">
        <Select id="f-year" label="Paper" value={filters.year} onChange={set('year')} options={[['', 'All'], ...atlas.years.map((y): [string, string] => [String(y), String(y)])]} />
        <Select id="f-part" label="Part" value={filters.part} onChange={set('part')} options={[['', 'Both'], ['DA', 'Data Science and AI'], ['GA', 'General Aptitude']]} />
        <Select
          id="f-section"
          label="Section"
          value={filters.section}
          onChange={set('section')}
          options={[['', 'All'], ...sections.filter((s) => !filters.part || s.part === filters.part).map((s): [string, string] => [s.id, s.label])]}
        />
        <Select id="f-type" label="Type" value={filters.type} onChange={set('type')} options={[['', 'All'], ['MCQ', 'MCQ'], ['MSQ', 'MSQ'], ['NAT', 'NAT']]} />
        <Select id="f-marks" label="Marks" value={filters.marks} onChange={set('marks')} options={[['', 'All'], ['1', '1 mark'], ['2', '2 marks']]} />
        <Select id="f-quality" label="Text" value={filters.quality} onChange={set('quality')} options={[['', 'All'], ['clean', 'Clean text'], ['needs_review', 'Read the image']]} />
        <div className="field field--grow">
          <label htmlFor="f-text">Search</label>
          <input id="f-text" type="search" placeholder="eigenvalue, SQL, Bayes…" value={filters.text} onChange={(event) => set('text')(event.target.value)} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 10 }}>
        <span className="num muted">
          {visible.length} of {questions.length} questions
        </span>
        {itemFilter && (
          <button className="chip chip--strong" type="button" onClick={() => setItemFilter(null)} aria-label={`Remove topic filter ${itemLabel(itemFilter)}`}>
            Topic: {itemById.get(itemFilter)?.label} ✕
          </button>
        )}
        {(Object.values(filters).some(Boolean) || itemFilter) && (
          <button
            className="btn btn--quiet"
            type="button"
            style={{ padding: '2px 8px' }}
            onClick={() => {
              setFilters(EMPTY);
              setItemFilter(null);
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <div className={`qview ${current ? 'qview--detail' : 'qview--list'}`}>
        <nav className="qlist" aria-label="Question list">
          {visible.length === 0 && <p className="empty">No question matches these filters. Clear a filter to see more.</p>}
          {visible.map((q) => (
            <a key={q.id} className="qrow" href={`#q-${q.id}`} aria-current={shown?.id === q.id ? 'true' : undefined}>
              <span className="qrow__id">{questionName(q.id)}</span>
              <span className="muted">
                {q.type}, {q.marks} mark{q.marks > 1 ? 's' : ''}
              </span>
              <span className="qrow__flags">{q.status === 'needs_review' && <FlagIcon title="Read the image: the text is lossy" />}</span>
              <span className="qrow__topic">{itemLabel(q.tags.primary)}</span>
            </a>
          ))}
        </nav>
        <div className="qdetail-wrap" style={{ minWidth: 0 }} ref={detailRef}>
          {current && (
            <button className="btn btn--quiet only-narrow" type="button" style={{ marginBottom: 10 }} onClick={() => navigate({ view: 'questions' })}>
              Back to the list
            </button>
          )}
          {shown && <Detail q={shown} />}
        </div>
      </div>
    </>
  );
}
