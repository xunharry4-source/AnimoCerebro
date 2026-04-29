import { useState, useEffect, useRef, useCallback } from 'react';
import { ZentexTask, TasksByStatus } from './types';
import { generateTestTasks, groupTasksByStatus } from './testData';

const TASKS_LIMIT_PER_GROUP = 100;

interface UseTaskManagementReturn {
  tasksByStatus: TasksByStatus;
  loading: boolean;
  error: string | null;
  fetchTasks: () => Promise<void>;
  loadTestTasks: () => void; // Add test data loader
  currentTasks: ZentexTask[];
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
    pending: [],
    waiting_confirmation: [],
    completed: [],
    cancelled: []
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
      params.set("limit_per_group", String(TASKS_LIMIT_PER_GROUP));
      params.set("offset", "0");
      const url = `/api/web/tasks/by-status?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`获取任务列表失败（HTTP ${res.status}）`);
      }
      const data: TasksByStatus = await res.json();
      // Add id field for DataGrid
      const processedData: TasksByStatus = {
        in_progress: data.in_progress.map(t => ({ ...t, id: t.task_id })),
        pending: data.pending.map(t => ({ ...t, id: t.task_id })),
        waiting_confirmation: data.waiting_confirmation.map(t => ({ ...t, id: t.task_id })),
        completed: data.completed.map(t => ({ ...t, id: t.task_id })),
        cancelled: data.cancelled.map(t => ({ ...t, id: t.task_id }))
      };
      setTasksByStatus(processedData);
    } catch (err) {
      console.error('Failed to fetch tasks', err);
      setError(err instanceof Error ? err.message : "获取任务列表失败");
    } finally {
      setLoading(false);
    }
  }, [sourceModuleFilter]);

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

  // Load test tasks
  const loadTestTasks = useCallback(() => {
    console.log('Loading test tasks...');
    const testTasks = generateTestTasks();
    const grouped = groupTasksByStatus(testTasks);
    setTasksByStatus(grouped);
    setError(null);
    setLoading(false);
    console.log(`Loaded ${testTasks.length} test tasks`);
  }, []);

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

  const getCurrentTasks = useCallback((): ZentexTask[] => {
    switch (tabValue) {
      case 0:
        return tasksByStatus.in_progress;
      case 1:
        return tasksByStatus.pending;
      case 2:
        return tasksByStatus.waiting_confirmation;
      case 3:
        return tasksByStatus.completed;
      case 4:
        return tasksByStatus.cancelled;
      default:
        return [];
    }
  }, [tabValue, tasksByStatus]);

  const currentTasks = getCurrentTasks();

  return {
    tasksByStatus,
    loading,
    error,
    fetchTasks,
    loadTestTasks, // Export test data loader
    currentTasks,
    tabValue,
    setTabValue,
    sourceModuleFilter,
    setSourceModuleFilter,
  };
};

export default useTaskManagement;
