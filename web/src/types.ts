/** Shapes of the JSON exported by `python -m gate_atlas export-web`. */
import type { Unit } from './planner/types';

export type Part = 'DA' | 'GA';
export type QuestionType = 'MCQ' | 'MSQ' | 'NAT';

export interface SyllabusItem {
  id: string;
  label: string;
  cluster: string;
  official_text: string;
  note: string;
}

export interface SyllabusSection {
  id: string;
  title: string;
  official_text: string;
  items: SyllabusItem[];
}

export interface SyllabusPart {
  code: Part;
  title: string;
  sections: SyllabusSection[];
}

export interface Forecast {
  expected_marks: number;
  p_asked: number;
  rate_low: number;
  rate_high: number;
  expected_questions: number;
}

export interface ItemStats {
  marks: number[];
  shared_marks: number;
  secondary_uses: number;
  status: 'asked' | 'only_secondary' | 'never_asked';
  forecast: Forecast;
  questions: string[];
  secondary_questions: string[];
}

export interface SectionRow {
  part: Part;
  id: string;
  section_id: string;
  title: string;
  items: number;
  marks_total: number;
  marks_mean: number;
  marks_min: number;
  marks_max: number;
  share_of_part: number;
  trend_marks_per_year: number;
  trend: 'rising' | 'falling' | 'stable' | 'mixed';
  [key: `marks_${number}` | `questions_${number}`]: number;
}

export interface TypeMixRow {
  part: Part;
  section_id: string;
  type: QuestionType;
  marks_each: number;
  questions: number;
  marks: number;
}

export interface CoverageRow {
  part: Part;
  year: number;
  items_touched: number;
  items_total: number;
  share: number;
}

export interface PairRow {
  item_a: string;
  label_a: string;
  item_b: string;
  label_b: string;
  questions: number;
  cross_section: boolean;
}

export interface TaggerScore {
  label: string;
  n: number;
  primary: number;
  primary_in_reference_items: number;
  section: number;
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
  level: string;
}

export interface Source {
  filename: string;
  kind: string;
  year: number;
  subject: string;
  url: string;
  sha256: string;
  mirrors: number;
}

export interface Atlas {
  generated_at: string;
  years: number[];
  syllabus: SyllabusPart[];
  items: Record<string, ItemStats>;
  sections: { primary: SectionRow[]; shared: SectionRow[] };
  clusters: SectionRow[];
  type_mix: TypeMixRow[];
  coverage: CoverageRow[];
  cooccurrence: PairRow[];
  forecast: {
    prior: Record<string, { shape: number; section_rates: Record<string, number> }>;
    backtest: Record<string, Record<string, { brier: number; log_loss: number; count_rmse: number }>>;
  };
  tag_sensitivity: Record<string, { max_abs_change_marks: number; where: string; mean_abs_change_marks: number }>;
  units: Unit[];
  tagging: {
    methods: Record<string, TaggerScore>;
    paired_tests: Record<string, { n: number; only_first_right: number; only_second_right: number; p_value: number }>;
  };
  validation: { passed: boolean; summary: Record<string, Record<string, unknown>>; checks: Check[] };
  sources: Source[];
}

export type Answer =
  | { kind: 'options'; options: string[] }
  | { kind: 'range'; low: number; high: number }
  | { kind: 'mta' };

export interface Tags {
  primary: string;
  secondary: string[];
  fit: 'direct' | 'indirect' | 'outside';
  confidence: 'high' | 'medium' | 'low';
  rationale: string;
  source: string;
}

export interface Question {
  id: string;
  year: number;
  number: number;
  part: Part;
  marks: number;
  type: QuestionType;
  negative: number;
  answer: Answer | null;
  stem: string;
  options: Record<string, string> | null;
  status: 'clean' | 'needs_review';
  reasons: string[];
  tags: Tags;
  crop: string;
  pages: number[];
  similar: [string, number][];
  ai: { llm: string | null; hybrid: string | null };
}
