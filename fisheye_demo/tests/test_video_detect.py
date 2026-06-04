"""
tests/test_video_detect.py — Video Processing Logic Tests
"""

import pytest
from video_detect import detection_stride


class TestDetectionStride:
    @pytest.mark.parametrize("fps_src,target_fps,expected", [
        (30.0, 5.0, 6),
        (25.0, 5.0, 5),
        (30.0, 30.0, 1),   # target == source → no skipping
        (30.0, None, 1),    # None target → process every frame
        (30.0, 0.0, 1),     # 0 target → guard against div/0
        (30.0, 100.0, 1),   # target > source → clamp to 1
    ])
    def test_stride_calculation(self, fps_src, target_fps, expected):
        assert detection_stride(fps_src, target_fps) == expected
