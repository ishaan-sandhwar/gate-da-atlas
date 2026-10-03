/** Loads the exported dataset once and builds the indexes every view uses. */
import atlasJson from './data/atlas.json';
import questionsJson from './data/questions.json';
import type { Atlas, Question, SyllabusItem, SyllabusSection } from './types';

export const atlas = atlasJson as unknown as Atlas;
export const questions = questionsJson as unknown as Question[];

export interface ItemInfo extends SyllabusItem {
  part: 'DA' | 'GA';
  sectionId: string;
  sectionTitle: string;
}

export const itemById = new Map<string, ItemInfo>();
export const sectionById = new Map<string, SyllabusSection & { part: 'DA' | 'GA' }>();
for (const part of atlas.syllabus) {
  for (const section of part.sections) {
    sectionById.set(section.id, { ...section, part: part.code });
    for (const item of section.items) {
      itemById.set(item.id, { ...item, part: part.code, sectionId: section.id, sectionTitle: section.title });
    }
  }
}

export const questionById = new Map(questions.map((q) => [q.id, q]));

/** Short section names for tight spaces. */
export const SHORT_SECTION: Record<string, string> = {
  'DA.PS': 'Probability & Statistics',
  'DA.LA': 'Linear Algebra',
  'DA.CO': 'Calculus & Optimization',
  'DA.PD': 'Programming & DSA',
  'DA.DB': 'Databases & Warehousing',
  'DA.ML': 'Machine Learning',
  'DA.AI': 'AI',
  'GA.VA': 'Verbal',
  'GA.QA': 'Quantitative',
  'GA.AA': 'Analytical',
  'GA.SA': 'Spatial',
};

/** Label for an item id, e.g. "Bayes' theorem". */
export function itemLabel(id: string): string {
  return itemById.get(id)?.label ?? id;
}

/** Year and number of a question id: DA2025-Q31 -> "2025 Q31". */
export function questionName(id: string): string {
  const match = /^DA(\d{4})-Q(\d+)$/.exec(id);
  return match ? `${match[1]} Q${Number(match[2])}` : id;
}

/** Answer key in words. */
export function answerText(q: Question): string {
  const answer = q.answer;
  if (!answer) return 'No key';
  if (answer.kind === 'mta') return 'Marks to all (the key dropped this question)';
  if (answer.kind === 'range') return answer.low === answer.high ? `${answer.low}` : `${answer.low} to ${answer.high}`;
  return answer.options.join(', ');
}

export const REASON_TEXT: Record<string, string> = {
  figure: 'has a figure the text cannot carry',
  figure_referenced: 'refers to a figure; check the image',
  table: 'has a table; the text flattens it',
  display_math: 'has fractions, matrices or other stacked math',
  unmapped_glyphs: 'uses symbols the PDF did not map to text',
  formatting_semantics: 'depends on underlining',
  empty_text: 'has options that are only pictures',
  option_labels: 'option labels could not be read',
  key_missing: 'has no answer-key row',
};
