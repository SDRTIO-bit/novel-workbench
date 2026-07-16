import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './client';
import type { Project, ProjectListItem, ProjectDocument, ProjectCreate, ProjectUpdate, DocumentUpdate } from '../types';

export const listProjects = (includeDeleted = false) => apiGet<ProjectListItem[]>(`/projects?include_deleted=${includeDeleted}`);
export const getProject = (id: string) => apiGet<Project>(`/projects/${id}`);
export const createProject = (data: ProjectCreate) => apiPost<Project>('/projects', data);
export const updateProject = (id: string, data: ProjectUpdate) => apiPatch<Project>(`/projects/${id}`, data);
export const deleteProject = (id: string) => apiDelete(`/projects/${id}`);
export const restoreProject = (id: string) => apiPost<Project>(`/projects/${id}/restore`);
export const duplicateProject = (id: string) => apiPost<Project>(`/projects/${id}/duplicate`);
export const getDocuments = (projectId: string) => apiGet<ProjectDocument[]>(`/projects/${projectId}/documents`);
export const updateDocument = (projectId: string, kind: string, data: DocumentUpdate) => apiPut<ProjectDocument>(`/projects/${projectId}/documents/${kind}`, data);
