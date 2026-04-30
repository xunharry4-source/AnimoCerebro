import { useState, useEffect, useRef, useCallback } from 'react';
import { TaskGroupCounts, TaskPageResponse, TaskPresentationGroup, TasksByStatus, ZentexTask } from './types';

const DEFAULT_PAGE_SIZE = 25;
const EMPTY_COUNTS: TaskGroupCounts = {
  in_progress: 0,
  todo: 0,
  blocked: 0,
  pending: 0,
  waiting_confirmation: 0,
  completed: 0,
  cancelled: 0,
};

const TAB_GROUPS: TaskPresentationGroup[] = [
  'in_progress',
  'todo',
  'blocked',
  'waiting_confirmation',
  'completed',
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
  fetchTasks: () => Promise<void>;
  tabValue: number;
  setTabValue: (value: number) => void;
  sourceModuleFilter: string;
  setSourceModuleFilter: (value: string) => void;
}

const useTaskManagement = (): UseTaskManagementReturn => {
  const [tabValue, setTabValue] = useState(0);
  const [sourceModuleFilter, setSourceModuleFilter] = useState("all");
  const [tasksByStatus, setTasksByStatus] = useState<TasksByStatus>({
    in_progress: [],
    todo: [],
    blocked: [],
    pending: [],
    waiting_confirmation: [],
    completed: [],
    cancelled: []
  });
  const [groupCounts, setGroupCounts] = useState<TaskGroupCounts>(EMPTY_COUNTS);
  const [paginationModel, setPaginationModel] = useState<PaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (sourceModuleFilter !== "all") {
        params.set("source_module", sourceModuleFilter);
      }
      const group = TAB_GROUPS[tabValue] ?? 'completed';
      params.set("group", group);
      params.set("limit", String(paginationModel.pageSize));
      params.set("offset", String(paginationModel.page * paginationModel.pageSize));
      const url = `/api/web/tasks/page?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`获取任务列表失败（HTTP ${res.status}）`);
      }
      const data: TaskPageResponse = await res.json();
      const rows = data.items.map(t => ({ ...t, id: t.task_id }));
      const processedData: TasksByStatus = {
        in_progress: [],
        todo: [],
        blocked: [],
        pending: [],
        waiting_confirmation: [],
        completed: [],
        cancelled: [],
        [group]: rows,
      };
      setTasksByStatus(processedData);
      setGroupCounts(data.counts);
    } catch (err) {
      console.error('Failed to fetch tasks', err);
      setError(err instanceof Error ? err.message : "获取任务列表失败");
    } finally {
      setLoading(false);
    }
  }, [paginationModel.page, paginationModel.pageSize, sourceModuleFilter, tabValue]);

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
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounting');
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [fetchTasks, connectWebSocket]);

  const handleSetTabValue = useCallback((value: number) => {
    setTabValue(value);
    setPaginationModel(previous => ({ ...previous, page: 0 }));
  }, []);

  const handleSetSourceModuleFilter = useCallback((value: string) => {
    setSourceModuleFilter(value);
    setPaginationModel(previous => ({ ...previous, page: 0 }));
  }, []);

  const getCurrentTasks = useCallback((): ZentexTask[] => {
    switch (tabValue) {
      case 0:
        return tasksByStatus.in_progress;
      case 1:
        return tasksByStatus.todo ?? [];
      case 2:
        return tasksByStatus.blocked ?? [];
      case 3:
        return tasksByStatus.waiting_confirmation;
      case 4:
        return tasksByStatus.completed;
      case 5:
        return tasksByStatus.cancelled;
      default:
        return [];
    }
  }, [tabValue, tasksByStatus]);

  const currentTasks = getCurrentTasks();
  const currentGroup = TAB_GROUPS[tabValue] ?? 'completed';

  return {
    tasksByStatus,
    currentRows: currentTasks,
    rowCount: groupCounts[currentGroup] ?? 0,
    groupCounts,
    paginationModel,
    setPaginationModel,
    loading,
    error,
    fetchTasks,
    tabValue,
    setTabValue: handleSetTabValue,
    sourceModuleFilter,
    setSourceModuleFilter: handleSetSourceModuleFilter,
  };
};

export default useTaskManagement;
