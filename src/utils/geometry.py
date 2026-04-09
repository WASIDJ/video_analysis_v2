"""几何计算工具函数."""
import numpy as np
from typing import Tuple


def calculate_angle_2d(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    min_confidence: float = 0.0,
    confidences: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> float:
    """计算三点形成的角度（2D）.

    Args:
        p1: 第一个点 (x, y)，通常是起点
        p2: 第二个点 (x, y)，顶角
        p3: 第三个点 (x, y)，通常是终点
        min_confidence: 最小置信度阈值
        confidences: 三个点的置信度

    Returns:
        角度（度），范围[0, 180]
    """
    # 检查置信度
    if any(c < min_confidence for c in confidences):
        return np.nan

    # 转换为向量
    a = np.array([p1[0] - p2[0], p1[1] - p2[1]])
    b = np.array([p3[0] - p2[0], p3[1] - p2[1]])

    # 计算角度
    cos_angle = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = np.degrees(np.arccos(cos_angle))

    return float(angle)


def calculate_angle_3d(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    p3: Tuple[float, float, float],
    min_confidence: float = 0.0,
    confidences: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> float:
    """计算三点形成的角度（3D）.

    Args:
        p1: 第一个点 (x, y, z)
        p2: 第二个点 (x, y, z)，顶角
        p3: 第三个点 (x, y, z)
        min_confidence: 最小置信度阈值
        confidences: 三个点的置信度

    Returns:
        角度（度），范围[0, 180]
    """
    if any(c < min_confidence for c in confidences):
        return np.nan

    a = np.array([p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2]])
    b = np.array([p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2]])

    cos_angle = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = np.degrees(np.arccos(cos_angle))

    return float(angle)


def calculate_distance(
    p1: Tuple[float, ...],
    p2: Tuple[float, ...],
    min_confidence: float = 0.0,
    confidences: Tuple[float, float] = (1.0, 1.0),
) -> float:
    """计算两点间距离.

    Args:
        p1: 第一个点 (x, y) 或 (x, y, z)
        p2: 第二个点 (x, y) 或 (x, y, z)
        min_confidence: 最小置信度阈值
        confidences: 两个点的置信度

    Returns:
        欧氏距离
    """
    if any(c < min_confidence for c in confidences):
        return np.nan

    a = np.array(p1)
    b = np.array(p2)
    return float(np.linalg.norm(a - b))


def normalize_vector(v: np.ndarray) -> np.ndarray:
    """归一化向量.

    Args:
        v: 输入向量

    Returns:
        单位向量
    """
    norm = np.linalg.norm(v)
    if norm < 1e-6:
        return v
    return v / norm


def calculate_vector_angle(
    v1: np.ndarray,
    v2: np.ndarray,
) -> float:
    """计算两个向量间的夹角.

    Args:
        v1: 向量1
        v2: 向量2

    Returns:
        角度（度），范围[0, 180]
    """
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def project_to_plane(
    point: np.ndarray,
    plane_normal: np.ndarray,
    plane_point: np.ndarray = np.array([0, 0, 0]),
) -> np.ndarray:
    """将点投影到平面.

    Args:
        point: 待投影的点
        plane_normal: 平面法向量
        plane_point: 平面上的一点

    Returns:
        投影后的点
    """
    normal = normalize_vector(plane_normal)
    vec = point - plane_point
    distance = np.dot(vec, normal)
    return point - distance * normal


def calculate_vertical_angle(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> float:
    """计算线段与垂直方向的夹角.

    Args:
        p1: 点1 (x, y)
        p2: 点2 (x, y)

    Returns:
        与垂直方向的夹角（度），范围[0, 90]
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dy) < 1e-6:
        return 90.0

    # 计算与垂直方向的夹角
    angle = np.degrees(np.arctan(abs(dx) / abs(dy)))
    return float(angle)


def calculate_horizontal_angle(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> float:
    """计算线段与水平方向的夹角.

    Args:
        p1: 点1 (x, y)
        p2: 点2 (x, y)

    Returns:
        与水平方向的夹角（度），范围[-90, 90]
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dx) < 1e-6:
        return 90.0 if dy > 0 else -90.0

    return float(np.degrees(np.arctan(dy / dx)))
