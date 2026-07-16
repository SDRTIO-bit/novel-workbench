import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import type { Chapter, ChapterListSchema, ChapterVersion, ChapterCreate, ChapterUpdate, ChapterReorderItem, VersionCreate } from '../types';

export const listChapters = (projectId: string) => apiGet<ChapterListSchema[]>(`/projects/${projectId}/chapters`);
export const createChapter = (projectId: string, data: ChapterCreate) => apiPost<Chapter>(`/projects/${projectId}/chapters`, data);
export const updateChapter = (id: string, data: ChapterUpdate) => apiPatch<Chapter>(`/chapters/${id}`, data);
export const deleteChapter = (id: string) => apiDelete(`/chapters/${id}`);
export const restoreChapter = (id: string) => apiPost<Chapter>(`/chapters/${id}/restore`);
export const reorderChapters = (items: ChapterReorderItem[]) => apiPost<void>('/chapters/reorder', { items });
export const getVersions = (chapterId: string) => apiGet<ChapterVersion[]>(`/chapters/${chapterId}/versions`);
export const createVersion = (chapterId: string, data: VersionCreate) => apiPost<ChapterVersion>(`/chapters/${chapterId}/versions`, data);
export const restoreVersion = (chapterId: string, versionId: string) => apiPost<ChapterVersion>(`/chapters/${chapterId}/restore-version/${versionId}`);
