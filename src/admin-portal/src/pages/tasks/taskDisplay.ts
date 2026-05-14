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

const formatReasonList = (value: unknown): string => {
  if (!Array.isArray(value)) {
    return '';
  }
  return value
    .map((item) => String(item || '').trim())
    .filter((item) => item.length > 0)
    .join('；');
};

const firstString = (...values: unknown[]): string => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
  }
  return '';
};

const sanitizeInternalText = (value: string, t: TFunction): string => {
  return value
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\b(?:internal|external_connector|connector|cli|mcp|agent):[A-Za-z0-9_.:-]+/g, () =>
      t('tasks.exceptionReasons.selectedExecutor', { defaultValue: '指定执行方' }),
    )
    .replace(/\b[A-Za-z]+(?:_[A-Za-z0-9]+){2,}\b/g, (token) => businessCapabilityLabel(token, t))
    .replace(/\s+/g, ' ')
    .trim();
};

const includesToken = (value: unknown, token: string): boolean => {
  if (Array.isArray(value)) {
    return value.some((item) => includesToken(item, token));
  }
  return typeof value === 'string' && value.includes(token);
};

const businessCapabilityLabel = (value: unknown, t: TFunction): string => {
  if (includesToken(value, 'mongodb_csv_inspect')) {
    return t('tasks.exceptionReasons.csvInspectionCapability', {
      defaultValue: 'CSV 文件格式与时间戳检查',
    });
  }
  if (includesToken(value, 'mongodb_csv_import')) {
    return t('tasks.exceptionReasons.csvImportCapability', {
      defaultValue: 'CSV 文件校验与入库',
    });
  }
  if (includesToken(value, 'mongodb_read')) {
    return t('tasks.exceptionReasons.mongoReadCapability', {
      defaultValue: '数据库读取',
    });
  }
  if (includesToken(value, 'mongodb_create') || includesToken(value, 'mongodb_update') || includesToken(value, 'mongodb_delete')) {
    return t('tasks.exceptionReasons.mongoWriteCapability', {
      defaultValue: '数据库写入或修改',
    });
  }
  if (includesToken(value, 'task_evidence')) {
    return t('tasks.exceptionReasons.evidenceCapability', {
      defaultValue: '任务证据提取',
    });
  }
  if (includesToken(value, 'reflection')) {
    return t('tasks.exceptionReasons.reflectionCapability', {
      defaultValue: '反思分析',
    });
  }
  if (includesToken(value, 'oracle')) {
    return t('tasks.exceptionReasons.objectiveCapability', {
      defaultValue: '目标分析',
    });
  }
  if (includesToken(value, 'gemini')) {
    return t('tasks.exceptionReasons.externalModelCapability', {
      defaultValue: '外部模型执行',
    });
  }
  if (includesToken(value, 'execution_local_system')) {
    return t('tasks.exceptionReasons.localExecutionCapability', {
      defaultValue: '本地系统执行',
    });
  }
  return t('tasks.exceptionReasons.requiredBusinessCapability', {
    defaultValue: '所需业务执行能力',
  });
};

const compactBusinessList = (value: unknown, t: TFunction): string => {
  if (!Array.isArray(value)) {
    return businessCapabilityLabel(value, t);
  }
  const labels = value
    .map((item) => {
      const text = String(item || '').trim();
      if (!text) {
        return '';
      }
      if (/^[\u4e00-\u9fa5A-Za-z0-9 ，,。；;：:（）()]+$/.test(text) && !text.includes('_') && !text.includes(':')) {
        return text;
      }
      return businessCapabilityLabel(text, t);
    })
    .filter((item) => item.length > 0);
  return Array.from(new Set(labels)).slice(0, 4).join('、') || businessCapabilityLabel(value, t);
};

const mismatchAnalysisFrom = (...values: unknown[]): Record<string, any> => {
  for (const value of values) {
    if (isRecord(value)) {
      const direct = value.mismatch_analysis;
      if (isRecord(direct)) {
        return direct;
      }
      if (
        typeof value.root_cause === 'string' ||
        typeof value.why_blocked === 'string' ||
        typeof value.operator_action === 'string' ||
        typeof value.required_next_step === 'string'
      ) {
        return value;
      }
    }
  }
  return {};
};

