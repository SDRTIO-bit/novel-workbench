import { apiGet, apiPost } from './client';
import type { GenerationRun, GenerationRunList, GenerationCandidate, CreateRun, StageOverride, SelectIssues } from '../types';

export const createRun = (data: CreateRun) => apiPost<GenerationRun>('/runs', data);
export const getRun = (id: string) => apiGet<GenerationRun>(`/runs/${id}`);
export const listRuns = (projectId: string) => apiGet<GenerationRunList[]>(`/projects/${projectId}/runs`);
export const executeStage = (runId: string, stage: string, override?: Partial<StageOverride>) => apiPost<GenerationCandidate>(`/runs/${runId}/steps/${stage}/execute`, override || {});
export const previewStage = (runId: string, stage: string, override?: Partial<StageOverride>) => apiPost(`/runs/${runId}/steps/${stage}/preview`, override || {});
export const selectCandidate = (runId: string, stage: string, candidateId: string) => apiPost(`/runs/${runId}/steps/${stage}/select/${candidateId}`);
export const selectIssues = (runId: string, data: SelectIssues) => apiPost(`/runs/${runId}/critic/select-issues`, data);
export const acceptFinal = (runId: string) => apiPost<{ status: string; source: string; version_number: number }>(`/runs/${runId}/accept`);
export const cancelRun = (runId: string) => apiPost(`/runs/${runId}/cancel`);
