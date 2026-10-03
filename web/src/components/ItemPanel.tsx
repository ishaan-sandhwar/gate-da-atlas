/** Details of one syllabus item: official wording, marks by paper, forecast and its questions. */
import { SHORT_SECTION, atlas, itemById, questionById, questionName } from '../data';
import { navigate } from '../router';
import { useAppState } from '../appState';

export function ItemPanel({ itemId }: { itemId: string }) {
  const { setItemFilter } = useAppState();
  const item = itemById.get(itemId);
  const stats = atlas.items[itemId];
  if (!item || !stats) return null;
  const total = stats.marks.reduce((a, b) => a + b, 0);
  const related = [...stats.questions, ...stats.secondary_questions.filter((q) => !stats.questions.includes(q))];
  const forecast = stats.forecast;

  return (
    <aside className="panel" aria-label={`Details for ${item.label}`}>
      <div className="panel__place">
        {SHORT_SECTION[item.sectionId] ?? item.sectionTitle}
        <br />
        {item.cluster}
      </div>
      <h2>{item.label}</h2>
      <div className="official">
        <small>Official syllabus wording</small>
        {item.official_text}
        {item.note && <small>Note: {item.note}</small>}
      </div>

      <div className="statline">
        {atlas.years.map((year, k) => (
          <div className="stat" key={year}>
            <span className="stat__value num">{stats.marks[k]}</span>
            <span className="stat__label">marks in {year}</span>
          </div>
        ))}
      </div>

      {stats.status === 'never_asked' ? (
        <p>
          Never asked in 2024–2026. The forecast still gives it a <strong>{Math.round(forecast.p_asked * 100)}%</strong> chance of
          appearing in the next paper, because other items of its section do appear.
        </p>
      ) : (
        <p>
          {total > 0 ? `${total} marks across the three papers` : 'No question of its own yet'}
          {stats.secondary_uses > 0 && `, and needed inside ${stats.secondary_uses} other question${stats.secondary_uses > 1 ? 's' : ''}`}. Next
          paper: about <strong className="num">{forecast.expected_questions.toFixed(1)}</strong> questions expected,{' '}
          <strong>{Math.round(forecast.p_asked * 100)}%</strong> chance it appears (80% interval{' '}
          <span className="num">
            {forecast.rate_low.toFixed(1)}–{forecast.rate_high.toFixed(1)}
          </span>{' '}
          questions).
        </p>
      )}

      {related.length > 0 && (
        <div>
          <ul className="qlinks">
            {related.map((qid) => {
              const q = questionById.get(qid)!;
              const main = q.tags.primary === itemId;
              return (
                <li key={qid}>
                  <a href={`#q-${qid}`}>
                    <span className="qlinks__id">{questionName(qid)}</span>
                    <span className="badge">{q.type}</span>
                    <span className="muted">
                      {q.marks} mark{q.marks > 1 ? 's' : ''}
                      {main ? '' : ', as a secondary concept'}
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {related.length > 0 && (
        <button
          className="btn"
          type="button"
          onClick={() => {
            setItemFilter(itemId);
            navigate({ view: 'questions' });
          }}
        >
          Practice {related.length === 1 ? 'this question' : `these ${related.length} questions`}
        </button>
      )}
    </aside>
  );
}
