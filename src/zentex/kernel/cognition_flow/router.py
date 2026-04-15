"""NineQuestionRouter — plans which questions to execute for a given state."""

from zentex.kernel.cognition_flow.models import (
    BootstrapStatus,
    DEFAULT_NINE_QUESTIONS,
    NineQuestion,
    NineQuestionState,
)


class NineQuestionRouter:
    """Decides which nine-questions should be executed given the current state.

    Routing logic:
    - Cold start (not_started): all questions run.
    - Any other status: only questions that lack a valid answer are included.
    """

    def __init__(self, questions: list[NineQuestion] | None = None) -> None:
        self._questions: list[NineQuestion] = questions or list(DEFAULT_NINE_QUESTIONS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(self, state: NineQuestionState) -> list[NineQuestion]:
        """Return the list of questions to execute for *state*.

        On a cold start (not_started) every question is returned.  Otherwise
        only unanswered or errored questions are included.
        """
        if state.bootstrap_status == BootstrapStatus.not_started:
            return list(self._questions)

        unanswered: list[NineQuestion] = []
        for q in self._questions:
            resp = state.responses.get(q.question_id)
            if resp is None or not resp.answer or resp.error:
                unanswered.append(q)
        return unanswered

    def needs_bootstrap(self, state: NineQuestionState) -> bool:
        """Return True if the bootstrap process should (re-)run."""
        return state.bootstrap_status in (
            BootstrapStatus.not_started,
            BootstrapStatus.failed,
        )

    def get_execution_order(self, planned: list[NineQuestion]) -> list[NineQuestion]:
        """Return *planned* sorted by priority ascending (lower = higher priority)."""
        return sorted(planned, key=lambda q: q.priority)
