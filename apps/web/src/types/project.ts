export interface ProjectListItem {
  id: string;
  name: string;
  genre: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ProjectDocument {
  id: string;
  kind: DocumentKind;
  title: string;
  content: string;
  sort_order: number;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  genre: string;
  author_note: string;
  default_pov: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  documents: ProjectDocument[];
}

export type DocumentKind =
  | "synopsis"
  | "outline"
  | "characters"
  | "world"
  | "style"
  | "principles"
  | "summary"
  | "notes";

export const DOCUMENT_KINDS: DocumentKind[] = [
  "synopsis",
  "outline",
  "characters",
  "world",
  "style",
  "principles",
  "summary",
  "notes",
];

export const DOCUMENT_LABELS: Record<DocumentKind, string> = {
  synopsis: "梗概",
  outline: "大纲",
  characters: "人物",
  world: "世界观",
  style: "风格",
  principles: "原则",
  summary: "摘要",
  notes: "笔记",
};

export interface ProjectCreate {
  name: string;
  genre?: string;
  author_note?: string;
  default_pov?: string;
}

export interface ProjectUpdate {
  name?: string;
  genre?: string;
  author_note?: string;
  default_pov?: string;
}

export interface DocumentUpdate {
  title?: string;
  content?: string;
}
