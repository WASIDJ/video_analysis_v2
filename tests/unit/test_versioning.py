"""版本管理单元测试."""

from src.core.iteration.versioning import VersionStore


class TestVersionStore:
    """测试版本库."""

    def test_promote_candidate_sets_it_as_active_version(self, tmp_path):
        """发布 candidate 后应将其设为 active 版本."""
        store = VersionStore(storage_path=tmp_path / "versions.json")
        store.register_version(
            action_id="squat",
            version_id="baseline-v1",
            dataset_version="dataset-v1",
            config_version="config-v1",
            metrics={"f1": 0.80},
            status="baseline",
        )
        store.register_version(
            action_id="squat",
            version_id="candidate-v2",
            dataset_version="dataset-v2",
            config_version="config-v2",
            metrics={"f1": 0.88},
            status="candidate",
        )

        promoted = store.promote_candidate(action_id="squat", version_id="candidate-v2")

        assert promoted.version_id == "candidate-v2"
        assert store.get_active_version("squat").version_id == "candidate-v2"

    def test_rollback_restores_previous_baseline_reference(self, tmp_path):
        """回滚后应恢复指定版本为 active."""
        store = VersionStore(storage_path=tmp_path / "versions.json")
        store.register_version("squat", "baseline-v1", "dataset-v1", "config-v1", {"f1": 0.80}, status="baseline")
        store.register_version("squat", "candidate-v2", "dataset-v2", "config-v2", {"f1": 0.88}, status="candidate")
        store.promote_candidate("squat", "candidate-v2")

        restored = store.rollback_to("squat", "baseline-v1")

        assert restored.version_id == "baseline-v1"
        assert store.get_active_version("squat").version_id == "baseline-v1"
        assert store.list_history("squat")[-1]["event"] == "rollback"

