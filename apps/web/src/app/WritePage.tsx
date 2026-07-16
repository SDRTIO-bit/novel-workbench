import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useBeforeUnload } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as chaptersApi from '../api/chapters';
import * as projectsApi from '../api/projects';
import { useUIStore } from '../stores/uiStore';
import { useWriteStore } from '../stores/writeStore';
import { WorkflowPanel } from '../features/generation';
import type { ChapterListSchema, ChapterCreate, ChapterUpdate } from '../types';
import { DOCUMENT_KINDS, DOCUMENT_LABELS } from '../types';
import type { DocumentKind } from '../types';
import type { ApiError } from '../api/client';

export default function WritePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    sidebarOpen, rightPanelOpen, selectedChapterId,
    toggleSidebar, toggleRightPanel, setSelectedChapter,
    selectedDocumentKind, setSelectedDocument,
  } = useUIStore();
  const { dirty, activeRunId, setDirty, setLastSaved, setActiveRun } = useWriteStore();

  const [chapterText, setChapterText] = useState('');
  const [chapterTitle, setChapterTitle] = useState('');
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved');
  const [showVersionForm, setShowVersionForm] = useState(false);
  const [versionNote, setVersionNote] = useState('');
  const [sceneInstruction, setSceneInstruction] = useState('');
  const [docText, setDocText] = useState('');
  const [docTitle, setDocTitle] = useState('');

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expectedUpdatedAtRef = useRef<string>('');
  const chapterTextRef = useRef(chapterText);
  const chapterTitleRef = useRef(chapterTitle);
  const chapterIdRef = useRef(selectedChapterId);
  chapterTextRef.current = chapterText;
  chapterTitleRef.current = chapterTitle;
  chapterIdRef.current = selectedChapterId;

  const { data: chapters = [] } = useQuery({
    queryKey: ['chapters', projectId],
    queryFn: () => chaptersApi.listChapters(projectId!),
    enabled: !!projectId,
  });

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.getProject(projectId!),
    enabled: !!projectId,
  });

  const { data: activeRun } = useQuery({
    queryKey: ['run', activeRunId],
    queryFn: () => runsApi.getRun(activeRunId!),
    enabled: !!activeRunId,
  });

  const selectedChapter = chapters.find((c) => c.id === selectedChapterId) as
    | (ChapterListSchema & { current_text?: string })
    | undefined;

  useEffect(() => {
    if (selectedChapter) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      setChapterTitle(selectedChapter.title);
      setChapterText(selectedChapter.current_text || '');
      expectedUpdatedAtRef.current = selectedChapter.updated_at;
      setSaveStatus('saved');
      setDirty(false);
    }
  }, [selectedChapterId]);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const updateChapterMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ChapterUpdate }) =>
      chaptersApi.updateChapter(id, data),
    onSuccess: (result) => {
      expectedUpdatedAtRef.current = result.updated_at;
      setSaveStatus('saved');
      setDirty(false);
      setLastSaved(new Date().toISOString());
      queryClient.invalidateQueries({ queryKey: ['chapters', projectId] });
    },
    onError: (error: ApiError) => {
      if (error.statusCode === 409) {
        const serverText = (error.details as { current_text?: string })?.current_text || '';
        alert(`编辑冲突：内容已被其他用户修改。\n\n服务器当前文本：${serverText}`);
      }
      setSaveStatus('unsaved');
    },
  });

  const debouncedSave = () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const id = chapterIdRef.current;
      if (!id) return;
      setSaveStatus('saving');
      updateChapterMutation.mutate({
        id,
        data: {
          title: chapterTitleRef.current,
          current_text: chapterTextRef.current,
          expected_updated_at: expectedUpdatedAtRef.current,
        },
      });
    }, 800);
  };

  const handleTextChange = (text: string) => {
    setChapterText(text);
    setDirty(true);
    setSaveStatus('unsaved');
    debouncedSave();
  };

  const handleTitleChange = (title: string) => {
    setChapterTitle(title);
    setDirty(true);
    setSaveStatus('unsaved');
    debouncedSave();
  };

  const createChapterMutation = useMutation({
    mutationFn: (data: ChapterCreate) => chaptersApi.createChapter(projectId!, data),
    onSuccess: (newChapter) => {
      queryClient.invalidateQueries({ queryKey: ['chapters', projectId] });
      setSelectedChapter(newChapter.id);
    },
  });

  const reorderMutation = useMutation({
    mutationFn: chaptersApi.reorderChapters,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chapters', projectId] }),
  });

  const createVersionMutation = useMutation({
    mutationFn: ({ chapterId, data }: { chapterId: string; data: { text: string; note?: string; source?: string } }) =>
      chaptersApi.createVersion(chapterId, data),
    onSuccess: () => {
      setShowVersionForm(false);
      setVersionNote('');
      queryClient.invalidateQueries({ queryKey: ['chapter-versions', selectedChapterId] });
    },
  });

  const createRunMutation = useMutation({
    mutationFn: (data: { project_id: string; chapter_id?: string; scene_instruction: string }) =>
      runsApi.createRun(data),
    onSuccess: (run) => {
      setActiveRun(run.id);
      setSceneInstruction('');
    },
  });

  const executeStageMutation = useMutation({
    mutationFn: ({ runId, stage }: { runId: string; stage: string }) =>
      runsApi.executeStage(runId, stage),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['run', activeRunId] }),
  });

  const acceptFinalMutation = useMutation({
    mutationFn: (runId: string) => runsApi.acceptFinal(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chapters', projectId] });
      queryClient.invalidateQueries({ queryKey: ['chapter-versions', selectedChapterId] });
      queryClient.invalidateQueries({ queryKey: ['run', activeRunId] });
      setActiveRun(null);
    },
  });

  const updateDocumentMutation = useMutation({
    mutationFn: ({ kind, data }: { kind: DocumentKind; data: { title?: string; content?: string } }) =>
      projectsApi.updateDocument(projectId!, kind, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      setSelectedDocument(null);
    },
  });

  const documentMap = new Map((project?.documents || []).map((d) => [d.kind, d]));
  const activeDocument = selectedDocumentKind
    ? documentMap.get(selectedDocumentKind as DocumentKind)
    : undefined;

  const moveChapter = (chapter: ChapterListSchema, direction: -1 | 1) => {
    const sorted = [...chapters]
      .filter((c) => !c.deleted_at)
      .sort((a, b) => a.sort_order - b.sort_order);
    const idx = sorted.findIndex((c) => c.id === chapter.id);
    if (idx === -1) return;
    const swapIdx = idx + direction;
    if (swapIdx < 0 || swapIdx >= sorted.length) return;
    reorderMutation.mutate([
      { id: sorted[idx].id, sort_order: sorted[swapIdx].sort_order },
      { id: sorted[swapIdx].id, sort_order: sorted[idx].sort_order },
    ]);
  };

  const openDocument = (kind: DocumentKind) => {
    const doc = documentMap.get(kind);
    setSelectedDocument(kind);
    setDocTitle(doc?.title || DOCUMENT_LABELS[kind] || kind);
    setDocText(doc?.content || '');
  };

  const stepForStage = (stage: Stage) => activeRun?.steps?.find((s) => s.stage === stage);
  const writerHasOutput = () => {
    const step = stepForStage('writer');
    return step?.candidates?.some((c) => c.is_selected && c.text_output);
  };

  useBeforeUnload(
    useCallback(
      (e: BeforeUnloadEvent) => {
        if (dirty) {
          e.preventDefault();
          (e as BeforeUnloadEvent & { returnValue: string }).returnValue = '';
        }
      },
      [dirty],
    ),
  );

  if (!projectId) return null;

  const sortedChapters = [...chapters]
    .filter((c) => !c.deleted_at)
    .sort((a, b) => a.sort_order - b.sort_order);
  const wordCount = chapterText.replace(/\s/g, '').length;

  return (
    <div className="flex h-full overflow-hidden relative">
      {/* Left Sidebar */}
      {sidebarOpen && (
        <aside className="w-64 border-r border-gray-200 bg-gray-50 flex flex-col shrink-0">
          <div className="p-3 border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <button
                onClick={() => navigate('/projects')}
                className="text-gray-400 hover:text-gray-600 shrink-0"
                title="返回项目列表"
              >
                ←
              </button>
              <span className="text-sm font-semibold text-gray-800 truncate">
                {project?.name || '加载中...'}
              </span>
            </div>
            <button
              onClick={toggleSidebar}
              className="text-gray-400 hover:text-gray-600 text-xs p-0.5"
              title="收起侧栏"
            >
              ◀
            </button>
          </div>

          <div className="p-3 border-b border-gray-200">
            <button
              onClick={() => createChapterMutation.mutate({ title: '新章节' })}
              disabled={createChapterMutation.isPending}
              className="w-full px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              新建章节
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            <p className="px-2 py-1 text-xs font-medium text-gray-500 uppercase tracking-wider">
              章节列表
            </p>
            <div className="space-y-0.5">
              {sortedChapters.map((chapter) => (
                <div
                  key={chapter.id}
                  className={`group flex items-center gap-1 px-2 py-1.5 rounded-lg text-sm transition-colors ${
                    selectedChapterId === chapter.id
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <button
                    onClick={() => setSelectedChapter(chapter.id)}
                    className="flex-1 text-left truncate text-xs cursor-pointer"
                  >
                    {chapter.title}
                  </button>
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); moveChapter(chapter, -1); }}
                      className="text-gray-400 hover:text-gray-600 text-xs leading-none px-0.5"
                      title="上移"
                    >
                      ↑
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); moveChapter(chapter, 1); }}
                      className="text-gray-400 hover:text-gray-600 text-xs leading-none px-0.5"
                      title="下移"
                    >
                      ↓
                    </button>
                  </div>
                </div>
              ))}
              {sortedChapters.length === 0 && (
                <p className="px-2 py-2 text-xs text-gray-400">暂无章节</p>
              )}
            </div>

            <p className="px-2 py-1 mt-4 text-xs font-medium text-gray-500 uppercase tracking-wider">
              项目文档
            </p>
            <div className="space-y-0.5">
              {DOCUMENT_KINDS.map((kind) => (
                <button
                  key={kind}
                  onClick={() => openDocument(kind)}
                  className={`w-full text-left px-2 py-1.5 rounded-lg text-xs transition-colors ${
                    selectedDocumentKind === kind
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {DOCUMENT_LABELS[kind]}
                </button>
              ))}
            </div>

            {selectedDocumentKind && activeDocument !== undefined && (
              <div className="mt-3 p-2 bg-white rounded-lg border border-gray-200">
                <input
                  value={docTitle}
                  onChange={(e) => setDocTitle(e.target.value)}
                  className="w-full px-2 py-1 text-xs border border-gray-300 rounded mb-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="文档标题"
                />
                <textarea
                  value={docText}
                  onChange={(e) => setDocText(e.target.value)}
                  className="w-full px-2 py-1 text-xs border border-gray-300 rounded resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  rows={6}
                  placeholder="输入内容..."
                />
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() =>
                      updateDocumentMutation.mutate({
                        kind: selectedDocumentKind as DocumentKind,
                        data: { title: docTitle, content: docText },
                      })
                    }
                    disabled={updateDocumentMutation.isPending}
                    className="flex-1 px-2 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    {updateDocumentMutation.isPending ? '保存中...' : '保存'}
                  </button>
                  <button
                    onClick={() => setSelectedDocument(null)}
                    className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        </aside>
      )}

      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 p-1 bg-white border border-gray-200 rounded-r-lg text-gray-400 hover:text-gray-600 shadow-sm"
          title="展开侧栏"
        >
          ▶
        </button>
      )}

      {/* Center: Chapter Editor */}
      <main className="flex-1 flex flex-col min-w-0">
        {selectedChapter ? (
          <>
            <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white shrink-0 flex-wrap">
              <input
                value={chapterTitle}
                onChange={(e) => handleTitleChange(e.target.value)}
                className="text-lg font-semibold text-gray-900 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-indigo-500 focus:outline-none px-1 py-0.5 min-w-0 flex-1"
              />
              <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-full shrink-0">
                草稿
              </span>
              <span className="text-xs text-gray-400 shrink-0">
                字数: {wordCount.toLocaleString()}
              </span>
              <span
                className={`text-xs shrink-0 ${
                  saveStatus === 'saved'
                    ? 'text-green-600'
                    : saveStatus === 'saving'
                      ? 'text-blue-600'
                      : 'text-orange-600'
                }`}
              >
                {saveStatus === 'saved' ? '已保存' : saveStatus === 'saving' ? '保存中...' : '未保存'}
              </span>
              <button
                onClick={() => setShowVersionForm((v) => !v)}
                className="px-2 py-0.5 text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors shrink-0"
              >
                保存新版本
              </button>
            </div>

            {showVersionForm && (
              <div className="flex items-center gap-2 px-4 py-2 bg-indigo-50 border-b border-indigo-100">
                <input
                  value={versionNote}
                  onChange={(e) => setVersionNote(e.target.value)}
                  placeholder="版本说明..."
                  className="flex-1 px-2 py-1 text-xs border border-indigo-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <button
                  onClick={() => {
                    if (!selectedChapterId || !chapterText) return;
                    createVersionMutation.mutate({
                      chapterId: selectedChapterId,
                      data: { text: chapterText, note: versionNote || undefined, source: 'manual' },
                    });
                  }}
                  disabled={createVersionMutation.isPending}
                  className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                >
                  {createVersionMutation.isPending ? '保存中...' : '确认'}
                </button>
                <button
                  onClick={() => { setShowVersionForm(false); setVersionNote(''); }}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                >
                  取消
                </button>
              </div>
            )}

            <textarea
              value={chapterText}
              onChange={(e) => handleTextChange(e.target.value)}
              className="flex-1 w-full px-4 py-3 text-sm font-mono leading-relaxed resize-none focus:outline-none"
              style={{ minHeight: '60vh' }}
              placeholder="开始写作..."
            />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
            {sortedChapters.length > 0 ? '请从左侧选择一个章节' : '点击"新建章节"开始写作'}
          </div>
        )}
      </main>

      {/* Right Sidebar: Workflow */}
      {rightPanelOpen && (
        <aside className="w-96 border-l border-gray-200 bg-gray-50 flex flex-col shrink-0 overflow-y-auto">
          <div className="p-3 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">五步生成工作流</h2>
            <button
              onClick={toggleRightPanel}
              className="text-gray-400 hover:text-gray-600 text-xs"
              title="收起面板"
            >
              ▶
            </button>
          </div>

          <div className="p-3 flex-1">
            <WorkflowPanel
              projectId={projectId!}
              chapterId={selectedChapterId}
              onAccept={() => {
                queryClient.invalidateQueries({ queryKey: ['chapter-versions', selectedChapterId] });
                setActiveRun(null);
              }}
            />
          </div>
        </aside>
      )}

      {!rightPanelOpen && (
        <button
          onClick={toggleRightPanel}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 p-1 bg-white border border-gray-200 rounded-l-lg text-gray-400 hover:text-gray-600 shadow-sm"
          title="展开面板"
        >
          ◀
        </button>
      )}
    </div>
  );
}
