import { create } from 'zustand';

interface WriteState {
  dirty: boolean;
  lastSavedAt: string | null;
  activeRunId: string | null;
  setDirty: (d: boolean) => void;
  setLastSaved: (t: string) => void;
  setActiveRun: (id: string | null) => void;
}

export const useWriteStore = create<WriteState>((set) => ({
  dirty: false,
  lastSavedAt: null,
  activeRunId: null,
  setDirty: (d) => set({ dirty: d }),
  setLastSaved: (t) => set({ lastSavedAt: t }),
  setActiveRun: (id) => set({ activeRunId: id }),
}));
