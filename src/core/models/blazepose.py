"""MediaPipe BlazePose实现 (Tasks API版本).

使用 MediaPipe Tasks API 替代已弃用的 Solutions API.
支持33个关键点（包括面部、手部和脚部细节）.
"""
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from .base import BasePoseEstimator, Keypoint, PoseFrame, PoseSequence


class BlazePoseEstimator(BasePoseEstimator):
    """MediaPipe BlazePose姿态估计器 (Tasks API).

    提供33个关键点（包括面部、手部和脚部细节）.
    支持2D和3D坐标输出.

    关键点索引:
        0: nose
        1-10: 眼部和脸部
        11-12: 肩膀
        13-14: 肘部
        15-16: 手腕
        17-22: 手指
        23-24: 臀部
        25-26: 膝盖
        27-28: 脚踝
        29-32: 脚部和脚跟
    """

    # 33个关键点名称
    KEYPOINT_NAMES = [
        # 面部 (0-10)
        "nose",
        "left_eye_inner",
        "left_eye",
        "left_eye_outer",
        "right_eye_inner",
        "right_eye",
        "right_eye_outer",
        "left_ear",
        "right_ear",
        "mouth_left",
        "mouth_right",
        # 躯干 (11-24)
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
        "left_pinky",
        "right_pinky",
        "left_index",
        "right_index",
        "left_thumb",
        "right_thumb",
        "left_hip",
        "right_hip",
        # 腿部 (25-32)
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
        "left_heel",
        "right_heel",
        "left_foot_index",
        "right_foot_index",
    ]

    # 骨骼连接关系（用于可视化）
    KEYPOINT_CONNECTIONS = [
        # 面部
        (0, 1), (1, 2), (2, 3), (3, 7),
        (0, 4), (4, 5), (5, 6), (6, 8),
        (9, 10),
        # 躯干
        (11, 12), (11, 23), (12, 24), (23, 24),
        # 左臂
        (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
        # 右臂
        (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),
        # 左腿
        (23, 25), (25, 27), (27, 29), (29, 31),
        # 右腿
        (24, 26), (26, 28), (28, 30), (30, 32),
        # 头颈连接
        (0, 11), (0, 12),
    ]

    # 模型下载URL (blaze_pose_heavy)
    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"

    def __init__(
        self,
        model_path: Optional[str] = None,
        num_poses: int = 1,
        min_pose_detection_confidence: float = 0.5,
        min_pose_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        """
        Args:
            model_path: 模型文件路径（.task文件），None则自动下载
            num_poses: 最大检测人数
            min_pose_detection_confidence: 最小检测置信度
            min_pose_presence_confidence: 最小存在置信度
            min_tracking_confidence: 最小跟踪置信度
        """
        super().__init__(
            model_path=model_path,
            num_poses=num_poses,
            min_pose_detection_confidence=min_pose_detection_confidence,
            min_pose_presence_confidence=min_pose_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        self._landmarker = None
        self._PoseLandmarker = None
        self._PoseLandmarkerOptions = None
        self._VisionRunningMode = None

    @property
    def keypoint_names(self) -> List[str]:
        return self.KEYPOINT_NAMES

    @property
    def keypoint_connections(self) -> List[Tuple[int, int]]:
        return self.KEYPOINT_CONNECTIONS

    @property
    def model_name(self) -> str:
        return "BlazePose_TasksAPI_heavy"

    def _ensure_model(self) -> str:
        """确保模型文件存在，如果不存在则下载."""
        model_path = self._config.get("model_path")

        if model_path and Path(model_path).exists():
            return model_path

        # 使用默认路径
        default_path = Path.home() / ".mediapipe" / "pose_landmarker_heavy.task"

        if default_path.exists():
            return str(default_path)

        # 下载模型
        print(f"下载 BlazePose 模型到 {default_path}...")
        default_path.parent.mkdir(parents=True, exist_ok=True)

        import urllib.request
        import ssl
        import shutil

        # 创建SSL上下文（处理macOS证书问题）
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            # 使用urlopen + shutil.copyfileobj来处理SSL上下文
            request = urllib.request.Request(self.MODEL_URL)
            with urllib.request.urlopen(request, context=ssl_context, timeout=300) as response:
                with open(default_path, 'wb') as f:
                    shutil.copyfileobj(response, f)
            print("模型下载完成")
            return str(default_path)
        except Exception as e:
            print(f"模型下载失败: {e}")
            # 尝试使用lite版本
            lite_url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
            lite_path = Path.home() / ".mediapipe" / "pose_landmarker_lite.task"

            try:
                print("尝试下载轻量级模型...")
                request = urllib.request.Request(lite_url)
                with urllib.request.urlopen(request, context=ssl_context, timeout=300) as response:
                    with open(lite_path, 'wb') as f:
                        shutil.copyfileobj(response, f)
                print("轻量级模型下载完成")
                return str(lite_path)
            except Exception as e2:
                raise RuntimeError(f"无法下载模型: {e}, {e2}")

    def initialize(self) -> None:
        """初始化BlazePose模型 (Tasks API)."""
        if self._is_initialized:
            return

        try:
            from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions
            try:
                from mediapipe.tasks.python.core import BaseOptions
            except ImportError:
                # 新版MediaPipe使用不同的导入路径
                from mediapipe.tasks.python.core.base_options import BaseOptions
            try:
                from mediapipe.tasks.python.vision.core import VisionRunningMode
            except ImportError:
                # 0.10.33+ 版本使用 VisionTaskRunningMode
                from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode as VisionRunningMode

            self._PoseLandmarker = PoseLandmarker
            self._PoseLandmarkerOptions = PoseLandmarkerOptions
            self._VisionRunningMode = VisionRunningMode

            # 确保模型存在
            model_path = self._ensure_model()

            # 创建选项
            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionRunningMode.VIDEO,
                num_poses=self._config.get("num_poses", 1),
                min_pose_detection_confidence=self._config.get("min_pose_detection_confidence", 0.5),
                min_pose_presence_confidence=self._config.get("min_pose_presence_confidence", 0.5),
                min_tracking_confidence=self._config.get("min_tracking_confidence", 0.5),
            )

            # 创建landmarker
            self._landmarker = PoseLandmarker.create_from_options(options)
            self._is_initialized = True

        except ImportError as e:
            raise ImportError(
                f"MediaPipe导入失败: {e}. "
                "请安装: pip install mediapipe>=0.10.0"
            )

    def process_frame(self, frame: np.ndarray) -> Optional[PoseFrame]:
        """处理单帧.

        Args:
            frame: BGR格式的numpy数组

        Returns:
            PoseFrame或None
        """
        if not self._is_initialized:
            self.initialize()

        try:
            from mediapipe.tasks.python.vision import PoseLandmarker
            from mediapipe import Image, ImageFormat

            # 转换为RGB
            rgb_frame = frame[:, :, ::-1]  # BGR to RGB
            h, w = frame.shape[:2]

            # 创建MediaPipe Image
            mp_image = Image(image_format=ImageFormat.SRGB, data=rgb_frame)

            # 推理 (VIDEO模式需要传入时间戳)
            timestamp_ms = 0  # 单帧处理使用0
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

            if not result.pose_landmarks:
                return None

            # 提取第一个人的关键点
            landmarks = result.pose_landmarks[0]

            # 转换为Keypoint列表
            keypoints = []
            for idx, landmark in enumerate(landmarks):
                if idx >= len(self.KEYPOINT_NAMES):
                    break

                kp = Keypoint(
                    name=self.KEYPOINT_NAMES[idx],
                    x=landmark.x,
                    y=landmark.y,
                    z=landmark.z,
                    visibility=landmark.visibility if hasattr(landmark, 'visibility') else 1.0,
                    confidence=landmark.presence if hasattr(landmark, 'presence') else 1.0,
                )
                keypoints.append(kp)

            return PoseFrame(
                frame_id=0,
                keypoints=keypoints,
                timestamp=0.0,
            )

        except Exception as e:
            print(f"处理帧时出错: {e}")
            return None

    def process_video(
        self,
        video_path: str,
        target_fps: Optional[float] = None,
        progress_callback: Optional[callable] = None,
        **kwargs
    ) -> PoseSequence:
        """处理视频.

        Args:
            video_path: 视频路径
            target_fps: 目标帧率
            progress_callback: 进度回调函数(frame_id, total_frames)

        Returns:
            PoseSequence
        """
        from ...utils.video import VideoFrameIterator
        from mediapipe import Image, ImageFormat

        # 重新初始化 landmarker 以重置内部的时间戳状态
        if self._is_initialized and self._landmarker:
            self._landmarker.close()
            self._is_initialized = False
            
        if not self._is_initialized:
            self.initialize()

        sequence = PoseSequence()
        sequence.metadata["model"] = self.model_name
        sequence.metadata["video_path"] = video_path

        with VideoFrameIterator(
            video_path,
            target_fps=target_fps,
            auto_rotate=True,
        ) as iterator:

            sequence.metadata["video_info"] = iterator.get_video_info()

            fps = target_fps or iterator.original_fps or 30.0
            frame_time_ms = 1000.0 / fps

            for frame_id, frame in iterator:
                # 转换为RGB
                rgb_frame = frame[:, :, ::-1]

                # 创建MediaPipe Image
                mp_image = Image(image_format=ImageFormat.SRGB, data=rgb_frame)

                # 计算时间戳
                timestamp_ms = int(frame_id * frame_time_ms)

                # 推理
                result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

                if result.pose_landmarks:
                    landmarks = result.pose_landmarks[0]

                    # 提取关键点
                    keypoints = []
                    for idx, landmark in enumerate(landmarks):
                        if idx >= len(self.KEYPOINT_NAMES):
                            break

                        kp = Keypoint(
                            name=self.KEYPOINT_NAMES[idx],
                            x=landmark.x,
                            y=landmark.y,
                            z=landmark.z,
                            visibility=landmark.visibility if hasattr(landmark, 'visibility') else 1.0,
                            confidence=landmark.presence if hasattr(landmark, 'presence') else 1.0,
                        )
                        keypoints.append(kp)

                    pose_frame = PoseFrame(
                        frame_id=frame_id,
                        keypoints=keypoints,
                        timestamp=frame_id / fps,
                    )
                    sequence.add_frame(pose_frame)

                if progress_callback:
                    progress_callback(frame_id, len(iterator))

        return sequence

    def __del__(self):
        """清理资源."""
        if hasattr(self, '_landmarker') and self._landmarker:
            try:
                self._landmarker.close()
            except Exception:
                pass
