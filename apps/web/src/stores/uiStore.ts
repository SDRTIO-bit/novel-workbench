import { create } from 'zustand';

interface UIState {
  sidebarOpen: boolean;
  rightPanelOpen: boolean;
  selectedChapterId: string | null;
  selectedDocumentKind: string | null;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  setSelectedChapter: (id: string | null) => void;
  setSelectedDocument: (kind: string | null) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  rightPanelOpen: true,
  selectedChapterId: null,
  selectedDocumentKind: null,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setSelectedChapter: (id) => set({ selectedChapterId: id }),
  setSelectedDocument: (kind) => set({ selectedDocumentKind: kind }),
}));
