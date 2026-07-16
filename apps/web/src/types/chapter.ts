export interface Chapter {
  id: string;
  project_id: string;
  title: string;
  sort_order: number;
  current_text: string;
  status: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ChapterListSchema {
  id: string;
  project_id: string;
  title: string;
  sort_order: number;
  status: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ChapterVersion {
  id: string;
  chapter_id: string;
  version_number: number;
  source: string;
  text: string;
  note: string;
  generation_candidate_id: string | null;
  created_at: string;
}

export interface ChapterCreate {
  title?: string;
  sort_order?: number;
  current_text?: string;
}

export interface ChapterUpdate {
  title?: string;
  current_text?: string;
  expected_updated_at: string;
}

export interface ChapterReorderItem {
  id: string;
  sort_order: number;
}

export interface VersionCreate {
  text: string;
  note?: string;
  source?: string;
}
