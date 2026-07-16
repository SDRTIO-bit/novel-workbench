import { apiPost } from './client';
import type { ContextPreviewRequest, ContextPreviewResponse } from '../types';

export const previewContext = (data: ContextPreviewRequest) => apiPost<ContextPreviewResponse>('/context/preview', data);
