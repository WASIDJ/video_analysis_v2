"""几何计算工具单元测试."""
import numpy as np
import pytest

from src.utils.geometry import (
    calculate_angle_2d,
    calculate_angle_3d,
    calculate_distance,
    normalize_vector,
    calculate_vector_angle,
    calculate_vertical_angle,
    calculate_horizontal_angle,
)


class TestCalculateAngle2D:
    """测试2D角度计算."""

    def test_right_angle(self):
        """测试直角."""
        # 90度角
        angle = calculate_angle_2d((0, 0), (1, 0), (1, 1))
        assert abs(angle - 90.0) < 0.1

    def test_straight_angle(self):
        """测试平角."""
        angle = calculate_angle_2d((0, 0), (1, 0), (2, 0))
        assert abs(angle - 180.0) < 0.1

    def test_acute_angle(self):
        """测试锐角."""
        angle = calculate_angle_2d((0, 0), (1, 0), (2, 1))
        assert 90 < angle < 180

    def test_obtuse_angle(self):
        """测试钝角."""
        angle = calculate_angle_2d((0, 0), (1, 0), (0, 1))
        assert 0 < angle < 90

    def test_low_confidence(self):
        """测试低置信度返回nan."""
        angle = calculate_angle_2d(
            (0, 0), (1, 0), (1, 1),
            min_confidence=0.5,
            confidences=(0.3, 1.0, 1.0),
        )
        assert np.isnan(angle)


class TestCalculateAngle3D:
    """测试3D角度计算."""

    def test_right_angle_3d(self):
        """测试3D直角."""
        angle = calculate_angle_3d(
            (0, 0, 0), (1, 0, 0), (1, 1, 0)
        )
        assert abs(angle - 90.0) < 0.1

    def test_3d_angle(self):
        """测试3D角度."""
        angle = calculate_angle_3d(
            (0, 0, 0), (1, 0, 0), (0, 1, 1)
        )
        assert 0 < angle < 180


class TestCalculateDistance:
    """测试距离计算."""

    def test_2d_distance(self):
        """测试2D距离."""
        dist = calculate_distance((0, 0), (3, 4))
        assert abs(dist - 5.0) < 0.001

    def test_3d_distance(self):
        """测试3D距离."""
        dist = calculate_distance((0, 0, 0), (1, 1, 1))
        expected = np.sqrt(3)
        assert abs(dist - expected) < 0.001

    def test_zero_distance(self):
        """测试零距离."""
        dist = calculate_distance((1, 1), (1, 1))
        assert dist == 0.0


class TestNormalizeVector:
    """测试向量归一化."""

    def test_normalize(self):
        """测试归一化."""
        v = np.array([3, 4])
        normalized = normalize_vector(v)
        assert abs(np.linalg.norm(normalized) - 1.0) < 0.001

    def test_zero_vector(self):
        """测试零向量."""
        v = np.array([0, 0])
        normalized = normalize_vector(v)
        assert np.allclose(normalized, v)


class TestCalculateVectorAngle:
    """测试向量角度计算."""

    def test_perpendicular(self):
        """测试垂直向量."""
        v1 = np.array([1, 0])
        v2 = np.array([0, 1])
        angle = calculate_vector_angle(v1, v2)
        assert abs(angle - 90.0) < 0.1

    def test_parallel(self):
        """测试平行向量."""
        v1 = np.array([1, 0])
        v2 = np.array([2, 0])
        angle = calculate_vector_angle(v1, v2)
        assert abs(angle - 0.0) < 0.1


class TestVerticalAngle:
    """测试垂直角度计算."""

    def test_vertical_line(self):
        """测试垂直线."""
        angle = calculate_vertical_angle((0, 0), (0, 1))
        assert abs(angle - 0.0) < 0.1

    def test_horizontal_line(self):
        """测试水平线."""
        angle = calculate_vertical_angle((0, 0), (1, 0))
        assert abs(angle - 90.0) < 0.1

    def test_45_degree(self):
        """测试45度线."""
        angle = calculate_vertical_angle((0, 0), (1, 1))
        assert abs(angle - 45.0) < 0.1