const formatMismatchAnalysisReason = (
  analysis: Record<string, any>,
  t: TFunction,
): string => {
  const cause = firstString(
    analysis.why_blocked,
    analysis.root_cause,
    analysis.problem,
    analysis.why_code_rules_could_not_fully_explain,
  );
  const action = firstString(
    analysis.operator_action,
    analysis.required_next_step,
    analysis.required_executor_or_capability,
  );
  const readableCause = cause ? sanitizeInternalText(cause, t) : '';
  const readableAction = action ? sanitizeInternalText(action, t) : '';
  if (readableCause && readableAction) {
    return t('tasks.exceptionReasons.analysisWithAction', {
      cause: readableCause,
      action: readableAction,
      defaultValue: `原因：${readableCause}。处理建议：${readableAction}`,
    });
  }
  if (readableCause) {
    return t('tasks.exceptionReasons.analysisCauseOnly', {
      cause: readableCause,
      defaultValue: `原因：${readableCause}`,
    });
  }
  return '';
};

const formatBusinessExceptionReason = (
  task: ZentexTask,
  t: TFunction,
  context: {
    dispatchFailure: Record<string, any>;
    g31aAssignment: Record<string, any>;
    g31aEvidence: Record<string, any>;
    suspension: Record<string, any>;
    firstNegotiation: Record<string, any>;
  },
): string => {
  const metadata = task.metadata || {};
  const mismatchAnalysis = mismatchAnalysisFrom(
    context.g31aEvidence.mismatch_analysis,
    metadata.mismatch_analysis,
    context.dispatchFailure.mismatch_analysis,
  );
  const analysisReason = formatMismatchAnalysisReason(mismatchAnalysis, t);
  if (analysisReason) {
    return analysisReason;
  }
  const failureReason = firstString(
    context.g31aEvidence.failure_reason,
    context.dispatchFailure.reason,
    metadata.failure_reason,
  );
  const missing = context.g31aAssignment.missing_resources || context.firstNegotiation.required_asset;
  const capability = compactBusinessList(missing || metadata.required_capabilities, t);
  if (failureReason === 'designated_external_connector_capability_not_available') {
    return t('tasks.exceptionReasons.designatedCapabilityUnavailable', {
      capability,
      defaultValue: `指定执行方不支持${capability}，任务已暂停，等待更换具备该能力的执行方或补齐执行能力。`,
    });
  }

  if (failureReason === 'external_connector_capability_not_specified') {
    return t('tasks.exceptionReasons.connectorCapabilityNotSpecified', {
      defaultValue: '只指定了外部连接器，但没有指定它要执行的具体业务操作，任务已暂停等待补充执行能力。',
    });
  }

  if (failureReason === 'external_connector_health_probe_capability_not_business_executable') {
    return t('tasks.exceptionReasons.healthProbeNotBusinessExecutable', {
      defaultValue: '当前选中的连接器能力只能做连通性检查，不能执行这个业务任务，任务已暂停等待选择真实业务执行能力。',
    });
  }

  if (failureReason === 'designated_owner_not_available' || failureReason === 'required_owner_ref_not_available') {
    return t('tasks.exceptionReasons.designatedOwnerUnavailable', {
      defaultValue: '指定执行方当前未注册、未启用或不可用，任务已暂停等待可用执行方。',
    });
  }

  if (failureReason === 'no_candidate_satisfies_required_capabilities') {
    return t('tasks.exceptionReasons.noExecutorForCapability', {
      capability,
      defaultValue: `当前没有可用执行方支持${capability}，任务已暂停等待注册或启用对应执行方。`,
    });
  }

  const rawReason = firstString(context.suspension.suspension_reason, task.last_error);
  if (rawReason.startsWith('G9 resource gap:') || rawReason.includes('required_capabilities=')) {
    return t('tasks.exceptionReasons.resourceGap', {
      capability,
      defaultValue: `当前缺少${capability}，任务已暂停等待补齐资源。`,
    });
  }

  return '';
};

