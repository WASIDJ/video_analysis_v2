"""iteration CLI 单元测试."""

import json
import subprocess


class TestIterationCli:
    """测试 iteration CLI."""

    def test_cli_can_enqueue_job_and_print_job_id(self, tmp_path):
        """CLI 应能从 JSON 文件读取请求并输出 job_id."""
        request_path = tmp_path / "request.json"
        request_path.write_text(
            json.dumps(
                {
                    "action_id": "squat",
                    "trigger_reason": "manual",
                    "baseline": {
                        "version_id": "baseline-v1",
                        "action_id": "squat",
                        "overall_score": 0.8,
                        "metric_scores": {"f1": 0.8},
                        "sample_results": [],
                        "dataset_version": "dataset-v1",
                        "config_version": "config-v1",
                    },
                    "candidate": {
                        "version_id": "candidate-v2",
                        "action_id": "squat",
                        "overall_score": 0.88,
                        "metric_scores": {"f1": 0.88},
                        "sample_results": [],
                        "dataset_version": "dataset-v1",
                        "config_version": "config-v2",
                    },
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                ".venv/bin/python",
                "manage_iteration.py",
                "enqueue",
                "--request-file",
                str(request_path),
            ],
            cwd="/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou",
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "job_id=" in result.stdout
