import { apiGet, apiPost } from './client';
import type { PromptProfileList, PromptProfile, PromptVersion, PromptCreate, PromptVersionCreate, RenderPreviewRequest, RenderPreviewResponse } from '../types';

export const listPrompts = (stage?: string) => {
  const qs = stage ? `?stage=${stage}` : '';
  return apiGet<PromptProfileList[]>(`/prompts${qs}`);
};
export const createPrompt = (data: PromptCreate) => apiPost<PromptProfile>('/prompts', data);
export const getVersions = (profileId: string) => apiGet<PromptVersion[]>(`/prompts/${profileId}/versions`);
export const addVersion = (profileId: string, data: PromptVersionCreate) => apiPost<PromptVersion>(`/prompts/${profileId}/versions`, data);
export const duplicatePrompt = (profileId: string) => apiPost<PromptProfile>(`/prompts/${profileId}/duplicate`);
export const restoreDefault = (profileId: string) => apiPost<PromptProfile>(`/prompts/${profileId}/restore-default`);
export const renderPreview = (data: RenderPreviewRequest) => apiPost<RenderPreviewResponse>('/prompts/render-preview', data);
export const exportPrompts = () => apiGet<unknown>('/prompts/export');
export const importPrompts = (data: unknown) => apiPost<{ imported: number }>('/prompts/import', data);
