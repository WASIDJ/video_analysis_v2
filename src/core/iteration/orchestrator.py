"""迭代闭环编排器."""

from __future__ import annotations

from .evaluator import UnifiedEvaluator
from .models import EvaluationDecision, ModelEvaluation
from .versioning import VersionStore
from ..dataset.feedback_loop import FeedbackLoop


class IterationOrchestrator:
    """协调评估、回流和版本切换."""

    def __init__(
        self,
        evaluator: UnifiedEvaluator,
        version_store: VersionStore,
        feedback_loop: FeedbackLoop,
    ) -> None:
        self.evaluator = evaluator
        self.version_store = version_store
        self.feedback_loop = feedback_loop

    def process_candidate(
        self,
        action_id: str,
        baseline: ModelEvaluation,
        candidate: ModelEvaluation,
    ) -> EvaluationDecision:
        """处理 candidate 的评估、版本切换与反馈回流."""
        decision = self.evaluator.compare(baseline, candidate)

        if decision.should_promote:
            self.version_store.promote_candidate(action_id, candidate.version_id)
        else:
            self.version_store.rollback_to(action_id, baseline.version_id)

        for feedback in self.evaluator.collect_feedback_records(candidate):
            self.feedback_loop.process_feedback(feedback)

        return decision
