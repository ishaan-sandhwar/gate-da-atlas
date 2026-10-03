/**
 * The syllabus map: one tile per syllabus item, grouped into section regions and shaded by the
 * marks its questions carried in the chosen papers. Hatched tiles were never asked.
 */
import { useState, type CSSProperties } from 'react';
import { SHORT_SECTION, atlas } from '../data';
import { describeTile, tileState, type Scope } from './tiles';

interface Props {
  scope: Scope;
  selected: string;
  onSelect: (itemId: string) => void;
}

export function SyllabusMap({ scope, selected, onSelect }: Props) {
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const sectionMarks = new Map(atlas.sections.primary.map((s) => [s.section_id, s.marks_mean]));

  const bands = atlas.syllabus.map((part) => ({
    code: part.code,
    title: part.code === 'DA' ? 'Data Science and AI (85 marks a paper)' : 'General Aptitude (15 marks a paper)',
    sections: [...part.sections].sort((a, b) => (sectionMarks.get(b.id) ?? 0) - (sectionMarks.get(a.id) ?? 0)),
  }));

  return (
    <div className="map" onMouseLeave={() => setTip(null)}>
      {bands.map((band) => (
        <section className="map__band" key={band.code} aria-label={band.title}>
          <div className="map__band-title">{band.title}</div>
          <div className="map__regions">
            {band.sections.map((section) => (
              <div className="region" key={section.id}>
                <div className="region__name">
                  <h3>{SHORT_SECTION[section.id] ?? section.title}</h3>
                  <span className="region__meta num">
                    {section.items.length} items, {(sectionMarks.get(section.id) ?? 0).toFixed(1)} marks a paper
                  </span>
                </div>
                <div className="tiles">
                  {section.items.map((item, index) => {
                    const state = tileState(item.id, scope);
                    const text = describeTile(item.label, state, scope);
                    const style = { '--delay': `${Math.min(index * 9, 280)}ms` } as CSSProperties;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={`tile tile--${state.level}`}
                        style={style}
                        aria-pressed={selected === item.id}
                        aria-label={text}
                        onClick={() => onSelect(item.id)}
                        onMouseMove={(event) => setTip({ text, x: event.clientX, y: event.clientY })}
                        onFocus={(event) => {
                          const box = event.currentTarget.getBoundingClientRect();
                          setTip({ text, x: box.right, y: box.top });
                        }}
                        onBlur={() => setTip(null)}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {tip && (
        <div className="tile-tip" role="presentation" style={{ left: Math.min(tip.x + 14, window.innerWidth - 270), top: tip.y + 16 }}>
          {tip.text}
        </div>
      )}
    </div>
  );
}

export function MapLegend({ scope }: { scope: Scope }) {
  return (
    <div className="legend" aria-label="Map legend">
      <span>Marks carried</span>
      <span className="legend__scale">
        <span className="legend__swatch tile--l1" />
        <span className="num">1–2</span>
      </span>
      <span className="legend__scale">
        <span className="legend__swatch tile--l2" />
        <span className="num">3–4</span>
      </span>
      <span className="legend__scale">
        <span className="legend__swatch tile--l3" />
        <span className="num">5–8</span>
      </span>
      <span className="legend__scale">
        <span className="legend__swatch tile--l4" />
        <span className="num">9+</span>
      </span>
      <span className="legend__scale">
        <span className="legend__swatch tile--secondary" />
        only inside other questions
      </span>
      <span className="legend__scale">
        <span className="legend__swatch tile--never" />
        {scope === 'all' ? 'never asked' : `not asked in ${scope}`}
      </span>
    </div>
  );
}
