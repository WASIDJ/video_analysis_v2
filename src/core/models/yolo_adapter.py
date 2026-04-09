"""YOLOv8-pose 适配器."""
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from ultralytics import YOLO

from .base import BasePoseEstimator, Keypoint, PoseFrame, PoseSequence


class YOLOPoseAdapter(BasePoseEstimator):
    """YOLOv8-pose 适配器.

    提供与BlazePose相同的接口，但底层使用YOLOv8-pose模型.
    输出17个COCO格式关键点.

    关键点索引 (COCO格式):
        0: nose
        1-2: eyes
        3-4: ears
        5-6: shoulders
        7-8: elbows
        9-10: wrists
        11-12: hips
        13-14: knees
        15-16: ankles
    """

    # 17个关键点名称
    KEYPOINT_NAMES = [
        "nose",
        "left_eye", "right_eye",
        "left_ear", "right_ear",
        "left_shoulder", "right_shoulder",
        "left_elbow", "right_elbow",
        "left_wrist", "right_wrist",
        "left_hip", "right_hip",
        "left_knee", "right_knee",
        "left_ankle", "right_ankle",
    ]

    # 骨骼连接
    KEYPOINT_CONNECTIONS = [
        # 面部
        (0, 1), (0, 2), (1, 3), (2, 4),
        # 躯干
        (5, 6), (5, 11), (6, 12), (11, 12),
        # 左臂
        (5, 7), (7, 9),
        # 右臂
        (6, 8), (8, 10),
        # 左腿
        (11, 13), (13, 15),
        # 右腿
        (12, 14), (14, 16),
    ]

    # YOLO索引到标准名称的映射
    INDEX_TO_NAME = {i: name for i, name in enumerate(KEYPOINT_NAMES)}

    def __init__(
        self,
        model_path: str = "yolov8m-pose.pt",
        conf: float = 0.5,
        iou: float = 0.5,
        max_det: int = 1,
        device: Optional[str] = None,
    ):
        """
        Args:
            model_path: YOLO模型路径或名称
            conf: 置信度阈值
            iou: NMS IoU阈值
            max_det: 最大检测人数
            device: 运行设备 (cuda/cpu/mps)
        """
        super().__init__(
            model_path=model_path,
            conf=conf,
            iou=iou,
            max_det=max_det,
            device=device,
        )

        self._model_path = model_path
        self._device = device

    @property
    def keypoint_names(self) -> List[str]:
        return self.KEYPOINT_NAMES

    @property
    def keypoint_connections(self) -> List[Tuple[int, int]]:
        return self.KEYPOINT_CONNECTIONS

    @property
    def model_name(self) -> str:
        return f"YOLOv8-pose_{Path(self._model_path).stem}"

    def initialize(self) -> None:
        """加载YOLO模型."""
        if self._is_initialized:
            return

        self._model = YOLO(self._model_path)

        # 设置设备
        device = self._config.get("device")
        if device:
            self._model.to(device)

        self._is_initialized = True

    def process_frame(self, frame: np.ndarray) -> Optional[PoseFrame]:
        """处理单帧.

        Args:
            frame: BGR格式的numpy数组

        Returns:
            PoseFrame或None
        """
        if not self._is_initialized:
            self.initialize()

        # YOLO推理
        results = self._model(
            frame,
            conf=self._config.get("conf", 0.5),
            iou=self._config.get("iou", 0.5),
            max_det=self._config.get("max_det", 1),
            verbose=False,
        )

        # 提取关键点
        for result in results:
            if result.keypoints is None:
                continue

            keypoints_data = result.keypoints

            # 处理多人情况，选择置信度最高的人
            if len(keypoints_data) == 0:
                continue

            # 获取关键点坐标和置信度
            if hasattr(keypoints_data, 'xy'):
                # 新版本ultralytics
                kpts = keypoints_data.xy[0].cpu().numpy() if keypoints_data.xy else None
                confs = keypoints_data.conf[0].cpu().numpy() if keypoints_data.conf else None
            else:
                # 兼容旧版本
                kpts = keypoints_data.xyn[0].cpu().numpy() if keypoints_data.xyn else None
                confs = keypoints_data.conf[0].cpu().numpy() if keypoints_data.conf else None

            if kpts is None or len(kpts) == 0:
                continue

            # 归一化坐标
            h, w = frame.shape[:2]

            keypoints = []
            for idx in range(min(len(kpts), len(self.KEYPOINT_NAMES))):
                if len(kpts[idx]) >= 2:
                    x = float(kpts[idx][0])
                    y = float(kpts[idx][1])

                    # 如果是像素坐标，转换为归一化
                    if x > 1.0 or y > 1.0:
                        x = x / w
                        y = y / h

                    conf = float(confs[idx]) if confs is not None and idx < len(confs) else 1.0

                    kp = Keypoint(
                        name=self.KEYPOINT_NAMES[idx],
                        x=x,
                        y=y,
                        z=0.0,
                        visibility=conf,
                        confidence=conf,
                    )
                    keypoints.append(kp)

            return PoseFrame(frame_id=0, keypoints=keypoints, timestamp=0.0)

        return None

    def process_video(
        self,
        video_path: str,
        target_fps: Optional[float] = None,
        progress_callback: Optional[callable] = None,
        **kwargs
    ) -> PoseSequence:
        """处理视频.

        使用YOLO的track模式进行视频跟踪.
        """
        from ...utils.video import VideoFrameIterator

        if not self._is_initialized:
            self.initialize()

        sequence = PoseSequence()
        sequence.metadata["model"] = self.model_name
        sequence.metadata["video_path"] = video_path

        # 使用YOLO内置视频处理
        results = self._model.track(
            source=video_path,
            conf=self._config.get("conf", 0.5),
            iou=self._config.get("iou", 0.5),
            max_det=self._config.get("max_det", 1),
            stream=True,
            verbose=False,
            **kwargs
        )

        frame_id = 0
        for result in results:
            if result.keypoints is None or len(result.keypoints) == 0:
                frame_id += 1
                continue

            # 提取关键点
            keypoints_data = result.keypoints

            if hasattr(keypoints_data, 'xy'):
                kpts = keypoints_data.xy[0].cpu().numpy() if keypoints_data.xy else None
                confs = keypoints_data.conf[0].cpu().numpy() if keypoints_data.conf else None
            else:
                kpts = keypoints_data.xyn[0].cpu().numpy() if keypoints_data.xyn else None
                confs = keypoints_data.conf[0].cpu().numpy() if keypoints_data.conf else None

            if kpts is None or len(kpts) == 0:
                frame_id += 1
                continue

            h, w = result.orig_shape

            keypoints = []
            for idx in range(min(len(kpts), len(self.KEYPOINT_NAMES))):
                if len(kpts[idx]) >= 2:
                    x = float(kpts[idx][0])
                    y = float(kpts[idx][1])

                    # 归一化
                    if x > 1.0:
                        x = x / w
                    if y > 1.0:
                        y = y / h

                    conf = float(confs[idx]) if confs is not None and idx < len(confs) else 1.0

                    kp = Keypoint(
                        name=self.KEYPOINT_NAMES[idx],
                        x=x,
                        y=y,
                        z=0.0,
                        visibility=conf,
                        confidence=conf,
                    )
                    keypoints.append(kp)

            pose_frame = PoseFrame(
                frame_id=frame_id,
                keypoints=keypoints,
                timestamp=frame_id / 30.0,  # 假设30fps
            )
            sequence.add_frame(pose_frame)

            if progress_callback:
                progress_callback(frame_id, None)

            frame_id += 1

        return sequence


