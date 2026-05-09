import { TFunction } from 'i18next';

import { ZentexTask } from './types';

export const taskStartTime = (task: ZentexTask): string | null | undefined => {
  return task.execution_started_at || task.started_at;
};

export const taskEndTime = (task: ZentexTask): string | null | undefined => {
  return task.execution_finished_at || task.completed_at;
};

export const formatTaskDateTime = (value?: string | null): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

export const formatExecutionParty = (task: ZentexTask, t: TFunction): string => {
  const assignment = task.execution_assignment;
  if (assignment?.status === 'assigned') {
    return assignment.label || assignment.executor_id || task.target_id || t('tasks.unassigned');
  }
  if (assignment?.status === 'routed') {
    return assignment.label || assignment.executor_id || task.dispatch_plugin_id || t('tasks.assignmentStatuses.routed');
  }
  if (assignment?.status === 'declared') {
    const declaredType = assignment.executor_type || assignment.executor_id;
    const label = t('tasks.assignmentStatuses.declared');
    return declaredType ? `${label}: ${declaredType}` : label;
  }
  if (assignment?.status === 'pending_dispatch') {
    return t('tasks.assignmentStatuses.pending_dispatch');
  }
  if (assignment?.status === 'assignment_pending') {
    return t('tasks.assignmentStatuses.assignment_pending');
  }
  if (assignment?.status === 'dispatch_blocked') {
    return t('tasks.assignmentStatuses.dispatch_blocked');
  }
  if (assignment?.status === 'unassigned') {
    return t('tasks.assignmentStatuses.unassigned');
  }
  return task.target_id || task.dispatch_plugin_id || t('tasks.unassigned');
};

const isRecord = (value: unknown): value is Record<string, any> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
};

const verifierLabel = (verifier: Record<string, any>): string => {
  const verifierId = typeof verifier.verifier_id === 'string' ? verifier.verifier_id.trim() : '';
  const verifierType = typeof verifier.verifier_type === 'string' ? verifier.verifier_type.trim() : '';
  if (verifierId && verifierType) {
    return `${verifierId} (${verifierType})`;
  }
  return verifierId || verifierType;
};

const configuredVerifierLabels = (task: ZentexTask): string[] => {
  const verification = isRecord(task.contract?.verification) ? task.contract.verification : {};
  if (verification.enabled !== true || !Array.isArray(verification.verifiers)) {
    return [];
  }
  return verification.verifiers
    .filter(isRecord)
    .map(verifierLabel)
    .filter((value) => value.length > 0);
};

const resultVerifierLabels = (task: ZentexTask): string[] => {
  const metadata = task.metadata || {};
  const result = isRecord(metadata.verification_result) ? metadata.verification_result : {};
  const results = Array.isArray(result.verifier_results) ? result.verifier_results : [];
  return results
    .filter(isRecord)
    .map(verifierLabel)
    .filter((value) => value.length > 0);
};

export const formatTaskVerificationMethod = (task: ZentexTask, t: TFunction): string => {
  const configured = configuredVerifierLabels(task);
  if (configured.length > 0) {
    return configured.join('；');
  }

  const observed = resultVerifierLabels(task);
  if (observed.length > 0) {
    return observed.join('；');
  }

  const verification = isRecord(task.contract?.verification) ? task.contract.verification : {};
  if (verification.enabled === true) {
    return t('tasks.verificationStatuses.enabledNoVerifier');
  }
  return t('tasks.verificationStatuses.notConfigured');
};

export const formatBlockedReason = (task: ZentexTask, t: TFunction): string => {
  if (task.status !== 'blocked') {
    return '-';
  }
  const metadata = task.metadata || {};
  const dispatchFailure = metadata.dispatch_failure || {};
  const timeoutRecovery = metadata.timeout_recovery || {};
  const candidates = [
    task.last_error,
    dispatchFailure.message,
    dispatchFailure.reason,
    timeoutRecovery.message,
    timeoutRecovery.recovery_error,
    metadata.blocked_reason,
    metadata.block_reason,
    task.remarks,
  ];
  const reason = candidates.find(value => typeof value === 'string' && value.trim().length > 0);
  return reason ? String(reason) : t('tasks.noBlockedReason');
};

export const canRetryTask = (task: ZentexTask): boolean => {
  return task.status === 'blocked' || task.status === 'failed';
};
