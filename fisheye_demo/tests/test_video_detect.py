from __future__ import annotations

import unittest

from fisheye_demo.video_detect import detection_stride


class DetectionStrideTests(unittest.TestCase):
    def test_full_rate_when_target_missing(self) -> None:
        self.assertEqual(detection_stride(30.0, None), 1)
        self.assertEqual(detection_stride(30.0, 0), 1)

    def test_full_rate_when_target_ge_source(self) -> None:
        self.assertEqual(detection_stride(24.0, 30.0), 1)
        self.assertEqual(detection_stride(24.0, 24.0), 1)

    def test_stride_matches_rounded_ratio(self) -> None:
        self.assertEqual(detection_stride(30.0, 10.0), 3)
        self.assertEqual(detection_stride(29.97, 10.0), 3)


if __name__ == "__main__":
    unittest.main()
