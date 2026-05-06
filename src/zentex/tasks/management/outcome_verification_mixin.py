from __future__ import annotations

from zentex.tasks.management.audit_outcome_mixin import TaskServiceAuditOutcomeMixin
from zentex.tasks.management.recovery_statistics_mixin import TaskServiceRecoveryStatisticsMixin
from zentex.tasks.management.verification_completion_mixin import TaskServiceVerificationCompletionMixin
from zentex.tasks.management.verification_records_mixin import TaskServiceVerificationRecordsMixin


class TaskServiceOutcomeVerificationMixin(
    TaskServiceAuditOutcomeMixin,
    TaskServiceRecoveryStatisticsMixin,
    TaskServiceVerificationCompletionMixin,
    TaskServiceVerificationRecordsMixin,
):
    pass
