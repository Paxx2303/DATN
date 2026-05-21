"""
routes_extended.py — Các route mở rộng cho fisheye_demo

Đăng ký vào Flask app qua hàm register_extended_routes(app, settings, registry, ...)

Routes mới:
  GET  /api/db/health                  — kiểm tra DB
  GET  /api/analytics                  — dashboard analytics tổng hợp
  GET  /api/analytics/hourly           — biểu đồ traffic theo giờ
  GET  /api/analytics/class-dist       — phân bố class
  GET  /api/analytics/peak-hours       — giờ cao điểm
  GET  /api/analytics/heatmap          — heatmap vị trí detect
  GET  /api/alerts                     — danh sách alerts
  POST /api/alerts/<id>/acknowledge    — xác nhận alert
  GET  /api/alerts/thresholds          — lấy ngưỡng cảnh báo
  POST /api/alerts/thresholds          — cập nhật ngưỡng
  GET  /api/cloud/gallery              — ảnh cloud 6h gần nhất
  GET  /api/cloud/stats                — thống kê GCS bucket
  POST /api/cloud/cleanup              — trigger cleanup thủ công
  GET  /api/line-counter               — thống kê line counter
  POST /api/line-counter/reset         — reset counter
  GET  /api/detections                 — lịch sử detections từ DB
  GET  /api/live-sessions              — lịch sử live sessions
  GET  /api/export/csv                 — export CSV thống kê
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, jsonify, request

logger = logging.getLogger("fisheye_demo.routes_extended")


def register_extended_routes(
    app: Flask,
    settings: Any,
    registry: Any,
    heatmap,
    density_analyzer,
    alert_manager,
    line_counter,
    speed_estimator=None,       # SpeedEstimator instance
    congestion_detector=None,   # CongestionDetector instance
) -> None:
    """Đăng ký tất cả extended routes vào Flask app."""

    # ── DB Health ────────────────────────────────────────────────────────────

    @app.get("/api/db/health")
    def api_db_health():
        try:
            try:
                from db import health_check, init_db
            except ImportError:
                from fisheye_demo.db import health_check, init_db
            backend = init_db()
            result = health_check()
            return jsonify({"backend": backend, **result})
        except Exception as exc:
            return jsonify({"status": "error", "error": str(exc)}), 500

    # ── Analytics ────────────────────────────────────────────────────────────

    @app.get("/api/analytics")
    def api_analytics():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        try:
            try:
                from analytics import build_analytics_from_db
            except ImportError:
                from fisheye_demo.analytics import build_analytics_from_db
            data = build_analytics_from_db(hours=hours)
            # Thêm live density stats
            data["density"] = density_analyzer.get_summary()
            data["heatmap_stats"] = heatmap.get_stats()
            return jsonify(data)
        except Exception as exc:
            logger.error("api_analytics error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/analytics/hourly")
    def api_analytics_hourly():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        camera_source = request.args.get("camera_source") or None
        try:
            try:
                from db import get_hourly_traffic_chart
            except ImportError:
                from fisheye_demo.db import get_hourly_traffic_chart
            chart = get_hourly_traffic_chart(hours=hours, camera_source=camera_source)
            return jsonify({"hours": hours, "camera_source": camera_source, "data": chart})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/analytics/class-dist")
    def api_analytics_class_dist():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        try:
            try:
                from db import get_class_distribution
                from analytics import compute_class_percentages
            except ImportError:
                from fisheye_demo.db import get_class_distribution
                from fisheye_demo.analytics import compute_class_percentages
            dist = get_class_distribution(hours=hours)
            percentages = compute_class_percentages(dist)
            return jsonify({
                "hours": hours,
                "counts": dist,
                "percentages": percentages,
                "total": sum(dist.values()),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/analytics/peak-hours")
    def api_analytics_peak_hours():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        top_n = _parse_int(request.args.get("top"), default=3, minimum=1, maximum=10)
        try:
            try:
                from db import get_hourly_traffic_chart
                from analytics import detect_peak_hours
            except ImportError:
                from fisheye_demo.db import get_hourly_traffic_chart
                from fisheye_demo.analytics import detect_peak_hours
            chart = get_hourly_traffic_chart(hours=hours)
            peaks = detect_peak_hours(chart, top_n=top_n)
            return jsonify({"hours": hours, "top_n": top_n, "peaks": peaks})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/analytics/heatmap")
    def api_analytics_heatmap():
        b64 = heatmap.to_base64_jpeg()
        stats = heatmap.get_stats()
        return jsonify({
            "heatmap_b64": b64,
            "stats": stats,
        })

    @app.post("/api/analytics/heatmap/reset")
    def api_analytics_heatmap_reset():
        heatmap.reset()
        return jsonify({"status": "ok", "message": "Heatmap đã được reset"})

    # ── Alerts ───────────────────────────────────────────────────────────────

    @app.get("/api/alerts")
    def api_alerts():
        limit = _parse_int(request.args.get("limit"), default=50, minimum=1, maximum=200)
        unack_only = request.args.get("unacknowledged", "").lower() in ("1", "true", "yes")
        try:
            try:
                from db import list_alerts
            except ImportError:
                from fisheye_demo.db import list_alerts
            alerts = list_alerts(limit=limit, unacknowledged_only=unack_only)
            # Merge với in-memory buffer
            mem_alerts = alert_manager.get_recent_alerts(limit=20)
            return jsonify({
                "alerts": alerts,
                "recent_memory": mem_alerts,
                "total": len(alerts),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/alerts/<int:alert_id>/acknowledge")
    def api_alert_acknowledge(alert_id: int):
        try:
            try:
                from db import acknowledge_alert
            except ImportError:
                from fisheye_demo.db import acknowledge_alert
            acknowledge_alert(alert_id)
            return jsonify({"status": "ok", "alert_id": alert_id})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/alerts/thresholds")
    def api_alert_thresholds_get():
        return jsonify({"thresholds": alert_manager.get_thresholds()})

    @app.post("/api/alerts/thresholds")
    def api_alert_thresholds_update():
        data = request.get_json(silent=True) or {}
        new_thresholds: dict[str, int] = {}
        valid_keys = {"total_objects", "Car", "Bus", "Truck", "Pedestrian", "Motorbike"}
        for key, value in data.items():
            if key in valid_keys:
                try:
                    new_thresholds[key] = max(1, int(value))
                except (TypeError, ValueError):
                    pass
        if not new_thresholds:
            return jsonify({"error": "Không có threshold hợp lệ"}), 400
        alert_manager.update_thresholds(new_thresholds)
        return jsonify({"status": "ok", "thresholds": alert_manager.get_thresholds()})

    # ── Cloud Gallery ────────────────────────────────────────────────────────

    @app.get("/api/cloud/gallery")
    def api_cloud_gallery():
        limit = _parse_int(request.args.get("limit"), default=50, minimum=1, maximum=200)
        try:
            try:
                from db import list_cloud_snapshots
            except ImportError:
                from fisheye_demo.db import list_cloud_snapshots
            snapshots = list_cloud_snapshots(limit=limit, include_deleted=False)
            return jsonify({
                "snapshots": snapshots,
                "total": len(snapshots),
                "ttl_hours": int(__import__("os").getenv("FISHEYE_SNAPSHOT_TTL_HOURS", "6")),
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/cloud/stats")
    def api_cloud_stats():
        try:
            try:
                from cloud_storage import get_bucket_stats, is_enabled
            except ImportError:
                from fisheye_demo.cloud_storage import get_bucket_stats, is_enabled
            return jsonify(get_bucket_stats())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/cloud/cleanup")
    def api_cloud_cleanup():
        try:
            try:
                from cloud_storage import cleanup_expired_snapshots
            except ImportError:
                from fisheye_demo.cloud_storage import cleanup_expired_snapshots
            result = cleanup_expired_snapshots()
            return jsonify({"status": "ok", **result})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Line Counter ─────────────────────────────────────────────────────────

    @app.get("/api/line-counter")
    def api_line_counter():
        if line_counter is None:
            return jsonify({"enabled": False, "message": "Line counter chưa được cấu hình"})
        return jsonify({"enabled": True, **line_counter.get_stats()})

    @app.post("/api/line-counter/reset")
    def api_line_counter_reset():
        if line_counter is None:
            return jsonify({"error": "Line counter chưa được cấu hình"}), 400
        line_counter.reset()
        return jsonify({"status": "ok", "message": "Line counter đã được reset"})

    @app.post("/api/line-counter/config")
    def api_line_counter_config():
        """Cấu hình lại đường kẻ."""
        if line_counter is None:
            return jsonify({"error": "Line counter chưa được cấu hình"}), 400
        data = request.get_json(silent=True) or {}
        try:
            x1 = float(data.get("x1", 0.0))
            y1 = float(data.get("y1", 0.5))
            x2 = float(data.get("x2", 1.0))
            y2 = float(data.get("y2", 0.5))
            line_counter.line_start = (x1, y1)
            line_counter.line_end = (x2, y2)
            line_counter.reset()
            return jsonify({"status": "ok", "line_start": (x1, y1), "line_end": (x2, y2)})
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    # ── Detections from DB ───────────────────────────────────────────────────

    @app.get("/api/detections")
    def api_detections_db():
        limit = _parse_int(request.args.get("limit"), default=50, minimum=1, maximum=200)
        offset = _parse_int(request.args.get("offset"), default=0, minimum=0)
        task = request.args.get("task") or None
        try:
            try:
                from db import list_detections, count_detections
            except ImportError:
                from fisheye_demo.db import list_detections, count_detections
            items = list_detections(limit=limit, offset=offset, task=task)
            total = count_detections(task=task)
            return jsonify({
                "detections": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/detections/<detection_id>")
    def api_detection_detail(detection_id: str):
        try:
            try:
                from db import get_detection
            except ImportError:
                from fisheye_demo.db import get_detection
            item = get_detection(detection_id)
            if item is None:
                return jsonify({"error": "Không tìm thấy detection"}), 404
            return jsonify(item)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Live Sessions ────────────────────────────────────────────────────────

    @app.get("/api/live-sessions")
    def api_live_sessions():
        limit = _parse_int(request.args.get("limit"), default=20, minimum=1, maximum=100)
        try:
            try:
                from db import list_live_sessions
            except ImportError:
                from fisheye_demo.db import list_live_sessions
            sessions = list_live_sessions(limit=limit)
            return jsonify({"sessions": sessions, "total": len(sessions)})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Export CSV ───────────────────────────────────────────────────────────

    @app.get("/api/export/csv")
    def api_export_csv():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        try:
            try:
                from db import get_hourly_traffic_chart, get_class_distribution
            except ImportError:
                from fisheye_demo.db import get_hourly_traffic_chart, get_class_distribution

            chart = get_hourly_traffic_chart(hours=hours)
            class_names = ["Car", "Bus", "Truck", "Pedestrian", "Motorbike"]

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Hour", "Total"] + class_names)

            for bucket in chart:
                counts = bucket.get("counts", {})
                total = sum(counts.values())
                row = [bucket.get("hour", ""), total] + [counts.get(cls, 0) for cls in class_names]
                writer.writerow(row)

            csv_content = output.getvalue()
            filename = f"traffic_stats_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

            return Response(
                csv_content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/export/json")
    def api_export_json():
        hours = _parse_int(request.args.get("hours"), default=24, minimum=1, maximum=168)
        try:
            try:
                from analytics import build_analytics_from_db
            except ImportError:
                from fisheye_demo.analytics import build_analytics_from_db
            data = build_analytics_from_db(hours=hours)
            filename = f"analytics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            return Response(
                json.dumps(data, ensure_ascii=False, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Speed Estimator ──────────────────────────────────────────────────────

    @app.get("/api/speed/stats")
    def api_speed_stats():
        if speed_estimator is None:
            return jsonify({"enabled": False, "message": "Speed estimator chưa được khởi tạo"})
        return jsonify({"enabled": True, **speed_estimator.get_stats()})

    @app.get("/api/speed/current")
    def api_speed_current():
        if speed_estimator is None:
            return jsonify({"enabled": False, "vehicles": []})
        return jsonify({
            "enabled": True,
            "vehicles": speed_estimator.get_current_speeds(),
        })

    @app.post("/api/speed/config")
    def api_speed_config():
        if speed_estimator is None:
            return jsonify({"error": "Speed estimator chưa được khởi tạo"}), 400
        data = request.get_json(silent=True) or {}
        try:
            fps = float(data["fps"]) if "fps" in data else None
            ppm = float(data["pixels_per_meter"]) if "pixels_per_meter" in data else None
            limit = float(data["speed_limit_kmh"]) if "speed_limit_kmh" in data else None
            speed_estimator.update_config(fps=fps, pixels_per_meter=ppm, speed_limit_kmh=limit)
            return jsonify({
                "status": "ok",
                "config": {
                    "fps": speed_estimator.fps,
                    "pixels_per_meter": speed_estimator.pixels_per_meter,
                    "speed_limit_kmh": speed_estimator.speed_limit_kmh,
                },
            })
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/speed/reset")
    def api_speed_reset():
        if speed_estimator is None:
            return jsonify({"error": "Speed estimator chưa được khởi tạo"}), 400
        speed_estimator.reset()
        return jsonify({"status": "ok", "message": "Speed estimator đã được reset"})

    @app.post("/api/speed/detect-image")
    def api_speed_detect_image():
        """
        Chạy speed estimation trên 2 ảnh liên tiếp (frame t-1 và frame t).
        Form fields:
          frame1: ảnh frame trước
          frame2: ảnh frame sau
          fps: FPS giữa 2 frame (mặc định 25)
          pixels_per_meter: hệ số calibration
          speed_limit_kmh: ngưỡng tốc độ
          conf: confidence threshold
          iou: IoU threshold
        """
        from flask import request as req
        frame1_file = req.files.get("frame1")
        frame2_file = req.files.get("frame2")
        if frame1_file is None or frame2_file is None:
            return jsonify({"error": "Cần upload cả frame1 và frame2"}), 400

        try:
            fps_val = float(req.form.get("fps", 25.0))
            ppm_val = float(req.form.get("pixels_per_meter", 8.0))
            limit_val = float(req.form.get("speed_limit_kmh", 60.0))
            conf_val = float(req.form.get("conf", 0.25))
            iou_val = float(req.form.get("iou", 0.45))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": f"Tham số không hợp lệ: {exc}"}), 400

        try:
            from PIL import Image as PILImage
            import io as _io

            img1 = PILImage.open(frame1_file.stream).convert("RGB")
            img2 = PILImage.open(frame2_file.stream).convert("RGB")
            w, h = img1.size

            # Chạy YOLO detect trên cả 2 frame
            model, model_info = registry.load()

            import numpy as np
            import cv2

            def _detect(pil_img):
                arr = np.array(pil_img)
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                result = model.predict(source=bgr, conf=conf_val, iou=iou_val,
                                       verbose=False, device=settings.device)[0]
                dets = []
                names = getattr(getattr(model, "model", None), "names", None) or {}
                NAME_MAP = {
                    "car": "Car", "bus": "Bus", "truck": "Truck",
                    "person": "Pedestrian", "pedestrian": "Pedestrian",
                    "motorcycle": "Motorbike", "motorbike": "Motorbike",
                }
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                        raw = str(names.get(int(box.cls[0]), ""))
                        cls = NAME_MAP.get(raw.lower(), raw)
                        dets.append({
                            "class": cls,
                            "confidence": float(box.conf[0]),
                            "bbox": [x1, y1, x2, y2],
                        })
                return dets, result.plot()

            dets1, ann1 = _detect(img1)
            dets2, ann2 = _detect(img2)

            # Tạo SpeedEstimator tạm thời cho request này
            try:
                from speed_estimator import SpeedEstimator, annotate_speed_on_frame
            except ImportError:
                from fisheye_demo.speed_estimator import SpeedEstimator, annotate_speed_on_frame

            est = SpeedEstimator(fps=fps_val, pixels_per_meter=ppm_val,
                                 fisheye_correction=True, speed_limit_kmh=limit_val)
            est.update(dets1, w, h)          # frame 1 — khởi tạo tracks
            speed_results = est.update(dets2, w, h)  # frame 2 — tính tốc độ

            # Annotate frame 2
            ann2_speed = annotate_speed_on_frame(ann2, speed_results, w, h, speed_limit_kmh=limit_val)
            ann2_rgb = cv2.cvtColor(ann2_speed, cv2.COLOR_BGR2RGB)
            pil_out = PILImage.fromarray(ann2_rgb)

            import base64
            buf = _io.BytesIO()
            pil_out.save(buf, format="JPEG", quality=90)
            b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

            # Lọc kết quả có tốc độ > 0
            valid_speeds = [r for r in speed_results if r["speed_kmh"] > 0]
            overspeed = [r for r in valid_speeds if r["is_overspeed"]]

            return jsonify({
                "status": "ok",
                "annotated_frame2": b64,
                "speed_results": speed_results,
                "summary": {
                    "total_tracked": len(speed_results),
                    "vehicles_with_speed": len(valid_speeds),
                    "overspeed_count": len(overspeed),
                    "avg_speed_kmh": round(
                        sum(r["speed_kmh"] for r in valid_speeds) / len(valid_speeds), 1
                    ) if valid_speeds else 0.0,
                    "max_speed_kmh": round(
                        max((r["speed_kmh"] for r in valid_speeds), default=0.0), 1
                    ),
                    "speed_limit_kmh": limit_val,
                    "fps": fps_val,
                    "pixels_per_meter": ppm_val,
                },
                "model": {
                    "loaded_from_name": model_info.get("loaded_from_name"),
                    "device": model_info.get("device"),
                },
            })
        except Exception as exc:
            logger.error("api_speed_detect_image error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    # ── Congestion Detector ──────────────────────────────────────────────────

    @app.get("/api/congestion/status")
    def api_congestion_status():
        if congestion_detector is None:
            return jsonify({"enabled": False, "message": "Congestion detector chưa được khởi tạo"})
        return jsonify({"enabled": True, **congestion_detector.get_status()})

    @app.get("/api/congestion/rois")
    def api_congestion_rois():
        if congestion_detector is None:
            return jsonify({"enabled": False, "rois": []})
        return jsonify({"enabled": True, "rois": congestion_detector.list_rois()})

    @app.post("/api/congestion/rois")
    def api_congestion_add_roi():
        if congestion_detector is None:
            return jsonify({"error": "Congestion detector chưa được khởi tạo"}), 400
        data = request.get_json(silent=True) or {}
        try:
            name = str(data.get("name", f"roi_{int(datetime.now(timezone.utc).timestamp())}"))
            x1 = float(data.get("x1", 0.0))
            y1 = float(data.get("y1", 0.0))
            x2 = float(data.get("x2", 1.0))
            y2 = float(data.get("y2", 1.0))
            capacity = int(data.get("capacity", 10))
            congestion_detector.add_roi(name, x1, y1, x2, y2, capacity)
            return jsonify({"status": "ok", "name": name, "rois": congestion_detector.list_rois()})
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/congestion/rois/<roi_name>")
    def api_congestion_delete_roi(roi_name: str):
        if congestion_detector is None:
            return jsonify({"error": "Congestion detector chưa được khởi tạo"}), 400
        removed = congestion_detector.remove_roi(roi_name)
        if not removed:
            return jsonify({"error": f"ROI '{roi_name}' không tồn tại"}), 404
        return jsonify({"status": "ok", "removed": roi_name})

    @app.get("/api/congestion/history/<roi_name>")
    def api_congestion_history(roi_name: str):
        if congestion_detector is None:
            return jsonify({"enabled": False, "history": []})
        last_n = _parse_int(request.args.get("n"), default=30, minimum=1, maximum=200)
        history = congestion_detector.get_zone_history(roi_name, last_n=last_n)
        return jsonify({"roi_name": roi_name, "history": history, "count": len(history)})

    @app.post("/api/congestion/reset")
    def api_congestion_reset():
        if congestion_detector is None:
            return jsonify({"error": "Congestion detector chưa được khởi tạo"}), 400
        zone_name = request.get_json(silent=True, force=True) or {}
        zone_name = zone_name.get("zone_name") if isinstance(zone_name, dict) else None
        congestion_detector.reset_stats(zone_name)
        return jsonify({"status": "ok", "message": "Congestion stats đã được reset"})

    @app.post("/api/congestion/detect-image")
    def api_congestion_detect_image():
        """
        Phân tích ùn tắc trên 1 ảnh tĩnh.
        Form fields:
          image: file ảnh
          conf, iou: ngưỡng detect
          capacity: sức chứa tối đa của ROI full_frame
          roi_*: tùy chọn thêm ROI (roi_x1, roi_y1, roi_x2, roi_y2, roi_capacity)
        """
        from flask import request as req
        img_file = req.files.get("image") or req.files.get("file")
        if img_file is None:
            return jsonify({"error": "Cần upload ảnh"}), 400

        try:
            conf_val = float(req.form.get("conf", 0.25))
            iou_val = float(req.form.get("iou", 0.45))
            capacity = int(req.form.get("capacity", 15))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": f"Tham số không hợp lệ: {exc}"}), 400

        try:
            from PIL import Image as PILImage
            import io as _io
            import numpy as np
            import cv2

            img = PILImage.open(img_file.stream).convert("RGB")
            w, h = img.size
            arr = np.array(img)
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            # Detect
            model, model_info = registry.load()
            result = model.predict(source=bgr, conf=conf_val, iou=iou_val,
                                   verbose=False, device=settings.device)[0]

            names = getattr(getattr(model, "model", None), "names", None) or {}
            NAME_MAP = {
                "car": "Car", "bus": "Bus", "truck": "Truck",
                "person": "Pedestrian", "pedestrian": "Pedestrian",
                "motorcycle": "Motorbike", "motorbike": "Motorbike",
            }
            dets = []
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                    raw = str(names.get(int(box.cls[0]), ""))
                    cls = NAME_MAP.get(raw.lower(), raw)
                    dets.append({"class": cls, "confidence": float(box.conf[0]),
                                 "bbox": [x1, y1, x2, y2]})

            # Tạo CongestionDetector tạm thời
            try:
                from congestion_detector import CongestionDetector, annotate_congestion_on_frame
            except ImportError:
                from fisheye_demo.congestion_detector import CongestionDetector, annotate_congestion_on_frame

            det = CongestionDetector()
            det.add_roi("full_frame", 0.0, 0.0, 1.0, 1.0, capacity=capacity)
            det.add_roi("center", 0.25, 0.25, 0.75, 0.75, capacity=max(1, capacity // 2))

            # Thêm ROI tùy chỉnh nếu có
            if req.form.get("roi_x1"):
                try:
                    det.add_roi(
                        "custom",
                        float(req.form.get("roi_x1", 0)),
                        float(req.form.get("roi_y1", 0)),
                        float(req.form.get("roi_x2", 1)),
                        float(req.form.get("roi_y2", 1)),
                        capacity=int(req.form.get("roi_capacity", capacity)),
                    )
                except Exception:
                    pass

            cong_result = det.update(dets, w, h)

            # Annotate
            ann_bgr = result.plot()
            ann_bgr = annotate_congestion_on_frame(ann_bgr, cong_result, w, h)
            ann_rgb = cv2.cvtColor(ann_bgr, cv2.COLOR_BGR2RGB)
            pil_out = PILImage.fromarray(ann_rgb)

            import base64
            buf = _io.BytesIO()
            pil_out.save(buf, format="JPEG", quality=90)
            b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

            return jsonify({
                "status": "ok",
                "annotated_image": b64,
                "congestion": cong_result,
                "total_detections": len(dets),
                "model": {
                    "loaded_from_name": model_info.get("loaded_from_name"),
                    "device": model_info.get("device"),
                },
            })
        except Exception as exc:
            logger.error("api_congestion_detect_image error: %s", exc)
            return jsonify({"error": str(exc)}), 500

    logger.info("Extended routes registered successfully")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_int(value: Any, default: int, minimum: int = 0, maximum: int = 10000) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default
