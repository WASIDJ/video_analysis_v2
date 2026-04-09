"""模型单元测试."""
import numpy as np
import pytest

from src.core.models.base import Keypoint, PoseFrame, PoseSequence


class TestKeypoint:
    """测试关键点数据类."""

    def test_create_keypoint(self):
        """测试创建关键点."""
        kp = Keypoint(name="nose", x=0.5, y=0.5, visibility=0.9)
        assert kp.name == "nose"
        assert kp.x == 0.5
        assert kp.y == 0.5
        assert kp.visibility == 0.9

    def test_is_visible(self):
        """测试可见性判断."""
        kp_visible = Keypoint(name="test", x=0.5, y=0.5, visibility=0.9, confidence=0.9)
        assert kp_visible.is_visible is True

        kp_invisible = Keypoint(name="test", x=0.5, y=0.5, visibility=0.1, confidence=0.9)
        assert kp_invisible.is_visible is False

    def test_to_array(self):
        """测试转换为数组."""
        kp = Keypoint(name="test", x=0.1, y=0.2, z=0.3)

        arr_2d = kp.to_array(use_3d=False)
        assert len(arr_2d) == 2
        assert arr_2d[0] == 0.1
        assert arr_2d[1] == 0.2

        arr_3d = kp.to_array(use_3d=True)
        assert len(arr_3d) == 3
        assert arr_3d[2] == 0.3


class TestPoseFrame:
    """测试姿态帧数据类."""

    def test_get_keypoint(self):
        """测试获取关键点."""
        keypoints = [
            Keypoint(name="nose", x=0.5, y=0.3),
            Keypoint(name="left_shoulder", x=0.3, y=0.5),
        ]
        frame = PoseFrame(frame_id=0, keypoints=keypoints)

        kp = frame.get_keypoint("nose")
        assert kp is not None
        assert kp.x == 0.5

        kp_none = frame.get_keypoint("nonexistent")
        assert kp_none is None

    def test_to_dict(self):
        """测试转换为字典."""
        keypoints = [
            Keypoint(name="nose", x=0.5, y=0.3, z=0.1, visibility=0.9),
        ]
        frame = PoseFrame(frame_id=0, keypoints=keypoints)

        data = frame.to_dict()
        assert "nose" in data
        assert data["nose"]["x"] == 0.5
        assert data["nose"]["z"] == 0.1


class TestPoseSequence:
    """测试姿态序列数据类."""

    def test_add_frame(self):
        """测试添加帧."""
        seq = PoseSequence()
        assert len(seq) == 0

        frame = PoseFrame(frame_id=0, keypoints=[])
        seq.add_frame(frame)
        assert len(seq) == 1

    def test_get_keypoint_trajectory(self):
        """测试获取关键点轨迹."""
        seq = PoseSequence()

        for i in range(3):
            frame = PoseFrame(
                frame_id=i,
                keypoints=[Keypoint(name="nose", x=0.1 * i, y=0.2 * i)],
            )
            seq.add_frame(frame)

        trajectory = seq.get_keypoint_trajectory("nose")
        assert len(trajectory) == 3
        assert trajectory[0][0] == 0.0
        assert trajectory[1][0] == 0.1
        assert trajectory[2][0] == 0.2

    def test_get_visible_keypoints(self):
        """测试获取可见关键点."""
        seq = PoseSequence()

        keypoints = [
            Keypoint(name="visible_kp", x=0.5, y=0.5, confidence=0.9),
            Keypoint(name="low_conf_kp", x=0.5, y=0.5, confidence=0.1),
        ]
        frame = PoseFrame(frame_id=0, keypoints=keypoints)
        seq.add_frame(frame)

        visible = seq.get_visible_keypoints(min_confidence=0.5)
        assert "visible_kp" in visible
        assert "low_conf_kp" not in visible
