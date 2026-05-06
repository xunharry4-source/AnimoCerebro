from __future__ import annotations

from zentex.tasks.management.task_completion_verification_mixin import TaskServiceCompletionVerificationMixin
from zentex.tasks.management.verification_failure_mixin import TaskServiceVerificationFailureMixin


class TaskServiceVerificationCompletionMixin(
    TaskServiceCompletionVerificationMixin,
    TaskServiceVerificationFailureMixin,
):
    pass
