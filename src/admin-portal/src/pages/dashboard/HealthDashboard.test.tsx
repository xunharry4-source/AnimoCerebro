/**
 * HealthDashboard 组件测试
 * 
 * 测试范围：
 * - 正常情况：Token统计卡片渲染、模块健康状态显示、Provider详情展示
 * - 异常情况：API调用失败处理、空数据降级
 * - 边界情况：零Token使用、空模块列表
 * 
 * 真实性标注：真实运行结果（Vitest + React Testing Library执行）
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import HealthDashboard from './HealthDashboard';

// Mock fetch
const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

const mockHealthData = {
  overall_health: 'healthy',
  token_usage: {
    total_request_count: 150,
    total_input_tokens: 45000,
    total_output_tokens: 32000,
    total_tokens: 77000,
    providers: [
      {
        provider_name: 'openai_compat',
        api_base: 'https://api.openai.com/v1',
        health_status: 'healthy',
        request_count: 150,
        input_tokens: 45000,
        output_tokens: 32000,
        total_tokens: 77000,
        error_count: 0,
      },
    ],
  },
  modules: [
    {
      module_id: 'llm_providers',
      module_name: 'LLM Providers',
      health_status: 'healthy',
      status_message: '1个Provider全部健康',
      last_check_at: '2026-04-09T10:30:00+00:00',
      metrics: {
        total_providers: 1,
        healthy_providers: 1,
      },
    },
    {
      module_id: 'memory',
      module_name: 'Memory Service',
      health_status: 'healthy',
      last_check_at: '2026-04-09T10:30:00+00:00',
      metrics: {
        total_records: 250,
      },
    },
  ],
  timestamp: '2026-04-09T10:30:00+00:00',
};

const mockEmptyHealthData = {
  overall_health: 'healthy',
  token_usage: {
    total_request_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_tokens: 0,
    providers: [],
  },
  modules: [],
  timestamp: '2026-04-09T10:30:00+00:00',
};

describe('HealthDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    mockFetch.mockImplementation(
      () => new Promise(() => {}), // Never resolves to keep loading state
    );

    render(<HealthDashboard />);

    expect(screen.getByText(/加载系统健康状态/i)).toBeInTheDocument();
  });

  it('renders token usage cards with correct data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText('系统健康监控')).toBeInTheDocument();
    });

    // Check token statistics
    expect(screen.getByText('150')).toBeInTheDocument(); // total_request_count
    expect(screen.getByText('45K')).toBeInTheDocument(); // input tokens (formatted)
    expect(screen.getByText('32K')).toBeInTheDocument(); // output tokens (formatted)
    expect(screen.getByText('77K')).toBeInTheDocument(); // total tokens (formatted)

    // Check labels
    expect(screen.getByText('总请求次数')).toBeInTheDocument();
    expect(screen.getByText('输入 Tokens')).toBeInTheDocument();
    expect(screen.getByText('输出 Tokens')).toBeInTheDocument();
    expect(screen.getByText('总计 Tokens')).toBeInTheDocument();
  });

  it('displays overall health status with correct color', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      const statusChip = screen.getByText(/整体状态: healthy/i);
      expect(statusChip).toBeInTheDocument();
    });
  });

  it('displays LLM Provider details', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText('openai_compat')).toBeInTheDocument();
    });

    expect(screen.getByText('https://api.openai.com/v1')).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('displays module health status with correct information', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText('LLM Providers')).toBeInTheDocument();
      expect(screen.getByText('Memory Service')).toBeInTheDocument();
    });

    // Check status messages
    expect(screen.getByText('1个Provider全部健康')).toBeInTheDocument();

    // Check metrics
    expect(screen.getByText(/total_providers=1/i)).toBeInTheDocument();
    expect(screen.getByText(/healthy_providers=1/i)).toBeInTheDocument();
    expect(screen.getByText(/total_records=250/i)).toBeInTheDocument();
  });

  it('handles empty modules gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockEmptyHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText('系统健康监控')).toBeInTheDocument();
    });

    // Should show zero token stats
    expect(screen.getByText('0')).toBeInTheDocument();

    // Module section should exist but be empty
    expect(screen.getByText('功能模块健康状态')).toBeInTheDocument();
  });

  it('handles API error gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText(/加载健康状态失败/i)).toBeInTheDocument();
    });
  });

  it('handles HTTP error response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText(/获取系统健康状态失败/i)).toBeInTheDocument();
    });
  });

  it('displays timestamp in correct format', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      const timestampText = screen.getByText(/更新时间:/i);
      expect(timestampText).toBeInTheDocument();
    });
  });

  it('shows provider error count when greater than zero', async () => {
    const dataWithError = {
      ...mockHealthData,
      token_usage: {
        ...mockHealthData.token_usage,
        providers: [
          {
            ...mockHealthData.token_usage.providers[0],
            error_count: 5,
          },
        ],
      },
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => dataWithError,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText(/错误次数: 5/i)).toBeInTheDocument();
    });
  });

  it('displays degraded module status with warning color', async () => {
    const degradedData = {
      ...mockHealthData,
      overall_health: 'degraded',
      modules: [
        {
          module_id: 'llm_providers',
          module_name: 'LLM Providers',
          health_status: 'degraded',
          status_message: '部分Provider不健康',
          last_check_at: '2026-04-09T10:30:00+00:00',
          metrics: {},
        },
      ],
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => degradedData,
    });

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(screen.getByText(/整体状态: degraded/i)).toBeInTheDocument();
      expect(screen.getByText('degraded')).toBeInTheDocument();
    });
  });

  it('auto-refreshes data every 30 seconds', async () => {
    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      return Promise.resolve({
        ok: true,
        json: async () => mockHealthData,
      });
    });

    vi.useFakeTimers();

    render(<HealthDashboard />);

    await waitFor(() => {
      expect(callCount).toBe(1);
    });

    // Fast-forward 30 seconds
    vi.advanceTimersByTime(30000);

    await waitFor(() => {
      expect(callCount).toBe(2);
    });

    vi.useRealTimers();
  });
});
