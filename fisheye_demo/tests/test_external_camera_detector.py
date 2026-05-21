from __future__ import annotations

import unittest

from fisheye_demo.external_camera_detector import sanitize_camera_title


class SanitizeCameraTitleTests(unittest.TestCase):
    def test_strips_alt_attribute_junk(self) -> None:
        self.assertEqual(
            sanitize_camera_title('Camera" />', fallback="Cam X"),
            "Camera",
        )

    def test_keeps_plain_label(self) -> None:
        self.assertEqual(
            sanitize_camera_title("Camera 1 - Ngã tư", fallback="X"),
            "Camera 1 - Ngã tư",
        )


if __name__ == "__main__":
    unittest.main()