export const formatTaskExceptionReason = (task: ZentexTask, t: TFunction): string => {
  if (!['blocked', 'suspended', 'failed'].includes(task.status)) {
    return '-';
  }
  const metadata = task.metadata || {};
  const dispatchFailure = isRecord(metadata.dispatch_failure) ? metadata.dispatch_failure : {};
  const timeoutRecovery = isRecord(metadata.timeout_recovery) ? metadata.timeout_recovery : {};
  const g31aAssignment = isRecord(metadata.g31a_assignment) ? metadata.g31a_assignment : {};
  const g31aEvidence = isRecord(g31aAssignment.evidence) ? g31aAssignment.evidence : {};
  const suspension = isRecord(task.suspension)
    ? task.suspension
    : isRecord(metadata.suspension)
      ? metadata.suspension
      : {};
  const negotiations = Array.isArray(metadata.g5_resource_negotiations) ? metadata.g5_resource_negotiations : [];
  const firstNegotiation = negotiations.find(isRecord) || {};
  const businessReason = formatBusinessExceptionReason(task, t, {
    dispatchFailure,
    g31aAssignment,
    g31aEvidence,
    suspension,
    firstNegotiation,
  });
  if (businessReason) {
    return businessReason;
  }
  const candidates = [
    task.last_error,
    suspension.suspension_reason,
    metadata.suspension_reason,
    dispatchFailure.message,
    dispatchFailure.reason,
    timeoutRecovery.message,
    timeoutRecovery.recovery_error,
    metadata.blocked_reason,
    metadata.block_reason,
    metadata.error_reason,
    metadata.failure_reason,
    g31aEvidence.failure_reason,
    formatReasonList(g31aAssignment.missing_resources),
    firstNegotiation.required_asset,
    formatReasonList(metadata.recovery_conditions),
    task.remarks,
  ];
  const reason = candidates.find(value => typeof value === 'string' && value.trim().length > 0);
  return reason ? String(reason) : t('tasks.noBlockedReason');
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

const isInternalVerificationText = (value: string): boolean => {
  return (
    /\b(?:q9_subtask_external_execution_evidence|g31a_executor_bound_subtask_contract|rule_based|verifier_id|VerificationType)\b/i.test(value) ||
    /^[A-Za-z0-9_.:-]+(?:_[A-Za-z0-9_.:-]+){2,}$/.test(value.trim())
  );
};

export const formatTaskVerificationMethod = (task: ZentexTask, t: TFunction): string => {
  const metadata = task.metadata || {};
  const declaredMethod = firstString(
    metadata.q9_verification_hint,
    metadata.q9_blueprint_verification_hint,
    metadata.q9_llm_verification_method,
    metadata.verification_method,
    task.contract?.verification_method,
  );
  if (declaredMethod && !isInternalVerificationText(declaredMethod)) {
    return declaredMethod;
  }

  const acceptanceCriteria = formatReasonList(metadata.acceptance_criteria);
  if (acceptanceCriteria && !isInternalVerificationText(acceptanceCriteria)) {
    return acceptanceCriteria;
  }

  const configured = configuredVerifierLabels(task);
  if (configured.length > 0) {
    return t('tasks.verificationStatuses.internalConfigured');
  }

  const observed = resultVerifierLabels(task);
  if (observed.length > 0) {
    return t('tasks.verificationStatuses.internalConfigured');
  }

  const verification = isRecord(task.contract?.verification) ? task.contract.verification : {};
  if (verification.enabled === true) {
    return t('tasks.verificationStatuses.enabledNoVerifier');
  }
  return t('tasks.verificationStatuses.notConfigured');
};

export const formatBlockedReason = (task: ZentexTask, t: TFunction): string => {
  return formatTaskExceptionReason(task, t);
};

export const canRetryTask = (task: ZentexTask): boolean => {
  return task.status === 'blocked' || task.status === 'failed';
};
