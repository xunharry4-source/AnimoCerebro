import { describe, expect, it } from 'vitest';

import {
  canRetryTask,
  formatBlockedReason,
  formatExecutionParty,
  formatTaskDateTime,
  formatTaskExceptionReason,
  formatTaskVerificationMethod,
  taskEndTime,
  taskStartTime,
} from './taskDisplay';
import { ZentexTask } from './types';

const t = (key: string, options?: Record<string, string>) => {
  const labels: Record<string, string> = {
    'tasks.assignmentStatuses.pending_dispatch': 'Pending Dispatch',
    'tasks.assignmentStatuses.assignment_pending': 'Waiting for Executor Assignment',
    'tasks.assignmentStatuses.dispatch_blocked': 'Dispatch Blocked',
    'tasks.assignmentStatuses.declared': 'Declared Executor, Not Bound',
    'tasks.unassigned': 'Unassigned',
    'tasks.noBlockedReason': 'No blocked reason',
    'tasks.exceptionReasons.csvInspectionCapability': 'CSV file format and timestamp inspection',
    'tasks.exceptionReasons.localExecutionCapability': 'local system execution',
    'tasks.exceptionReasons.selectedExecutor': 'the selected executor',
    'tasks.exceptionReasons.analysisWithAction': 'Reason: {{cause}} Suggested action: {{action}}',
    'tasks.exceptionReasons.analysisCauseOnly': 'Reason: {{cause}}',
    'tasks.exceptionReasons.designatedCapabilityUnavailable':
      'The selected executor cannot perform {{capability}}. The task is paused until an executor with that capability is selected or enabled.',
    'tasks.exceptionReasons.resourceGap': 'Missing {{capability}}. The task is paused until that resource is available.',
    'tasks.verificationStatuses.internalConfigured':
      'Internal verification is configured, but no displayable Q9 verification instruction is available',
    'tasks.verificationStatuses.enabledNoVerifier': 'Verification enabled, but no real verifier is configured',
    'tasks.verificationStatuses.notConfigured': 'No real verifier configured',
  };
  let value = labels[key] || key;
  for (const [name, replacement] of Object.entries(options || {})) {
    value = value.replaceAll(`{{${name}}}`, String(replacement));
  }
  return value;
};

const baseTask: ZentexTask = {
  id: 'task-1',
  task_id: 'task-1',
  subtask_id: 'local-1',
  idempotency_key: 'idem-1',
  title: 'Render task list fields',
  task_type: 'system_action',
  status: 'todo',
  progress: 0,
  originator_id: 'ci',
  remarks: null,
  started_at: null,
};

