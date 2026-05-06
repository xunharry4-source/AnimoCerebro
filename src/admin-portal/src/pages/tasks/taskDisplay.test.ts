import { describe, expect, it } from 'vitest';

import {
  canRetryTask,
  formatBlockedReason,
  formatExecutionParty,
  formatTaskDateTime,
  formatTaskVerificationMethod,
  taskEndTime,
  taskStartTime,
} from './taskDisplay';
import { ZentexTask } from './types';

const t = (key: string) => {
  const labels: Record<string, string> = {
    'tasks.assignmentStatuses.pending_dispatch': 'Pending Dispatch',
    'tasks.assignmentStatuses.assignment_pending': 'Waiting for Executor Assignment',
    'tasks.assignmentStatuses.dispatch_blocked': 'Dispatch Blocked',
    'tasks.assignmentStatuses.declared': 'Declared Executor, Not Bound',
    'tasks.unassigned': 'Unassigned',
    'tasks.noBlockedReason': 'No blocked reason',
    'tasks.verificationStatuses.enabledNoVerifier': 'Verification enabled, but no real verifier is configured',
    'tasks.verificationStatuses.notConfigured': 'No real verifier configured',
  };
  return labels[key] || key;
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

  it('formats verification method from real verifier configuration only', () => {
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
                  verifier_id: 'q8_required_outcome_evidence',
                  verifier_type: 'rule_based',
                },
              ],
            },
          },
        },
        t as any,
      ),
    ).toBe('q8_required_outcome_evidence (rule_based)');

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
});
