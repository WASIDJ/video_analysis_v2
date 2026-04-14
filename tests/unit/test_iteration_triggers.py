"""迭代触发器单元测试."""

from datetime import datetime, timedelta

from src.core.iteration.models import TriggerSnapshot
from src.core.iteration.triggers import IterationTriggerEngine


class TestIterationTriggers:
    """测试自动触发器."""

    def test_triggers_when_new_sample_threshold_is_reached(self):
        """新增样本数达到阈值时应触发."""
        engine = IterationTriggerEngine(new_samples_threshold=20, low_confidence_threshold=10, retrain_after=timedelta(hours=24))
        snapshot = TriggerSnapshot(
            action_id="squat",
            new_samples=20,
            low_confidence_samples=0,
            last_training_at=datetime(2026, 4, 12, 0, 0, 0),
            now=datetime(2026, 4, 13, 0, 0, 0),
        )

        decision = engine.evaluate(snapshot)

        assert decision.triggered is True
        assert "new_samples" in decision.reasons

    def test_triggers_when_low_confidence_threshold_is_reached(self):
        """低置信样本数达到阈值时应触发."""
        engine = IterationTriggerEngine(new_samples_threshold=20, low_confidence_threshold=10, retrain_after=timedelta(hours=24))
        snapshot = TriggerSnapshot(
            action_id="squat",
            new_samples=5,
            low_confidence_samples=10,
            last_training_at=datetime(2026, 4, 13, 0, 0, 0),
            now=datetime(2026, 4, 13, 8, 0, 0),
        )

        decision = engine.evaluate(snapshot)

        assert decision.triggered is True
        assert "low_confidence_samples" in decision.reasons

    def test_triggers_when_model_is_stale_for_24_hours(self):
        """距离上次训练超过 24 小时时应触发."""
        engine = IterationTriggerEngine(new_samples_threshold=20, low_confidence_threshold=10, retrain_after=timedelta(hours=24))
        snapshot = TriggerSnapshot(
            action_id="squat",
            new_samples=0,
            low_confidence_samples=0,
            last_training_at=datetime(2026, 4, 12, 0, 0, 0),
            now=datetime(2026, 4, 13, 1, 0, 0),
        )

        decision = engine.evaluate(snapshot)

        assert decision.triggered is True
        assert "stale_model" in decision.reasons

    def test_does_not_retrigger_with_same_snapshot_token(self):
        """同一窗口内不应重复触发相同快照."""
        engine = IterationTriggerEngine(new_samples_threshold=20, low_confidence_threshold=10, retrain_after=timedelta(hours=24))
        snapshot = TriggerSnapshot(
            action_id="squat",
            new_samples=20,
            low_confidence_samples=0,
            last_training_at=datetime(2026, 4, 12, 0, 0, 0),
            now=datetime(2026, 4, 13, 0, 0, 0),
            snapshot_id="snapshot-001",
        )

        first = engine.evaluate(snapshot)
        second = engine.evaluate(snapshot)

        assert first.triggered is True
        assert second.triggered is False

