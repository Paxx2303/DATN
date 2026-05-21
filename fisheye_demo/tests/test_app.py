import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from fisheye_demo.app import (
    CLASS_NAMES,
    ModelRegistry,
    build_preprocessing_options,
    build_settings,
    create_app,
    run_external_camera_pipeline,
)
from fisheye_demo.fisheye import apply_fisheye


class AppRouteTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SETTINGS_OVERRIDES": {
                    "upload_dir": root / "uploads",
                    "results_dir": root / "results",
                    "recent_image_db_path": root / "recent_images.sqlite3",
                    "preload_model": False,
                },
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def make_image_buffer(self, color: str = "white") -> io.BytesIO:
        image = Image.new("RGB", (32, 32), color)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)
        return buffer

    def make_test_video(self, path: Path, num_frames: int = 5, width: int = 96, height: int = 64):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (width, height))
        for _ in range(num_frames):
            frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
            writer.write(frame)
        writer.release()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("model", payload)
        self.assertIn("storage", payload)
        self.assertIn("recent_image_store", payload)

    def test_config_endpoint(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["classes"], CLASS_NAMES)
        self.assertIn("fisheye", payload)
        self.assertIn("effect_labels_vi", payload["fisheye"])
        self.assertIn("standard", payload["fisheye"]["effect_labels_vi"])
        self.assertIn("media_support", payload)
        self.assertIn("external_camera_url", payload)
        self.assertEqual(payload["external_camera_limit"], 1)
        self.assertIn("external_camera_live_interval_seconds", payload)
        self.assertIn("camera_fisheye_effect", payload["defaults"])
        self.assertTrue(payload["defaults"]["camera_fisheye_full_frame"])
        self.assertEqual(payload["external_camera_live_interval_seconds"], 1.0)
        self.assertIn("recent_image_store", payload)
        self.assertEqual(payload["limits"]["recent_image_limit"], 100)
        self.assertIn("models", payload)
        self.assertIn("selectable", payload["models"])
        self.assertIsInstance(payload["models"]["selectable"], list)

    def test_history_empty(self):
        response = self.client.get("/api/history")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["items"], [])

    def test_recent_images_empty(self):
        response = self.client.get("/api/recent-images")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["storage"]["stored_images"], 0)

    def test_stats_returns_200(self):
        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)

    def test_stats_has_required_fields(self):
        response = self.client.get("/api/stats")
        payload = response.get_json()
        for field in ["total_runs", "total_detect", "total_convert", "class_totals", "avg_inference_ms"]:
            self.assertIn(field, payload)

    def test_stats_counts_are_non_negative(self):
        response = self.client.get("/api/stats")
        payload = response.get_json()
        self.assertGreaterEqual(payload["total_runs"], 0)
        self.assertGreaterEqual(payload["total_detect"], 0)
        self.assertGreaterEqual(payload["total_convert"], 0)

    def test_stats_total_equals_detect_plus_convert(self):
        response = self.client.get("/api/stats")
        payload = response.get_json()
        self.assertEqual(payload["total_runs"], payload["total_detect"] + payload["total_convert"])

    def test_external_camera_preprocessing_profile_defaults_to_normal_fisheye(self):
        settings = build_settings(
            {
                "upload_dir": Path(self.tempdir.name) / "uploads2",
                "results_dir": Path(self.tempdir.name) / "results2",
                "recent_image_db_path": Path(self.tempdir.name) / "recent_images_2.sqlite3",
            }
        )
        preprocessing = build_preprocessing_options({}, settings, default_source_layout="normal", profile="external_camera")
        self.assertEqual(preprocessing["source_layout"], "normal")
        self.assertTrue(preprocessing["enabled"])
        self.assertEqual(preprocessing["effect"], settings.camera_fisheye_effect)
        self.assertEqual(preprocessing["center_y_ratio"], settings.camera_fisheye_center_y)
        self.assertEqual(preprocessing["axis_scale_x"], settings.camera_fisheye_axis_scale_x)
        self.assertTrue(preprocessing["full_frame"])

    def test_model_registry_only_exposes_traffic_checkpoint_for_selection(self):
        settings = self.app.extensions["fisheye_settings"]
        registry = ModelRegistry(settings)

        with patch.object(
            registry,
            "list_available_models",
            return_value=[
                {"key": "sahi", "name": "sahi.pt", "is_fallback": False},
                {"key": "traffic", "name": "traffic.pt", "is_fallback": False},
                {"key": "yolo11n", "name": "yolo11n.pt", "is_fallback": True},
            ],
        ):
            selectable = registry.list_selectable_models()

        self.assertEqual(len(selectable), 1)
        self.assertEqual(selectable[0]["key"], "traffic")
        self.assertEqual(selectable[0]["name"], "traffic.pt")

    def test_apply_fisheye_supports_offcenter_elliptical_distortion(self):
        gradient = np.zeros((48, 64, 3), dtype=np.uint8)
        gradient[..., 0] = np.tile(np.arange(64, dtype=np.uint8), (48, 1))
        gradient[..., 1] = np.tile(np.arange(48, dtype=np.uint8)[:, None], (1, 64))
        image = Image.fromarray(gradient, mode="RGB")

        centered = apply_fisheye(image, strength=0.8, radius=1.0, effect="traffic_camera")
        offset = apply_fisheye(
            image,
            strength=0.8,
            radius=1.0,
            effect="traffic_camera",
            center_x_ratio=0.5,
            center_y_ratio=0.62,
            axis_scale_x=1.18,
            axis_scale_y=0.82,
        )

        self.assertEqual(centered.size, image.size)
        self.assertEqual(offset.size, image.size)
        self.assertFalse(np.array_equal(np.asarray(centered), np.asarray(offset)))

    def test_apply_fisheye_full_frame_reaches_edges(self):
        gradient = np.zeros((48, 64, 3), dtype=np.uint8)
        gradient[..., 0] = np.tile(np.arange(64, dtype=np.uint8), (48, 1))
        gradient[..., 1] = np.tile(np.arange(48, dtype=np.uint8)[:, None], (1, 64))
        image = Image.fromarray(gradient, mode="RGB")

        inset = apply_fisheye(
            image,
            strength=0.82,
            radius=1.0,
            effect="traffic_camera",
            center_x_ratio=0.5,
            center_y_ratio=0.62,
            axis_scale_x=1.18,
            axis_scale_y=0.82,
            full_frame=False,
        )
        full = apply_fisheye(
            image,
            strength=0.82,
            radius=1.0,
            effect="traffic_camera",
            center_x_ratio=0.5,
            center_y_ratio=0.62,
            axis_scale_x=1.18,
            axis_scale_y=0.82,
            full_frame=True,
        )

        self.assertFalse(np.array_equal(np.asarray(inset), np.asarray(full)))

    def test_stats_aggregates_metadata(self):
        results_dir = self.app.extensions["fisheye_settings"].results_dir

        detect_image_dir = results_dir / "run-image"
        detect_image_dir.mkdir(parents=True, exist_ok=True)
        (detect_image_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "task": "detect",
                    "summary": {
                        "inference_ms": 10.0,
                        "class_counts": {"Car": 2, "Pedestrian": 1},
                    },
                }
            ),
            encoding="utf-8",
        )

        detect_video_dir = results_dir / "run-video"
        detect_video_dir.mkdir(parents=True, exist_ok=True)
        (detect_video_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "task": "detect",
                    "summary": {
                        "inference_ms_avg": 30.0,
                        "class_counts": {"Car": 3, "Bus": 1},
                    },
                }
            ),
            encoding="utf-8",
        )

        convert_dir = results_dir / "run-convert"
        convert_dir.mkdir(parents=True, exist_ok=True)
        (convert_dir / "metadata.json").write_text(json.dumps({"task": "convert"}), encoding="utf-8")

        response = self.client.get("/api/stats")
        payload = response.get_json()
        self.assertEqual(payload["total_runs"], 3)
        self.assertEqual(payload["total_detect"], 2)
        self.assertEqual(payload["total_convert"], 1)
        self.assertEqual(payload["class_totals"]["Car"], 5)
        self.assertEqual(payload["class_totals"]["Pedestrian"], 1)
        self.assertEqual(payload["class_totals"]["Bus"], 1)
        self.assertEqual(payload["avg_inference_ms"], 20.0)

    @patch("fisheye_demo.app.build_camera_collage")
    @patch("fisheye_demo.app.run_inference")
    @patch("fisheye_demo.app.download_camera_snapshot")
    @patch("fisheye_demo.app.extract_camera_entries")
    def test_external_camera_detect_returns_200(
        self,
        mock_extract_entries,
        mock_download_snapshot,
        mock_run_inference,
        mock_build_collage,
    ):
        from fisheye_demo.external_camera_detector import ExternalCameraItem

        mock_extract_entries.return_value = [
            ExternalCameraItem(index=0, embed_url="https://www.youtube.com/embed/a123456", youtube_id="a123456", title="Camera 1", snapshot_url="https://i.ytimg.com/vi/a123456/hqdefault_live.jpg"),
        ]
        mock_download_snapshot.return_value = Image.new("RGB", (64, 64), "white")
        mock_run_inference.return_value = (
            Image.new("RGB", (64, 64), "red"),
            [{"class": "Car", "raw_class": "car", "confidence": 0.9, "bbox": [1, 1, 10, 10], "color": "#4FC3F7"}],
            {"Car": 1, "Bus": 0, "Truck": 0, "Pedestrian": 0, "Motorbike": 0},
            11.0,
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )
        mock_build_collage.return_value = Image.new("RGB", (128, 128), "blue")

        response = self.client.post(
            "/api/external-camera/detect",
            data={"external_camera_url": "https://camera.0511.vn/camera.html"},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["task"], "detect")
        self.assertEqual(payload["media_type"], "external_camera_grid")
        self.assertEqual(payload["camera_count"], 1)
        self.assertEqual(len(payload["cameras"]), 1)
        self.assertEqual(payload["preprocessing"]["source_layout"], "normal")
        self.assertTrue(payload["preprocessing"]["enabled"])
        self.assertIn("overview_annotated", payload["record"]["artifact_urls"])

    @patch("fisheye_demo.app.build_camera_collage")
    @patch("fisheye_demo.app.run_inference")
    @patch("fisheye_demo.app.download_camera_snapshot")
    @patch("fisheye_demo.app.extract_camera_entries")
    def test_external_camera_pipeline_stream_frame_key_matches_camera_index(
        self,
        mock_extract_entries,
        mock_download_snapshot,
        mock_run_inference,
        mock_build_collage,
    ):
        from fisheye_demo.external_camera_detector import ExternalCameraItem

        mock_extract_entries.return_value = [
            ExternalCameraItem(
                index=0,
                embed_url="https://www.youtube.com/embed/a123456",
                youtube_id="a123456",
                title="Camera 1",
                snapshot_url="https://i.ytimg.com/vi/a123456/hqdefault_live.jpg",
            )
        ]
        mock_download_snapshot.return_value = Image.new("RGB", (64, 64), "white")
        mock_run_inference.return_value = (
            Image.new("RGB", (64, 64), "red"),
            [{"class": "Car", "raw_class": "car", "confidence": 0.9, "bbox": [1, 1, 10, 10], "color": "#4FC3F7"}],
            {"Car": 1, "Bus": 0, "Truck": 0, "Pedestrian": 0, "Motorbike": 0},
            11.0,
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )
        mock_build_collage.return_value = Image.new("RGB", (128, 128), "blue")

        settings = self.app.extensions["fisheye_settings"]
        registry = self.app.extensions["fisheye_model_registry"]
        payload = run_external_camera_pipeline(
            registry,
            settings,
            self.app.extensions["fisheye_recent_image_store"],
            "snapshot",
            "https://camera.0511.vn/camera.html",
            "",
            1,
            {
                "source_layout": "normal",
                "enabled": True,
                "strength": 0.82,
                "radius": 1.0,
                "effect": "traffic_camera",
                "center_x_ratio": 0.5,
                "center_y_ratio": 0.6,
                "axis_scale_x": 1.18,
                "axis_scale_y": 0.82,
                "full_frame": True,
                "profile": "external_camera",
            },
            0.25,
            0.45,
            None,
            False,
        )

        self.assertIn("overview", payload["stream_frames"])
        self.assertIn("camera_1", payload["stream_frames"])
        self.assertNotIn("camera_2", payload["stream_frames"])

    def test_external_camera_source_returns_stream_payload_when_stream_mode_enabled(self):
        app = create_app(
            {
                "TESTING": True,
                "SETTINGS_OVERRIDES": {
                    "upload_dir": Path(self.tempdir.name) / "stream-uploads",
                    "results_dir": Path(self.tempdir.name) / "stream-results",
                    "recent_image_db_path": Path(self.tempdir.name) / "stream_recent.sqlite3",
                    "preload_model": False,
                    "external_camera_source_mode": "stream",
                    "external_camera_stream_url": "rtsp://example.com/live",
                    "external_camera_url": "rtsp://example.com/live",
                },
            }
        )
        client = app.test_client()

        response = client.get("/api/external-camera/source")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["source_mode"], "stream")
        self.assertEqual(payload["stream_url"], "rtsp://example.com/live")
        self.assertIsNone(payload["embed_url"])

    @patch("fisheye_demo.app.extract_camera_entries")
    def test_external_camera_source_returns_embed_video(self, mock_extract_entries):
        from fisheye_demo.external_camera_detector import ExternalCameraItem

        mock_extract_entries.return_value = [
            ExternalCameraItem(
                index=0,
                embed_url="https://www.youtube.com/embed/a123456?autoplay=1",
                youtube_id="a123456",
                title="Camera 1",
                snapshot_url="https://i.ytimg.com/vi/a123456/hqdefault_live.jpg",
            )
        ]

        response = self.client.get("/api/external-camera/source?external_camera_url=https://camera.0511.vn/camera.html")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["youtube_id"], "a123456")
        self.assertIn("/embed/a123456", payload["embed_url"])
        self.assertEqual(payload["title"], "Camera 1")

    @patch("fisheye_demo.app.capture_stream_frame")
    @patch("fisheye_demo.app.run_inference")
    def test_external_camera_detect_uses_stream_source_in_stream_mode(
        self,
        mock_run_inference,
        mock_capture_stream_frame,
    ):
        app = create_app(
            {
                "TESTING": True,
                "SETTINGS_OVERRIDES": {
                    "upload_dir": Path(self.tempdir.name) / "stream-detect-uploads",
                    "results_dir": Path(self.tempdir.name) / "stream-detect-results",
                    "recent_image_db_path": Path(self.tempdir.name) / "stream_detect.sqlite3",
                    "preload_model": False,
                    "external_camera_source_mode": "stream",
                    "external_camera_stream_url": "rtsp://example.com/live",
                    "external_camera_url": "rtsp://example.com/live",
                },
            }
        )
        client = app.test_client()

        mock_capture_stream_frame.return_value = Image.new("RGB", (64, 64), "white")
        mock_run_inference.return_value = (
            Image.new("RGB", (64, 64), "red"),
            [{"class": "Car", "raw_class": "car", "confidence": 0.9, "bbox": [1, 1, 10, 10], "color": "#4FC3F7"}],
            {"Car": 1, "Bus": 0, "Truck": 0, "Pedestrian": 0, "Motorbike": 0},
            11.0,
            {
                "source": "custom",
                "loaded_from": "traffic.pt",
                "loaded_from_name": "traffic.pt",
                "device": "cpu",
            },
        )

        response = client.post(
            "/api/external-camera/detect",
            data={"external_camera_url": "rtsp://example.com/live"},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["camera_count"], 1)
        self.assertEqual(payload["cameras"][0]["stream_url"], "rtsp://example.com/live")
        mock_capture_stream_frame.assert_called_once_with("rtsp://example.com/live")

    def test_external_camera_live_status_returns_200(self):
        response = self.client.get("/api/external-camera/live/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("running", payload)
        self.assertIn("status", payload)
        self.assertIn("interval_seconds", payload)
        self.assertIn("actual_cycle_fps", payload)
        self.assertIn("last_cycle_duration_ms", payload)
        self.assertIn("stream_ready", payload)

    def test_external_camera_live_stream_returns_mjpeg(self):
        live_monitor = self.app.extensions["fisheye_live_monitor"]
        with (
            patch.object(live_monitor, "get_stream_frame_snapshot", return_value=(1, b"fakejpeg", False)),
            self.assertLogs("fisheye_demo.live", level="INFO") as captured,
        ):
            response = self.client.get("/api/external-camera/live/stream?view=overview", buffered=False)
            self.assertEqual(response.status_code, 200)
            self.assertIn("multipart/x-mixed-replace", response.mimetype)
            first_chunk = next(response.response)
            self.assertIn(b"Content-Type: image/jpeg", first_chunk)

        joined_logs = "\n".join(captured.output)
        self.assertIn("MJPEG client connected", joined_logs)
        self.assertIn("MJPEG first annotated frame ready", joined_logs)

    def test_external_camera_live_worker_logs_cycle_completion(self):
        live_monitor = self.app.extensions["fisheye_live_monitor"]
        fake_payload = {
            "source_url": "https://camera.0511.vn/camera.html",
            "camera_count": 1,
            "overview": "base64-overview",
            "summary": {"camera_count": 1, "total_objects": 4},
            "preprocessing": {"source_layout": "normal", "enabled": True},
            "model": {"name": "fake-model.pt"},
            "cameras": [{"index": 0, "title": "Camera 1"}],
            "stream_frames": {"overview": b"frame-a", "camera_1": b"frame-b"},
        }

        def fake_pipeline(*args, **kwargs):
            live_monitor._stop_event.set()
            return fake_payload

        with (
            patch("fisheye_demo.app.run_external_camera_pipeline", side_effect=fake_pipeline),
            self.assertLogs("fisheye_demo.live", level="INFO") as captured,
        ):
            live_monitor._stop_event.clear()
            live_monitor._worker_loop(
                source_mode="snapshot",
                source_url="https://camera.0511.vn/camera.html",
                stream_url="",
                camera_limit=1,
                preprocessing={"source_layout": "normal", "enabled": True},
                conf_threshold=0.25,
                iou_threshold=0.45,
                model_key=None,
                interval_seconds=1.0,
            )

        joined_logs = "\n".join(captured.output)
        self.assertIn("Live cycle complete", joined_logs)
        self.assertIn("Live worker exit", joined_logs)

    def test_external_camera_live_start_returns_started_state(self):
        live_monitor = self.app.extensions["fisheye_live_monitor"]
        with patch.object(
            live_monitor,
            "start",
            return_value={
                "running": True,
                "status": "starting",
                "interval_seconds": 1.0,
                "camera_limit": 1,
                "source_url": "https://camera.0511.vn/camera.html",
                "preprocessing": {"source_layout": "normal", "enabled": True, "strength": 0.7, "radius": 0.85, "effect": "standard"},
                "conf_threshold": 0.25,
                "iou_threshold": 0.45,
                "last_result": None,
            },
        ) as mock_start:
            response = self.client.post(
                "/api/external-camera/live/start",
                data={
                    "external_camera_url": "https://camera.0511.vn/camera.html",
                    "camera_limit": "1",
                    "interval_seconds": "1.0",
                    "source_layout": "normal",
                    "apply_fisheye": "true",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["running"])
        self.assertEqual(payload["interval_seconds"], 1.0)
        self.assertEqual(mock_start.call_args.kwargs["camera_limit"], 1)
        self.assertEqual(mock_start.call_args.kwargs["interval_seconds"], 1.0)
        self.assertTrue(mock_start.call_args.kwargs["preprocessing"]["enabled"])
        self.assertIsNone(mock_start.call_args.kwargs["model_key"])

    def test_external_camera_live_stop_returns_stopped_state(self):
        live_monitor = self.app.extensions["fisheye_live_monitor"]
        with patch.object(
            live_monitor,
            "stop",
            return_value={
                "running": False,
                "status": "stopped",
                "interval_seconds": 1.0,
                "camera_limit": 1,
                "source_url": "https://camera.0511.vn/camera.html",
                "preprocessing": {"source_layout": "fisheye", "enabled": False, "strength": 0.7, "radius": 0.85, "effect": "standard"},
                "conf_threshold": 0.25,
                "iou_threshold": 0.45,
                "last_result": None,
            },
        ):
            response = self.client.post("/api/external-camera/live/stop")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["running"])
        self.assertEqual(payload["status"], "stopped")

    def test_detect_requires_file(self):
        response = self.client.post("/api/detect", data={}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    @patch("fisheye_demo.app.save_detection_record")
    @patch("fisheye_demo.app.run_inference")
    def test_detect_success_with_fisheye_preprocess(self, mock_run_inference, mock_save_record):
        test_image = Image.new("RGB", (32, 32), "white")
        class_counts = {name: 0 for name in CLASS_NAMES}
        class_counts["Car"] = 1

        mock_run_inference.return_value = (
            test_image,
            [{"class": "Car", "raw_class": "car", "confidence": 0.95, "bbox": [1, 2, 16, 20], "color": "#4FC3F7"}],
            class_counts,
            12.4,
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )
        mock_save_record.return_value = {
            "id": "run-001",
            "filename": "frame.jpg",
            "task": "detect",
            "media_type": "image",
            "created_at": "2026-05-09T00:00:00Z",
            "summary": {"total_objects": 1, "inference_ms": 12.4, "class_counts": class_counts},
            "detections": [{"class": "Car", "raw_class": "car", "confidence": 0.95, "bbox": [1, 2, 16, 20], "color": "#4FC3F7"}],
            "model": {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
            "artifacts": {
                "original": "original.jpg",
                "preprocessed": "preprocessed.jpg",
                "annotated": "annotated.jpg",
                "metadata": "metadata.json",
            },
        }

        response = self.client.post(
            "/api/detect",
            data={
                "image": (self.make_image_buffer(), "frame.jpg"),
                "conf": "0.25",
                "iou": "0.45",
                "source_layout": "normal",
                "apply_fisheye": "true",
                "fisheye_strength": "0.8",
                "fisheye_radius": "0.9",
                "fisheye_effect": "standard",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total_objects"], 1)
        self.assertEqual(payload["record"]["id"], "run-001")
        self.assertTrue(payload["preprocessing"]["enabled"])
        self.assertEqual(payload["preprocessing"]["source_layout"], "normal")
        self.assertIn("artifact_urls", payload["record"])

    def test_convert_image_success(self):
        response = self.client.post(
            "/api/convert",
            data={
                "media": (self.make_image_buffer("blue"), "street.jpg"),
                "source_layout": "normal",
                "fisheye_strength": "0.65",
                "fisheye_radius": "0.85",
                "fisheye_effect": "subtle",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["task"], "convert")
        self.assertEqual(payload["media_type"], "image")
        self.assertTrue(payload["preprocessing"]["enabled"])
        self.assertIn("fisheye_image", payload["record"]["artifact_urls"])

        recent_response = self.client.get("/api/recent-images")
        self.assertEqual(recent_response.status_code, 200)
        recent_payload = recent_response.get_json()
        self.assertEqual(len(recent_payload["items"]), 1)
        item = recent_payload["items"][0]
        self.assertEqual(item["source_result_id"], payload["record"]["id"])
        self.assertEqual(item["image_role"], "fisheye_image")
        self.assertIn("/api/recent-images/", item["image_url"])

        image_response = self.client.get(item["image_url"])
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/jpeg")

    def test_convert_image_accepts_file_alias(self):
        response = self.client.post(
            "/api/convert",
            data={
                "file": (self.make_image_buffer("green"), "street.jpg"),
                "source_layout": "normal",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["media_type"], "image")
        self.assertEqual(payload["task"], "convert")

    @patch("fisheye_demo.app.run_video_detect")
    @patch("fisheye_demo.app.ModelRegistry.load")
    def test_detect_video_returns_200(self, mock_model_load, mock_run_video_detect):
        mock_model_load.return_value = (
            SimpleNamespace(names={}),
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )

        def create_outputs(*, output_path, preview_path, **_kwargs):
            Path(output_path).write_bytes(b"fake-video")
            Image.new("RGB", (32, 32), "red").save(preview_path, format="JPEG")
            return {
                "total_frames": 5,
                "fps_original": 10.0,
                "resolution": "96x64",
                "inference_ms_avg": 6.2,
                "class_counts": {"Car": 3, "Pedestrian": 1},
                "total_detections": 4,
            }

        mock_run_video_detect.side_effect = create_outputs

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            self.make_test_video(temp_path)
            with temp_path.open("rb") as video_file:
                response = self.client.post(
                    "/api/detect",
                    data={"file": (video_file, "traffic.mp4")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["task"], "detect")
            self.assertEqual(payload["media_type"], "video")
            self.assertIn("summary", payload)
            self.assertIn("artifact_urls", payload["record"])
            self.assertIn("annotated_video", payload["record"]["artifact_urls"])
        finally:
            temp_path.unlink(missing_ok=True)

    @patch("fisheye_demo.app.run_video_detect")
    @patch("fisheye_demo.app.ModelRegistry.load")
    def test_detect_video_summary_fields(self, mock_model_load, mock_run_video_detect):
        mock_model_load.return_value = (
            SimpleNamespace(names={}),
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )

        def create_outputs(*, output_path, preview_path, **_kwargs):
            Path(output_path).write_bytes(b"fake-video")
            Image.new("RGB", (32, 32), "blue").save(preview_path, format="JPEG")
            return {
                "total_frames": 5,
                "fps_original": 10.0,
                "resolution": "96x64",
                "inference_ms_avg": 5.4,
                "class_counts": {"Car": 2},
                "total_detections": 2,
            }

        mock_run_video_detect.side_effect = create_outputs

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            self.make_test_video(temp_path)
            with temp_path.open("rb") as video_file:
                response = self.client.post(
                    "/api/detect",
                    data={"file": (video_file, "traffic.mp4"), "source_layout": "fisheye"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 200)
            summary = response.get_json()["summary"]
            self.assertIn("total_frames", summary)
            self.assertIn("fps_original", summary)
            self.assertIn("inference_ms_avg", summary)
            self.assertIn("class_counts", summary)
            self.assertGreater(summary["total_frames"], 0)
        finally:
            temp_path.unlink(missing_ok=True)

    @patch("fisheye_demo.app.run_video_detect")
    @patch("fisheye_demo.app.ModelRegistry.load")
    def test_detect_video_uses_selected_model_key(self, mock_model_load, mock_run_video_detect):
        mock_model_load.return_value = (
            SimpleNamespace(names={}),
            {
                "source": "custom",
                "loaded_from": "traffic.pt",
                "loaded_from_name": "traffic.pt",
                "device": "cpu",
                "selected_key": "traffic",
                "selected_name": "traffic.pt",
            },
        )

        def create_outputs(*, output_path, preview_path, **_kwargs):
            Path(output_path).write_bytes(b"fake-video")
            Image.new("RGB", (32, 32), "green").save(preview_path, format="JPEG")
            return {
                "total_frames": 5,
                "fps_original": 10.0,
                "resolution": "96x64",
                "inference_ms_avg": 5.4,
                "class_counts": {"Car": 2},
                "total_detections": 2,
            }

        mock_run_video_detect.side_effect = create_outputs

        registry = self.app.extensions["fisheye_model_registry"]
        with patch.object(
            registry,
            "get_model_entry",
            side_effect=lambda model_key=None, selectable_only=True: {"key": "traffic", "name": "traffic.pt"} if model_key in {None, "traffic"} else None,
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                self.make_test_video(temp_path)
                with temp_path.open("rb") as video_file:
                    response = self.client.post(
                        "/api/detect",
                        data={"file": (video_file, "traffic.mp4"), "model_key": "traffic"},
                        content_type="multipart/form-data",
                    )
                self.assertEqual(response.status_code, 200)
                mock_model_load.assert_called_with("traffic")
            finally:
                temp_path.unlink(missing_ok=True)

    @patch("fisheye_demo.app.save_detection_record")
    @patch("fisheye_demo.app.run_inference")
    def test_detect_accepts_file_and_confidence_aliases(self, mock_run_inference, mock_save_record):
        test_image = Image.new("RGB", (32, 32), "white")
        class_counts = {name: 0 for name in CLASS_NAMES}

        mock_run_inference.return_value = (
            test_image,
            [],
            class_counts,
            8.5,
            {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
        )
        mock_save_record.return_value = {
            "id": "run-002",
            "filename": "frame.jpg",
            "task": "detect",
            "media_type": "image",
            "created_at": "2026-05-11T00:00:00Z",
            "summary": {"total_objects": 0, "inference_ms": 8.5, "class_counts": class_counts},
            "detections": [],
            "model": {
                "source": "custom",
                "loaded_from": "mock-model.pt",
                "loaded_from_name": "mock-model.pt",
                "device": "cpu",
            },
            "artifacts": {
                "original": "original.jpg",
                "annotated": "annotated.jpg",
                "metadata": "metadata.json",
            },
        }

        response = self.client.post(
            "/api/detect",
            data={
                "file": (self.make_image_buffer(), "frame.jpg"),
                "confidence": "0.31",
                "iou": "0.44",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["request_id"], "run-002")

    @patch("fisheye_demo.app.save_detection_record")
    @patch("fisheye_demo.app.run_inference")
    def test_detect_passes_selected_model_key_to_inference(self, mock_run_inference, mock_save_record):
        test_image = Image.new("RGB", (32, 32), "white")
        class_counts = {name: 0 for name in CLASS_NAMES}

        mock_run_inference.return_value = (
            test_image,
            [],
            class_counts,
            8.5,
            {
                "source": "custom",
                "loaded_from": "traffic.pt",
                "loaded_from_name": "traffic.pt",
                "device": "cpu",
                "selected_key": "traffic",
                "selected_name": "traffic.pt",
            },
        )
        mock_save_record.return_value = {
            "id": "run-003",
            "filename": "frame.jpg",
            "task": "detect",
            "media_type": "image",
            "created_at": "2026-05-11T00:00:00Z",
            "summary": {"total_objects": 0, "inference_ms": 8.5, "class_counts": class_counts},
            "detections": [],
            "model": {
                "source": "custom",
                "loaded_from": "traffic.pt",
                "loaded_from_name": "traffic.pt",
                "device": "cpu",
                "selected_key": "traffic",
                "selected_name": "traffic.pt",
            },
            "artifacts": {
                "original": "original.jpg",
                "annotated": "annotated.jpg",
                "metadata": "metadata.json",
            },
        }

        registry = self.app.extensions["fisheye_model_registry"]
        with patch.object(
            registry,
            "get_model_entry",
            side_effect=lambda model_key=None, selectable_only=True: {"key": "traffic", "name": "traffic.pt"} if model_key in {None, "traffic"} else None,
        ):
            response = self.client.post(
                "/api/detect",
                data={
                    "file": (self.make_image_buffer(), "frame.jpg"),
                    "model_key": "traffic",
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_run_inference.call_args.kwargs["model_key"], "traffic")

    def test_recent_image_store_keeps_only_latest_100_images(self):
        store = self.app.extensions["fisheye_recent_image_store"]
        jpeg_bytes = self.make_image_buffer("purple").getvalue()

        for index in range(105):
            minute = index // 60
            second = index % 60
            store.add_image(
                source_key=f"case-{index}",
                source_result_id=f"run-{index}",
                task="convert",
                media_type="image",
                image_role="fisheye_image",
                filename="fisheye.jpg",
                mime_type="image/jpeg",
                width=32,
                height=32,
                created_at=f"2026-05-13T00:{minute:02d}:{second:02d}Z",
                metadata={"index": index},
                image_bytes=jpeg_bytes,
            )

        items = store.list_recent(100)
        self.assertEqual(len(items), 100)
        self.assertEqual(store.stats()["stored_images"], 100)
        source_ids = {item["source_result_id"] for item in items}
        self.assertNotIn("run-0", source_ids)
        self.assertNotIn("run-4", source_ids)
        self.assertIn("run-5", source_ids)
        self.assertIn("run-104", source_ids)


if __name__ == "__main__":
    unittest.main()
