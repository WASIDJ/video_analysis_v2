"""深蹲动作阶段检测器."""
from enum import Enum
from typing import Dict, List, Optional, Any

import numpy as np

from .base import BasePhaseDetector, PhaseDetectionResult
from src.core.models.base import PoseSequence, PoseFrame
from src.utils.geometry import calculate_angle_2d


class SquatPhase(Enum):
    """深蹲动作阶段."""
    STANDING = "standing"           # 站立起始
    DESCENT = "descent"             # 下蹲过程
    BOTTOM = "bottom"               # 最低点（离心结束）
    ASCENT = "ascent"               # 站起过程
    COMPLETION = "completion"       # 动作完成


class SquatPhaseDetector(BasePhaseDetector):
    """深蹲阶段检测器.

    基于膝关节角度变化检测深蹲的各个阶段:
    - 站立: 膝关节角度 > 160°
    - 下蹲: 角度从 >160° 减小
    - 最低点: 角度最小值位置
    - 站起: 角度从最小值增加
    """

    # 阶段判断阈值
    STANDING_THRESHOLD = 160.0      # 站立时膝关节角度阈值
    DEPTH_THRESHOLD = 90.0          # 深蹲深度阈值（小于此值为有效深蹲）

    def __init__(self, min_phase_duration: float = 0.2):
        """
        Args:
            min_phase_duration: 最小阶段持续时间（秒）
        """
        super().__init__(min_phase_duration)

    def _calculate_knee_angle_sequence(self, pose_sequence: PoseSequence) -> np.ndarray:
        """计算膝关节角度序列."""
        angles = []

        for frame in pose_sequence.frames:
            # 获取左膝关节关键点（使用左侧作为代表）
            hip = self._get_keypoint(frame, "left_hip")
            knee = self._get_keypoint(frame, "left_knee")
            ankle = self._get_keypoint(frame, "left_ankle")

            if hip and knee and ankle:
                angle = calculate_angle_2d(
                    (hip.x, hip.y),
                    (knee.x, knee.y),
                    (ankle.x, ankle.y),
                    min_confidence=0.3,
                    confidences=(hip.confidence, knee.confidence, ankle.confidence),
                )
                angles.append(angle if not np.isnan(angle) else 180.0)
            else:
                # 尝试右侧
                hip = self._get_keypoint(frame, "right_hip")
                knee = self._get_keypoint(frame, "right_knee")
                ankle = self._get_keypoint(frame, "right_ankle")

                if hip and knee and ankle:
                    angle = calculate_angle_2d(
                        (hip.x, hip.y),
                        (knee.x, knee.y),
                        (ankle.x, ankle.y),
                        min_confidence=0.3,
                        confidences=(hip.confidence, knee.confidence, ankle.confidence),
                    )
                    angles.append(angle if not np.isnan(angle) else 180.0)
                else:
                    angles.append(180.0)  # 默认站立角度

        return np.array(angles)

    def detect_phases(self, pose_sequence: PoseSequence) -> List[PhaseDetectionResult]:
        """检测深蹲阶段."""
        if len(pose_sequence) < 10:
            return []

        # 计算膝关节角度序列
        knee_angles = self._calculate_knee_angle_sequence(pose_sequence)

        # 平滑处理
        smoothed_angles = self.smooth_sequence(knee_angles, window=3)

        phases = []

        # 寻找最低点（深蹲最深处）
        bottom_idx = int(np.argmin(smoothed_angles))
        bottom_angle = smoothed_angles[bottom_idx]

        # 确定起始点（站立）
        start_idx = 0
        for i in range(bottom_idx):
            if smoothed_angles[i] > self.STANDING_THRESHOLD:
                start_idx = i
                break

        # 确定结束点（回到站立）
        end_idx = len(smoothed_angles) - 1
        for i in range(bottom_idx, len(smoothed_angles)):
            if smoothed_angles[i] > self.STANDING_THRESHOLD:
                end_idx = i
                break

        # 创建阶段结果

        # 1. 站立起始阶段
        if start_idx > 0:
            phases.append(PhaseDetectionResult(
                phase=SquatPhase.STANDING,
                start_frame=0,
                end_frame=start_idx,
                confidence=0.8,
                metadata={"avg_knee_angle": float(np.mean(smoothed_angles[:start_idx]))}
            ))

        # 2. 下蹲阶段
        phases.append(PhaseDetectionResult(
            phase=SquatPhase.DESCENT,
            start_frame=start_idx,
            end_frame=bottom_idx,
            confidence=0.9,
            metadata={
                "start_angle": float(smoothed_angles[start_idx]),
                "end_angle": float(bottom_angle),
            }
        ))

        # 3. 最低点阶段
        bottom_range = 5  # 最低点前后的帧数范围
        bottom_start = max(0, bottom_idx - bottom_range)
        bottom_end = min(len(smoothed_angles), bottom_idx + bottom_range)

        phases.append(PhaseDetectionResult(
            phase=SquatPhase.BOTTOM,
            start_frame=bottom_start,
            end_frame=bottom_end,
            confidence=0.95,
            metadata={
                "min_angle": float(bottom_angle),
                "is_valid_depth": bottom_angle < self.DEPTH_THRESHOLD,
            }
        ))

        # 4. 站起阶段
        phases.append(PhaseDetectionResult(
            phase=SquatPhase.ASCENT,
            start_frame=bottom_idx,
            end_frame=end_idx,
            confidence=0.9,
            metadata={
                "start_angle": float(bottom_angle),
                "end_angle": float(smoothed_angles[end_idx]),
            }
        ))

        # 5. 完成阶段
        if end_idx < len(smoothed_angles) - 1:
            phases.append(PhaseDetectionResult(
                phase=SquatPhase.COMPLETION,
                start_frame=end_idx,
                end_frame=len(smoothed_angles) - 1,
                confidence=0.8,
                metadata={"avg_knee_angle": float(np.mean(smoothed_angles[end_idx:]))}
            ))

        return phases

    def get_key_frame_for_metric(
        self,
        pose_sequence: PoseSequence,
        metric_id: str
    ) -> Optional[int]:
        """获取用于评估检测项的关键帧.

        根据检测项类型返回最适合评估的帧:
        - 深蹲深度类: 返回最低点帧
        - 膝外翻类: 返回下蹲过程中的最大值帧
        - 躯干前倾类: 返回最低点帧
        """
        phases = self.detect_phases(pose_sequence)

        if not phases:
            return None

        # 找到最低点阶段
        bottom_phase = None
        for phase in phases:
            if phase.phase == SquatPhase.BOTTOM:
                bottom_phase = phase
                break

        if not bottom_phase:
            return None

        # 根据检测项类型选择关键帧
        depth_metrics = ["knee_flexion", "hip_flexion", "trunk_lean", "lumbar_curvature"]
        valgus_metrics = ["knee_valgus"]

        if metric_id in depth_metrics:
            # 深度相关检测项：在最低点评估
            return (bottom_phase.start_frame + bottom_phase.end_frame) // 2

        elif metric_id in valgus_metrics:
            # 膝外翻：在下蹲阶段评估最大值
            descent_phase = None
            for phase in phases:
                if phase.phase == SquatPhase.DESCENT:
                    descent_phase = phase
                    break
            if descent_phase:
                # 返回下蹲阶段中间位置
                return (descent_phase.start_frame + descent_phase.end_frame) // 2

        # 默认返回最低点
        return (bottom_phase.start_frame + bottom_phase.end_frame) // 2

    def get_key_frame_for_phase(
        self,
        pose_sequence: PoseSequence,
        phase_id: str,
    ) -> Optional[int]:
        """获取指定阶段的关键帧."""
        phases = self.detect_phases(pose_sequence)

        for phase in phases:
            # 兼容 Enum 和字符串
            if hasattr(phase.phase, "value") and phase.phase.value == phase_id:
                return (phase.start_frame + phase.end_frame) // 2
            elif hasattr(phase, "phase_id") and phase.phase_id == phase_id:
                return (phase.start_frame + phase.end_frame) // 2
            elif str(phase.phase) == phase_id or phase.phase == phase_id:
                return (phase.start_frame + phase.end_frame) // 2

        return None

    def _get_keypoint(self, frame: PoseFrame, name: str):
        """获取关键点."""
        kp = frame.get_keypoint(name)
        if kp:
            return kp

        # 尝试另一侧
        if name.startswith("left_"):
            return frame.get_keypoint(name.replace("left_", "right_"))
        elif name.startswith("right_"):
            return frame.get_keypoint(name.replace("right_", "left_"))

        return None


def create_phase_detector(action_name: str) -> Optional[BasePhaseDetector]:
    """创建动作阶段检测器工厂函数."""
    if action_name.lower() in ["squat", "深蹲"]:
        return SquatPhaseDetector()
    # 可以扩展其他动作
    return None