class PoseConverter:
    """姿态数据转换器.

    用于在BlazePose(33点)和YOLO(17点)之间转换.
    """

    # BlazePose索引 -> YOLO索引 映射
    BLAZEPOSE_TO_YOLO = {
        0: 0,    # nose
        2: 1,    # left_eye -> left_eye (approximate)
        5: 2,    # right_eye -> right_eye (approximate)
        7: 3,    # left_ear -> left_ear (approximate)
        8: 4,    # right_ear -> right_ear (approximate)
        11: 5,   # left_shoulder
        12: 6,   # right_shoulder
        13: 7,   # left_elbow
        14: 8,   # right_elbow
        15: 9,   # left_wrist
        16: 10,  # right_wrist
        23: 11,  # left_hip
        24: 12,  # right_hip
        25: 13,  # left_knee
        26: 14,  # right_knee
        27: 15,  # left_ankle
        28: 16,  # right_ankle
    }

    # YOLO索引 -> BlazePose索引 映射
    YOLO_TO_BLAZEPOSE = {v: k for k, v in BLAZEPOSE_TO_YOLO.items()}

    @classmethod
    def blaze_to_yolo(cls, pose_frame: PoseFrame) -> PoseFrame:
        """将BlazePose格式转换为YOLO格式.

        Args:
            pose_frame: BlazePose格式的姿态帧

        Returns:
            YOLO格式的姿态帧
        """
        keypoints = []

        for yolo_idx, yolo_name in enumerate(YOLOPoseAdapter.KEYPOINT_NAMES):
            blaze_idx = cls.YOLO_TO_BLAZEPOSE.get(yolo_idx)

            if blaze_idx is not None and blaze_idx < len(pose_frame.keypoints):
                kp = pose_frame.keypoints[blaze_idx]
                kp.name = yolo_name
                keypoints.append(kp)
            else:
                # 创建空的keypoint
                keypoints.append(Keypoint(
                    name=yolo_name,
                    x=0.0,
                    y=0.0,
                    visibility=0.0,
                    confidence=0.0,
                ))

        return PoseFrame(
            frame_id=pose_frame.frame_id,
            keypoints=keypoints,
            timestamp=pose_frame.timestamp,
        )

    @classmethod
    def yolo_to_blaze(cls, pose_frame: PoseFrame) -> PoseFrame:
        """将YOLO格式转换为BlazePose格式.

        Args:
            pose_frame: YOLO格式的姿态帧

        Returns:
            BlazePose格式的姿态帧
        """
        keypoints = []

        for blaze_idx, blaze_name in enumerate(BlazePoseEstimator.KEYPOINT_NAMES):
            yolo_idx = cls.BLAZEPOSE_TO_YOLO.get(blaze_idx)

            if yolo_idx is not None and yolo_idx < len(pose_frame.keypoints):
                kp = pose_frame.keypoints[yolo_idx]
                kp.name = blaze_name
                keypoints.append(kp)
            else:
                # BlazePose特有的点（如手指、脚趾）设为不可见
                keypoints.append(Keypoint(
                    name=blaze_name,
                    x=0.0,
                    y=0.0,
                    visibility=0.0,
                    confidence=0.0,
                ))

        return PoseFrame(
            frame_id=pose_frame.frame_id,
            keypoints=keypoints,
            timestamp=pose_frame.timestamp,
        )
