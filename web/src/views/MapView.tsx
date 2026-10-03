import { useState } from 'react';
import { ItemPanel } from '../components/ItemPanel';
import { MapLegend, SyllabusMap } from '../components/SyllabusMap';
import type { Scope } from '../components/tiles';
import { SHORT_SECTION, atlas, itemById, questions } from '../data';
import { navigate } from '../router';

/** Item with the most marks overall: the map opens on it. */
const DEFAULT_ITEM = Object.entries(atlas.items).sort(
  (a, b) => b[1].marks.reduce((x, y) => x + y, 0) - a[1].marks.reduce((x, y) => x + y, 0),
)[0][0];

function Findings() {
  const da = atlas.sections.primary.filter((s) => s.part === 'DA');
  const top3 = [...da].sort((a, b) => b.marks_mean - a.marks_mean).slice(0, 3);
  const share = top3.reduce((a, s) => a + s.share_of_part, 0);
  const daItems = Object.entries(atlas.items).filter(([id]) => id.startsWith('DA.'));
  const never = daItems.filter(([, s]) => s.status === 'never_asked').length;
  const rising = da.filter((s) => s.trend === 'rising').sort((a, b) => b.trend_marks_per_year - a.trend_marks_per_year)[0];
  const coverage = atlas.coverage.filter((c) => c.part === 'DA');
  const years = atlas.years;
  return (
    <div className="findings">
      <div className="finding">
        <p>
          <strong>{Math.round(share * 100)}%</strong> of the DA marks come from {top3.map((s) => SHORT_SECTION[s.section_id]).join(', ').replace(/, ([^,]*)$/, ' and $1')}.
        </p>
      </div>
      <div className="finding">
        <p>
          <strong>{never}</strong> of {daItems.length} DA syllabus items have never been asked, even as part of another question.
        </p>
      </div>
      {rising && (
        <div className="finding">
          <p>
            <strong>
              {rising[`marks_${years[0]}`]} → {rising[`marks_${years[years.length - 1]}`]}
            </strong>{' '}
            marks for {SHORT_SECTION[rising.section_id]}, the fastest-rising section.
          </p>
        </div>
      )}
      <div className="finding">
        <p>
          <strong>
            {Math.round(Math.min(...coverage.map((c) => c.share)) * 100)}–{Math.round(Math.max(...coverage.map((c) => c.share)) * 100)}%
          </strong>{' '}
          of the DA syllabus appears in any single paper, so no paper covers it all.
        </p>
      </div>
    </div>
  );
}

export function MapView({ itemId }: { itemId?: string }) {
  const [scope, setScope] = useState<Scope>('all');
  const selected = itemId && itemById.has(itemId) ? itemId : DEFAULT_ITEM;
  const options: { value: Scope; label: string }[] = [{ value: 'all', label: 'All papers' }, ...atlas.years.map((y) => ({ value: y, label: String(y) }))];

  return (
    <>
      <div className="hero">
        <h1>Where GATE DA&rsquo;s marks came from</h1>
        <p className="lede">
          {questions.length} questions from the official {atlas.years.slice(0, -1).join(', ')} and {atlas.years[atlas.years.length - 1]} papers,
          placed on all {Object.keys(atlas.items).length} items of the syllabus. Pick a tile to see its questions.
        </p>
        <div className="hero__controls">
          <div className="segmented" role="group" aria-label="Papers to show">
            {options.map((option) => (
              <button key={String(option.value)} type="button" aria-pressed={scope === option.value} onClick={() => setScope(option.value)}>
                {option.label}
              </button>
            ))}
          </div>
          <MapLegend scope={scope} />
        </div>
      </div>
      <div className="map-layout">
        <SyllabusMap scope={scope} selected={selected} onSelect={(id) => navigate({ view: 'map', item: id })} />
        <ItemPanel itemId={selected} />
      </div>
      <Findings />
    </>
  );
}
