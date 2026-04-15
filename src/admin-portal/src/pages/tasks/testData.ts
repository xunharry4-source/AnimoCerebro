import { ZentexTask } from './types';

/**
 * 生成测试任务数据,包括主任务和子任务的层级结构
 * 用于在 /console/tasks 页面演示功能
 */
export function generateTestTasks(): ZentexTask[] {
  const now = new Date();
  const daysAgo = (days: number) => new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
  const daysLater = (days: number) => new Date(now.getTime() + days * 24 * 60 * 60 * 1000).toISOString();

  const tasks: ZentexTask[] = [
    // === 主任务 1: 网站重构项目 (进行中) ===
    {
      id: 'TASK-001',
      task_id: 'TASK-001',
      parent_task_id: undefined,
      subtask_ids: ['TASK-001-1', 'TASK-001-2', 'TASK-001-3'],
      subtask_id: '',
      idempotency_key: 'key-001',
      title: '官网前端重构项目',
      task_type: 'development',
      status: 'in_progress',
      priority: 'high',
      progress: 0.65,
      originator_id: 'user_admin',
      target_id: 'project_website',
      remarks: '使用React + TypeScript重构官网,提升性能和用户体验',
      started_at: daysAgo(10),
      created_at: daysAgo(12),
      deadline: daysLater(20),
      tags: ['frontend', 'react', 'refactor'],
      metadata: {
        estimated_hours: 200,
        team_size: 5,
        tech_stack: ['React', 'TypeScript', 'Material-UI']
      }
    },
    
    // 子任务 1-1 (已完成)
    {
      id: 'TASK-001-1',
      task_id: 'TASK-001-1',
      parent_task_id: 'TASK-001',
      subtask_ids: [],
      subtask_id: 'TASK-001-1',
      idempotency_key: 'key-001-1',
      title: '设计系统搭建',
      task_type: 'design',
      status: 'done',
      priority: 'high',
      progress: 1.0,
      originator_id: 'user_designer',
      target_id: 'project_website',
      remarks: '建立统一的设计系统和组件库',
      started_at: daysAgo(10),
      completed_at: daysAgo(5),
      created_at: daysAgo(12),
      tags: ['design-system', 'ui'],
      metadata: { components_count: 45, design_tokens: 120 }
    },
    
    // 子任务 1-2 (进行中)
    {
      id: 'TASK-001-2',
      task_id: 'TASK-001-2',
      parent_task_id: 'TASK-001',
      subtask_ids: [],
      subtask_id: 'TASK-001-2',
      idempotency_key: 'key-001-2',
      title: '核心页面开发',
      task_type: 'development',
      status: 'in_progress',
      priority: 'high',
      progress: 0.75,
      originator_id: 'user_dev1',
      target_id: 'project_website',
      remarks: '开发首页、产品页、关于我们等核心页面',
      started_at: daysAgo(7),
      created_at: daysAgo(10),
      deadline: daysLater(8),
      tags: ['pages', 'development'],
      metadata: { pages_completed: 6, pages_total: 8 }
    },
    
    // 子任务 1-3 (待处理)
    {
      id: 'TASK-001-3',
      task_id: 'TASK-001-3',
      parent_task_id: 'TASK-001',
      subtask_ids: [],
      subtask_id: 'TASK-001-3',
      idempotency_key: 'key-001-3',
      title: '性能优化与测试',
      task_type: 'testing',
      status: 'todo',
      priority: 'medium',
      progress: 0.0,
      originator_id: 'user_qa',
      target_id: 'project_website',
      remarks: '性能测试、SEO优化、跨浏览器兼容性测试',
      started_at: null,
      created_at: daysAgo(10),
      deadline: daysLater(15),
      tags: ['performance', 'testing', 'seo'],
      metadata: { test_cases: 50, browsers: ['Chrome', 'Firefox', 'Safari', 'Edge'] }
    },
    
    // === 主任务 2: API升级 (进行中) ===
    {
      id: 'TASK-002',
      task_id: 'TASK-002',
      parent_task_id: undefined,
      subtask_ids: ['TASK-002-1', 'TASK-002-2'],
      subtask_id: '',
      idempotency_key: 'key-002',
      title: '后端API v2升级',
      task_type: 'backend',
      status: 'in_progress',
      priority: 'high',
      progress: 0.40,
      originator_id: 'user_architect',
      target_id: 'system_api',
      remarks: '升级到RESTful API v2,支持GraphQL查询',
      started_at: daysAgo(5),
      created_at: daysAgo(7),
      deadline: daysLater(25),
      tags: ['api', 'backend', 'graphql'],
      metadata: { endpoints_count: 35, breaking_changes: 8 }
    },
    
    // 子任务 2-1 (已完成)
    {
      id: 'TASK-002-1',
      task_id: 'TASK-002-1',
      parent_task_id: 'TASK-002',
      subtask_ids: [],
      subtask_id: 'TASK-002-1',
      idempotency_key: 'key-002-1',
      title: '数据库迁移脚本',
      task_type: 'database',
      status: 'done',
      priority: 'high',
      progress: 1.0,
      originator_id: 'user_dba',
      target_id: 'system_database',
      remarks: '编写并测试数据库迁移脚本',
      started_at: daysAgo(5),
      completed_at: daysAgo(2),
      created_at: daysAgo(7),
      tags: ['migration', 'database'],
      metadata: { tables_affected: 12, data_volume_gb: 5.2 }
    },
    
    // 子任务 2-2 (进行中)
    {
      id: 'TASK-002-2',
      task_id: 'TASK-002-2',
      parent_task_id: 'TASK-002',
      subtask_ids: [],
      subtask_id: 'TASK-002-2',
      idempotency_key: 'key-002-2',
      title: 'API端点实现',
      task_type: 'development',
      status: 'in_progress',
      priority: 'high',
      progress: 0.50,
      originator_id: 'user_dev2',
      target_id: 'system_api',
      remarks: '实现新的API端点和GraphQL resolvers',
      started_at: daysAgo(3),
      created_at: daysAgo(5),
      deadline: daysLater(18),
      tags: ['api', 'graphql'],
      metadata: { endpoints_done: 18, endpoints_total: 35 }
    },
    
    // === 主任务 3: 安全审计 (等待确认) ===
    {
      id: 'TASK-003',
      task_id: 'TASK-003',
      parent_task_id: undefined,
      subtask_ids: ['TASK-003-1', 'TASK-003-2', 'TASK-003-3', 'TASK-003-4'],
      subtask_id: '',
      idempotency_key: 'key-003',
      title: 'Q2季度安全审计',
      task_type: 'security',
      status: 'waiting_confirmation',
      priority: 'critical',
      progress: 0.85,
      originator_id: 'user_security',
      target_id: 'system_all',
      remarks: '全面的安全审计,包括渗透测试和代码审查',
      started_at: daysAgo(15),
      created_at: daysAgo(18),
      deadline: daysLater(5),
      tags: ['security', 'audit', 'compliance'],
      metadata: { audit_scope: 'full_system', compliance_standards: ['SOC2', 'GDPR', 'ISO27001'] }
    },
    
    // 子任务 3-1 (已完成)
    {
      id: 'TASK-003-1',
      task_id: 'TASK-003-1',
      parent_task_id: 'TASK-003',
      subtask_ids: [],
      subtask_id: 'TASK-003-1',
      idempotency_key: 'key-003-1',
      title: '漏洞扫描',
      task_type: 'security',
      status: 'done',
      priority: 'critical',
      progress: 1.0,
      originator_id: 'user_security',
      target_id: 'system_all',
      remarks: '使用自动化工具进行漏洞扫描',
      started_at: daysAgo(15),
      completed_at: daysAgo(12),
      created_at: daysAgo(18),
      tags: ['vulnerability', 'scanning'],
      metadata: { vulnerabilities_found: 23, critical: 2, high: 5, medium: 10, low: 6 }
    },
    
    // 子任务 3-2 (已完成)
    {
      id: 'TASK-003-2',
      task_id: 'TASK-003-2',
      parent_task_id: 'TASK-003',
      subtask_ids: [],
      subtask_id: 'TASK-003-2',
      idempotency_key: 'key-003-2',
      title: '渗透测试',
      task_type: 'security',
      status: 'done',
      priority: 'critical',
      progress: 1.0,
      originator_id: 'user_pentester',
      target_id: 'system_all',
      remarks: '手动渗透测试,模拟真实攻击场景',
      started_at: daysAgo(12),
      completed_at: daysAgo(8),
      created_at: daysAgo(15),
      tags: ['pentest', 'security'],
      metadata: { attack_vectors_tested: 45, successful_exploits: 3 }
    },
    
    // 子任务 3-3 (已完成)
    {
      id: 'TASK-003-3',
      task_id: 'TASK-003-3',
      parent_task_id: 'TASK-003',
      subtask_ids: [],
      subtask_id: 'TASK-003-3',
      idempotency_key: 'key-003-3',
      title: '代码安全审查',
      task_type: 'code_review',
      status: 'done',
      priority: 'high',
      progress: 1.0,
      originator_id: 'user_reviewer',
      target_id: 'system_codebase',
      remarks: '人工代码审查,重点关注安全相关代码',
      started_at: daysAgo(10),
      completed_at: daysAgo(5),
      created_at: daysAgo(12),
      tags: ['code-review', 'security'],
      metadata: { files_reviewed: 234, issues_found: 15 }
    },
    
    // 子任务 3-4 (进行中)
    {
      id: 'TASK-003-4',
      task_id: 'TASK-003-4',
      parent_task_id: 'TASK-003',
      subtask_ids: [],
      subtask_id: 'TASK-003-4',
      idempotency_key: 'key-003-4',
      title: '审计报告编写',
      task_type: 'documentation',
      status: 'in_progress',
      priority: 'high',
      progress: 0.60,
      originator_id: 'user_security',
      target_id: 'system_all',
      remarks: '编写完整的安全审计报告和修复建议',
      started_at: daysAgo(5),
      created_at: daysAgo(7),
      deadline: daysLater(3),
      tags: ['report', 'documentation'],
      metadata: { sections_completed: 6, sections_total: 10 }
    },
    
    // === 主任务 4: 用户反馈处理 (待处理) ===
    {
      id: 'TASK-004',
      task_id: 'TASK-004',
      parent_task_id: undefined,
      subtask_ids: [],
      subtask_id: '',
      idempotency_key: 'key-004',
      title: '处理用户反馈 #1234-#1250',
      task_type: 'support',
      status: 'todo',
      priority: 'medium',
      progress: 0.0,
      originator_id: 'user_support',
      target_id: 'system_support',
      remarks: '处理本周收集的用户反馈和建议',
      started_at: null,
      created_at: daysAgo(2),
      deadline: daysLater(10),
      tags: ['feedback', 'user-support'],
      metadata: { feedback_count: 17, categories: ['bug', 'feature_request', 'improvement'] }
    },
    
    // === 主任务 5: 已完成的任务 ===
    {
      id: 'TASK-005',
      task_id: 'TASK-005',
      parent_task_id: undefined,
      subtask_ids: ['TASK-005-1', 'TASK-005-2'],
      subtask_id: '',
      idempotency_key: 'key-005',
      title: 'CI/CD流水线优化',
      task_type: 'devops',
      status: 'done',
      priority: 'medium',
      progress: 1.0,
      originator_id: 'user_devops',
      target_id: 'system_cicd',
      remarks: '优化构建和部署流程,减少构建时间',
      started_at: daysAgo(20),
      completed_at: daysAgo(5),
      created_at: daysAgo(22),
      tags: ['cicd', 'devops', 'optimization'],
      metadata: { build_time_before_min: 15, build_time_after_min: 6, improvement_percent: 60 }
    },
    
    // 子任务 5-1 (已完成)
    {
      id: 'TASK-005-1',
      task_id: 'TASK-005-1',
      parent_task_id: 'TASK-005',
      subtask_ids: [],
      subtask_id: 'TASK-005-1',
      idempotency_key: 'key-005-1',
      title: 'Docker镜像优化',
      task_type: 'devops',
      status: 'done',
      priority: 'medium',
      progress: 1.0,
      originator_id: 'user_devops',
      target_id: 'system_docker',
      remarks: '减小Docker镜像体积,加快拉取速度',
      started_at: daysAgo(20),
      completed_at: daysAgo(15),
      created_at: daysAgo(22),
      tags: ['docker', 'optimization'],
      metadata: { image_size_before_mb: 1200, image_size_after_mb: 450 }
    },
    
    // 子任务 5-2 (已完成)
    {
      id: 'TASK-005-2',
      task_id: 'TASK-005-2',
      parent_task_id: 'TASK-005',
      subtask_ids: [],
      subtask_id: 'TASK-005-2',
      idempotency_key: 'key-005-2',
      title: '并行构建配置',
      task_type: 'devops',
      status: 'done',
      priority: 'medium',
      progress: 1.0,
      originator_id: 'user_devops',
      target_id: 'system_cicd',
      remarks: '配置并行构建以加速CI流程',
      started_at: daysAgo(15),
      completed_at: daysAgo(10),
      created_at: daysAgo(17),
      tags: ['parallel', 'build'],
      metadata: { parallel_jobs: 4, time_saved_min: 9 }
    },
    
    // === 主任务 6: 已取消的任务 ===
    {
      id: 'TASK-006',
      task_id: 'TASK-006',
      parent_task_id: undefined,
      subtask_ids: [],
      subtask_id: '',
      idempotency_key: 'key-006',
      title: '移动端App开发(已取消)',
      task_type: 'mobile',
      status: 'cancelled',
      priority: 'low',
      progress: 0.15,
      originator_id: 'user_product',
      target_id: 'project_mobile',
      remarks: '由于战略调整,暂时取消移动端App开发计划',
      started_at: daysAgo(30),
      completed_at: daysAgo(10),
      created_at: daysAgo(35),
      tags: ['mobile', 'cancelled'],
      metadata: { cancel_reason: 'strategic_shift', resources_reallocated: true }
    },
    
    // === 主任务 7: 等待确认的任务 ===
    {
      id: 'TASK-007',
      task_id: 'TASK-007',
      parent_task_id: undefined,
      subtask_ids: ['TASK-007-1'],
      subtask_id: '',
      idempotency_key: 'key-007',
      title: '第三方服务集成评估',
      task_type: 'evaluation',
      status: 'waiting_confirmation',
      priority: 'medium',
      progress: 0.90,
      originator_id: 'user_architect',
      target_id: 'system_integration',
      remarks: '评估多个第三方服务的集成方案,等待管理层确认',
      started_at: daysAgo(8),
      created_at: daysAgo(10),
      deadline: daysLater(7),
      tags: ['integration', 'evaluation', 'third-party'],
      metadata: { services_evaluated: 5, recommended_service: 'ServiceA' }
    },
    
    // 子任务 7-1 (已完成)
    {
      id: 'TASK-007-1',
      task_id: 'TASK-007-1',
      parent_task_id: 'TASK-007',
      subtask_ids: [],
      subtask_id: 'TASK-007-1',
      idempotency_key: 'key-007-1',
      title: '成本效益分析',
      task_type: 'analysis',
      status: 'done',
      priority: 'medium',
      progress: 1.0,
      originator_id: 'user_analyst',
      target_id: 'system_integration',
      remarks: '完成各方案的ROI分析和成本对比',
      started_at: daysAgo(8),
      completed_at: daysAgo(3),
      created_at: daysAgo(10),
      tags: ['cost-analysis', 'roi'],
      metadata: { annual_cost_range: '$50k-$120k', recommended_option_roi: '240%' }
    },
  ];

  return tasks;
}

/**
 * 将测试任务按状态分组
 */
export function groupTasksByStatus(tasks: ZentexTask[]) {
  return {
    in_progress: tasks.filter(t => t.status === 'in_progress'),
    pending: tasks.filter(t => t.status === 'todo' || t.status === 'blocked'),
    waiting_confirmation: tasks.filter(t => t.status === 'waiting_confirmation'),
    completed: tasks.filter(t => t.status === 'done'),
    cancelled: tasks.filter(t => t.status === 'cancelled' || t.status === 'archived')
  };
}
