"""自动迭代触发器."""

from __future__ import annotations

from datetime import timedelta

from .models import TriggerDecision, TriggerSnapshot


class IterationTriggerEngine:
    """根据数据与时间窗口决定是否触发迭代."""

    def __init__(
        self,
        new_samples_threshold: int = 20,
        low_confidence_threshold: int = 10,
        retrain_after: timedelta = timedelta(hours=24),
    ) -> None:
        self.new_samples_threshold = new_samples_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.retrain_after = retrain_after
        self._seen_snapshot_ids: set[str] = set()

    def evaluate(self, snapshot: TriggerSnapshot) -> TriggerDecision:
        """评估是否需要触发迭代."""
        snapshot_token = snapshot.snapshot_id or self._build_snapshot_token(snapshot)
        if snapshot_token in self._seen_snapshot_ids:
            return TriggerDecision(triggered=False, reasons=[])

        reasons: list[str] = []
        if snapshot.new_samples >= self.new_samples_threshold:
            reasons.append("new_samples")
        if snapshot.low_confidence_samples >= self.low_confidence_threshold:
            reasons.append("low_confidence_samples")
        if snapshot.last_training_at is None or snapshot.now - snapshot.last_training_at >= self.retrain_after:
            reasons.append("stale_model")

        triggered = len(reasons) > 0
        if triggered:
            self._seen_snapshot_ids.add(snapshot_token)
        return TriggerDecision(triggered=triggered, reasons=reasons)

    @staticmethod
    def _build_snapshot_token(snapshot: TriggerSnapshot) -> str:
        """从快照构造去重 token."""
        return ":".join(
            [
                snapshot.action_id,
                str(snapshot.new_samples),
                str(snapshot.low_confidence_samples),
                snapshot.last_training_at.isoformat() if snapshot.last_training_at else "none",
                snapshot.now.isoformat(),
            ]
        )