describe('taskDisplay', () => {
  it('prefers physical execution timestamps over lifecycle timestamps for list display', () => {
    const task: ZentexTask = {
      ...baseTask,
      started_at: '2026-05-01T08:09:10+00:00',
      completed_at: '2026-05-01T08:13:14+00:00',
      execution_started_at: '2026-05-01T08:10:11+00:00',
      execution_finished_at: '2026-05-01T08:12:13+00:00',
    };

    expect(taskStartTime(task)).toBe('2026-05-01T08:10:11+00:00');
    expect(taskEndTime(task)).toBe('2026-05-01T08:12:13+00:00');
    expect(formatTaskDateTime(taskStartTime(task))).toMatch(/2026|5\/1\/2026|01\/05\/2026|2026\/5\/1/);
  });

  it('shows only registry-confirmed execution assignments as real execution parties', () => {
    expect(
      formatExecutionParty(
        {
          ...baseTask,
          execution_assignment: {
            status: 'assigned',
            source: 'target_id',
            executor_id: 'cli:gemini',
            executor_type: 'cli',
            label: 'cli:gemini',
          },
        },
        t as any,
      ),
    ).toBe('cli:gemini');

    expect(
      formatExecutionParty(
        {
          ...baseTask,
          execution_assignment: {
            status: 'declared',
            source: 'metadata',
            executor_id: 'external_connector',
            executor_type: 'external_connector',
            label: 'external_connector',
          },
        },
        t as any,
      ),
    ).toBe('Declared Executor, Not Bound: external_connector');

    expect(
      formatExecutionParty(
        {
          ...baseTask,
          execution_assignment: {
            status: 'dispatch_blocked',
            source: 'none',
            executor_id: '',
            executor_type: '',
            label: '',
          },
        },
        t as any,
      ),
    ).toBe('Dispatch Blocked');

    expect(formatExecutionParty({ ...baseTask, target_id: 'agent:reviewer' }, t as any)).toBe('agent:reviewer');
  });

  it('formats verification method from Q9 display instruction and hides internal verifier ids', () => {
    expect(
      formatTaskVerificationMethod(
        {
          ...baseTask,
          metadata: {
            q9_verification_hint: '读取 connector output_summary 与 evidence_refs，确认 CSV 文件行数和时间戳统计存在。',
          },
          contract: {
            verification_method: 'q9_subtask_external_execution_evidence',
            verification: {
              enabled: true,
              verifiers: [
                {
                  verifier_id: 'q8_required_outcome_evidence',
                  verifier_type: 'rule_based',
                },
              ],
            },
          },
        },
        t as any,
      ),
    ).toBe('读取 connector output_summary 与 evidence_refs，确认 CSV 文件行数和时间戳统计存在。');

    expect(
      formatTaskVerificationMethod(
        {
          ...baseTask,
          contract: {
            verification_method: 'fake_unknown_code_path',
            verification: {
              enabled: true,
              verifiers: [
                {
                  verifier_id: 'q9_subtask_external_execution_evidence',
                  verifier_type: 'rule_based',
                },
              ],
            },
          },
        },
        t as any,
      ),
    ).toBe('Internal verification is configured, but no displayable Q9 verification instruction is available');

    expect(
      formatTaskVerificationMethod(
        {
          ...baseTask,
          contract: {
            verification_method: 'fake_unknown_code_path',
            verification: {
              enabled: true,
              verifiers: [],
            },
          },
        },
        t as any,
      ),
    ).toBe('Verification enabled, but no real verifier is configured');
    expect(formatTaskVerificationMethod(baseTask, t as any)).toBe('No real verifier configured');
  });

  it('shows real blocked reason and marks blocked tasks retryable', () => {
    const blockedTask: ZentexTask = {
      ...baseTask,
      status: 'blocked',
      last_error: 'No matching executor found for required capabilities',
      metadata: {
        dispatch_failure: {
          message: 'Router could not find a q8 executor',
        },
      },
    };

    expect(formatBlockedReason(blockedTask, t as any)).toBe('No matching executor found for required capabilities');
    expect(canRetryTask(blockedTask)).toBe(true);
    expect(canRetryTask({ ...baseTask, status: 'todo' })).toBe(false);
    expect(formatBlockedReason({ ...blockedTask, last_error: '', metadata: {} }, t as any)).toBe('No blocked reason');
  });

  it('shows suspended task reason from real suspension and G31A metadata', () => {
    const suspendedTask: ZentexTask = {
      ...baseTask,
      status: 'suspended',
      suspension: {
        task_id: 'task-1',
        original_status: 'assignment_pending',
        suspension_reason: 'G9 resource gap: mongodb_csv_inspect',
        recovery_conditions: ['Register a connector with mongodb_csv_inspect'],
      },
      metadata: {
        target_id: 'external_connector:mongodb_crud_connector',
        g31a_assignment: {
          status: 'suspended_resource_gap',
          missing_resources: ['mongodb_csv_inspect'],
          evidence: {
            failure_reason: 'designated_external_connector_capability_not_available',
          },
        },
      },
    };

    expect(formatTaskExceptionReason(suspendedTask, t as any)).toBe(
      'The selected executor cannot perform CSV file format and timestamp inspection. The task is paused until an executor with that capability is selected or enabled.',
    );
    expect(formatTaskExceptionReason(suspendedTask, t as any)).not.toContain(
      'designated_external_connector_capability_not_available',
    );
    expect(formatTaskExceptionReason(suspendedTask, t as any)).not.toContain('mongodb_csv_inspect');
    expect(formatTaskExceptionReason(suspendedTask, t as any)).not.toContain('external_connector');
  });

  it('uses stored mismatch analysis and sanitizes internal identifiers', () => {
    const suspendedTask: ZentexTask = {
      ...baseTask,
      status: 'suspended',
      metadata: {
        g31a_assignment: {
          evidence: {
            mismatch_analysis: {
              root_cause:
                'The assignment requires `mongodb_csv_inspect` to read and validate CSV file data, but external_connector:mongodb_crud_connector does not provide it.',
              operator_action:
                'Execute with external_connector:task-mongodb-csv-88de354c.mongodb_csv_inspect or acquire execution_local_system.',
            },
          },
        },
      },
    };

    const reason = formatTaskExceptionReason(suspendedTask, t as any);

    expect(reason).toContain('Reason:');
    expect(reason).toContain('CSV file format and timestamp inspection');
    expect(reason).toContain('the selected executor');
    expect(reason).not.toContain('mongodb_csv_inspect');
    expect(reason).not.toContain('external_connector');
    expect(reason).not.toContain('execution_local_system');
  });
});
