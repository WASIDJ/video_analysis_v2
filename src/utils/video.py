"""视频处理工具."""
import subprocess
from pathlib import Path
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np


def get_video_rotation(video_path: str) -> int:
    """获取视频旋转角度.

    使用ffprobe检测视频元数据中的旋转信息.

    Args:
        video_path: 视频文件路径

    Returns:
        旋转角度（0, 90, 180, 270）
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "side_data=rotation",
            "-of", "default=nw=1:nk=1",
            video_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            rotation = int(float(result.stdout.strip()))
            # 标准化到0, 90, 180, 270
            return rotation % 360

    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass

    # 备用方案：尝试从width/height推断
    try:
        cap = cv2.VideoCapture(video_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # 如果高度大于宽度，可能是竖屏视频
        if height > width:
            return 90
    except Exception:
        pass

    return 0


def rotate_frame(frame: np.ndarray, rotation: int) -> np.ndarray:
    """旋转帧.

    Args:
        frame: 输入帧
        rotation: 旋转角度（0, 90, 180, 270, -90）

    Returns:
        旋转后的帧
    """
    if rotation == 0:
        return frame
    elif rotation in (90, -270):
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation in (180, -180):
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation in (270, -90):
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        # 任意角度旋转
        (h, w) = frame.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, rotation, 1.0)
        return cv2.warpAffine(frame, M, (w, h))


class VideoFrameIterator:
    """视频帧迭代器.

    支持:
    - 自动旋转校正
    - 目标FPS采样
    - 最大分辨率限制
    """

    def __init__(
        self,
        video_path: str,
        target_fps: Optional[float] = None,
        max_resolution: Optional[int] = None,
        auto_rotate: bool = True,
    ):
        """
        Args:
            video_path: 视频路径
            target_fps: 目标帧率（None表示使用原始帧率）
            max_resolution: 最大分辨率（长边）
            auto_rotate: 是否自动旋转
        """
        self.video_path = Path(video_path)
        self.target_fps = target_fps
        self.max_resolution = max_resolution
        self.auto_rotate = auto_rotate

        # 打开视频
        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            raise ValueError(f"无法打开视频: {video_path}")

        # 获取视频信息
        self.original_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.original_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.original_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 旋转校正
        self.rotation = get_video_rotation(str(self.video_path)) if auto_rotate else 0
        if self.rotation in (90, 270):
            self.width, self.height = self.original_height, self.original_width
        else:
            self.width, self.height = self.original_width, self.original_height

        # 计算缩放比例
        self.scale = 1.0
        if max_resolution and max(self.width, self.height) > max_resolution:
            self.scale = max_resolution / max(self.width, self.height)
            self.width = int(self.width * self.scale)
            self.height = int(self.height * self.scale)

        # 计算采样间隔
        self.frame_interval = 1
        if target_fps and self.original_fps > 0:
            self.frame_interval = max(1, int(round(self.original_fps / target_fps)))

        self.current_frame = 0
        self.frame_count = 0

    def __iter__(self) -> Iterator[Tuple[int, np.ndarray]]:
        """迭代器.

        Yields:
            (frame_id, frame) 元组
        """
        return self

    def __next__(self) -> Tuple[int, np.ndarray]:
        """获取下一帧."""
        while True:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.release()
                raise StopIteration

            self.current_frame += 1

            # 按间隔采样
            if (self.current_frame - 1) % self.frame_interval != 0:
                continue

            self.frame_count += 1

            # 应用旋转
            if self.rotation != 0:
                frame = rotate_frame(frame, self.rotation)

            # 缩放
            if self.scale != 1.0:
                frame = cv2.resize(frame, (self.width, self.height))

            return self.frame_count - 1, frame

    def __len__(self) -> int:
        """估计的帧数."""
        return self.total_frames // self.frame_interval

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cap.release()
        return False

    def get_video_info(self) -> dict:
        """获取视频信息."""
        return {
            "path": str(self.video_path),
            "original_fps": self.original_fps,
            "target_fps": self.target_fps or self.original_fps,
            "total_frames": self.total_frames,
            "original_width": self.original_width,
            "original_height": self.original_height,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "scale": self.scale,
        }


def save_video(
    frames: list,
    output_path: str,
    fps: float = 30.0,
    codec: str = "mp4v",
) -> None:
    """保存视频.

    Args:
        frames: 帧列表
        output_path: 输出路径
        fps: 帧率
        codec: 编码器
    """
    if not frames:
        return

    height, width = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*codec)
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for frame in frames:
        out.write(frame)

    out.release()
