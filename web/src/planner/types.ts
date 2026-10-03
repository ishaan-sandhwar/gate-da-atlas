/** Types shared by the planner port (mirrors src/gate_atlas/planner in Python). */

export interface Unit {
  id: string;
  part: 'DA' | 'GA';
  section_id: string;
  section_title: string;
  title: string;
  items: string[];
  hours: number;
  prereqs: string[];
  expected_marks: number;
  questions: string[];
}

export type Level = 'not_started' | 'weak' | 'basic' | 'okay' | 'good' | 'strong';

export interface ProgressEntry {
  unit: string;
  hours: number;
}

export interface MockEntry {
  date?: string;
  /** section or unit id -> [correct, attempted] */
  results: Record<string, [number, number]>;
}

export interface Profile {
  name: string;
  exam_date: string; // ISO yyyy-mm-dd
  start_date: string;
  hours_per_day: number;
  study_days_per_week: number;
  final_weeks: number;
  reserve_papers_for_mocks: number[];
  ratings: Record<string, string>;
  progress: ProgressEntry[];
  mocks: MockEntry[];
}

export interface Mock {
  name: string;
  hours: number;
}

export interface Week {
  index: number;
  start: string;
  end: string;
  capacity: number;
  phase: 'learn' | 'final';
  learning: Record<string, number>;
  revision: Record<string, number>;
  targeted: Record<string, number>;
  mocks: Mock[];
  practice: Record<string, string[]>;
  finished: string[];
}

export interface Plan {
  profile: Profile;
  units: Unit[];
  mastery: Record<string, number>;
  hours: Record<string, number>;
  lambda: number;
  weeks: Week[];
  notes: string[];
}
