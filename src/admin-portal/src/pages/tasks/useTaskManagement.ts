import { useState, useEffect, useRef, useCallback } from 'react';
import { TaskGarbageAnalysisReport, TaskGroupCounts, TaskPageResponse, TaskPresentationGroup, TasksByStatus, ZentexTask } from './types';

const DEFAULT_PAGE_SIZE = 25;
const TASK_PAGE_FETCH_TIMEOUT_MS = 10000;
const EMPTY_COUNTS: TaskGroupCounts = {
  all: 0,
  in_progress: 0,
  todo: 0,
  blocked: 0,
  pending: 0,
  waiting_confirmation: 0,
  completed: 0,
  failed: 0,
  suspended: 0,
  archived: 0,
  cancelled: 0,
};

const TAB_GROUPS: TaskPresentationGroup[] = [
  'all',
  'in_progress',
  'todo',
  'blocked',
  'waiting_confirmation',
  'completed',
  'failed',
  'suspended',
  'archived',
  'cancelled',
];

interface PaginationModel {
  page: number;
  pageSize: number;
}

interface UseTaskManagementReturn {
  tasksByStatus: TasksByStatus;
  currentRows: ZentexTask[];
  rowCount: number;
  groupCounts: TaskGroupCounts;
  paginationModel: PaginationModel;
  setPaginationModel: (value: PaginationModel) => void;
  loading: boolean;
  error: string | null;
  garbageAnalysis: TaskGarbageAnalysisReport | null;
  garbageAnalysisLoading: boolean;
  garbageAnalysisError: string | null;
  fetchTasks: () => Promise<void>;
  fetchGarbageAnalysis: (enableLlmSemanticScoring?: boolean) => Promise<void>;
  tabValue: number;
  setTabValue: (value: number) => void;
  sourceModuleFilter: string;
  setSourceModuleFilter: (value: string) => void;
}

const useTaskManagement = (): UseTaskManagementReturn => {
  const [tabValue, setTabValue] = useState(0);
  const [sourceModuleFilter, setSourceModuleFilter] = useState("all");
  const [tasksByStatus, setTasksByStatus] = useState<TasksByStatus>({
    all: [],
    in_progress: [],
    todo: [],
    blocked: [],
    pending: [],
    waiting_confirmation: [],
    completed: [],
    failed: [],
    suspended: [],
    archived: [],
    cancelled: []
  });
  const [groupCounts, setGroupCounts] = useState<TaskGroupCounts>(EMPTY_COUNTS);
  const [paginationModel, setPaginationModel] = useState<PaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [garbageAnalysis, setGarbageAnalysis] = useState<TaskGarbageAnalysisReport | null>(null);
  const [garbageAnalysisLoading, setGarbageAnalysisLoading] = useState(false);
  const [garbageAnalysisError, setGarbageAnalysisError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), TASK_PAGE_FETCH_TIMEOUT_MS);
    try {
      const params = new URLSearchParams();
      if (sourceModuleFilter !== "all") {
        params.set("source_module", sourceModuleFilter);
      }
      const group = TAB_GROUPS[tabValue] ?? 'all';
      params.set("group", group);
      params.set("root_only", "true");
      params.set("limit", String(paginationModel.pageSize));
      params.set("offset", String(paginationModel.page * paginationModel.pageSize));
      const url = `/api/web/tasks/page?${params.toString()}`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        throw new Error(`获取任务列表失败（HTTP ${res.status}）`);
      }
      const data: TaskPageResponse = await res.json();
      const rows = data.items.map(t => ({ ...t, id: t.task_id }));
      const processedData: TasksByStatus = {
        all: [],
        in_progress: [],
        todo: [],
        blocked: [],
        pending: [],
        waiting_confirmation: [],
        completed: [],
        failed: [],
        suspended: [],
        archived: [],
        cancelled: [],
        [group]: rows,
      };
      setTasksByStatus(processedData);
      setGroupCounts(data.counts);
    } catch (err) {
      console.error('Failed to fetch tasks', err);
      if (err instanceof DOMException && err.name === "AbortError") {
        setError(`获取任务列表超时（${TASK_PAGE_FETCH_TIMEOUT_MS / 1000} 秒），请检查后端 /api/web/tasks/page 是否正常响应。`);
      } else {
        setError(err instanceof Error ? err.message : "获取任务列表失败");
      }
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }, [paginationModel.page, paginationModel.pageSize, sourceModuleFilter, tabValue]);

  const fetchGarbageAnalysis = useCallback(async (enableLlmSemanticScoring = false) => {
    setGarbageAnalysisLoading(true);
    setGarbageAnalysisError(null);
    try {
      const params = new URLSearchParams();
      params.set("stale_after_seconds", "300");
      params.set("enable_llm_semantic_scoring", String(enableLlmSemanticScoring));
      const res = await fetch(`/api/web/tasks/garbage-analysis?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`获取垃圾与重复任务分析失败（HTTP ${res.status}）`);
      }
      const data: TaskGarbageAnalysisReport = await res.json();
      setGarbageAnalysis(data);
    } catch (err) {
      console.error('Failed to fetch task garbage analysis', err);
      setGarbageAnalysisError(err instanceof Error ? err.message : "获取垃圾与重复任务分析失败");
    } finally {
      setGarbageAnalysisLoading(false);
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/web/tasks/stream`;
    
    console.log('Connecting to task stream:', wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Task stream connected');
      setError(null);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'task_update') {
          fetchTasks();
          console.log(`Task update received`);
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = (event) => {
      console.log('Task stream disconnected', event.code, event.reason);
      wsRef.current = null;
      
      if (event.code !== 1000 && !event.wasClean) {
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...');
          connectWebSocket();
        }, 3000);
      }
    };
  }, [fetchTasks]);

  useEffect(() => {
    fetchTasks();
    fetchGarbageAnalysis(false);
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounting');
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [fetchTasks, fetchGarbageAnalysis, connectWebSocket]);

  const handleSetTabValue = useCallback((value: number) => {
    setTabValue(value);
    setPaginationModel(previous => ({ ...previous, page: 0 }));
  }, []);

  const handleSetSourceModuleFilter = useCallback((value: string) => {
    setSourceModuleFilter(value);
    setPaginationModel(previous => ({ ...previous, page: 0 }));
  }, []);

  const currentGroup = TAB_GROUPS[tabValue] ?? 'all';
  const getCurrentTasks = useCallback((): ZentexTask[] => {
    return tasksByStatus[currentGroup] ?? [];
  }, [currentGroup, tasksByStatus]);

  const currentTasks = getCurrentTasks();

  return {
    tasksByStatus,
    currentRows: currentTasks,
    rowCount: groupCounts[currentGroup] ?? 0,
    groupCounts,
    paginationModel,
    setPaginationModel,
    loading,
    error,
    garbageAnalysis,
    garbageAnalysisLoading,
    garbageAnalysisError,
    fetchTasks,
    fetchGarbageAnalysis,
    tabValue,
    setTabValue: handleSetTabValue,
    sourceModuleFilter,
    setSourceModuleFilter: handleSetSourceModuleFilter,
  };
};

export default useTaskManagement;
