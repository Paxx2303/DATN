#!/usr/bin/env python3
"""
test_incident_scenarios.py — Test cụ thể các tình huống phát hiện sự cố
"""

import os
import sys
import time
import numpy as np
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from incident_detector import (
        Incident_Detector,
        INCIDENT_COLLISION,
        INCIDENT_STOPPED_VEHICLE,
        INCIDENT_WRONG_WAY,
        INCIDENT_FALLEN_OBJECT,
        INCIDENT_PEDESTRIAN_DANGER,
        INCIDENT_UNUSUAL_PATTERN,
    )
    import db
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def test_collision_scenario():
    """Test tình huống va chạm giữa 2 xe."""
    print("=== Testing Collision Scenario ===")
    
    detector = Incident_Detector(fps=10.0, pixels_per_meter=10.0)
    
    # Setup ROI cho đường
    detector.roi_manager.set_roi(
        "main_road", 0.0, 0.0, 1.0, 1.0,
        expected_direction=90.0,
        is_dangerous_zone=True
    )
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    # Tạo 2 xe di chuyển về phía nhau - closer initial positions
    car1_x, car2_x = 200, 300  # Start closer together
    
    print("Simulating two cars approaching each other...")
    
    for frame_num in range(20):
        # Xe 1 di chuyển sang phải, xe 2 di chuyển sang trái
        if frame_num < 12:  # Di chuyển bình thường
            car1_x += 8  # Slower movement
            car2_x -= 8
        else:  # Va chạm - dừng đột ngột
            pass  # Không di chuyển nữa
        
        detections = [
            {
                "class": "Car",
                "confidence": 0.9,
                "bbox": [car1_x, 200, car1_x + 80, 250]
            },
            {
                "class": "Car", 
                "confidence": 0.85,
                "bbox": [car2_x, 210, car2_x + 80, 260]
            }
        ]
        
        incidents = detector.process_frame(
            detections=detections,
            frame_rgb=mock_frame,
            camera_id="collision_test",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        # Debug tracking info
        tracks = detector.object_tracker.tracks
        if len(tracks) >= 2:
            track_list = list(tracks.values())
            t1, t2 = track_list[0], track_list[1]
            distance_px = abs(t1["cx"] * frame_w - t2["cx"] * frame_w)
            distance_m = distance_px / detector.pixels_per_meter
            print(f"Frame {frame_num+1}: Cars at x={car1_x}, x={car2_x}, distance={distance_px:.0f}px ({distance_m:.1f}m)")
            print(f"  Track speeds: {t1['speed']:.1f} km/h, {t2['speed']:.1f} km/h")
            print(f"  Track IDs: {t1['id']}, {t2['id']}")
        else:
            print(f"Frame {frame_num+1}: Cars at x={car1_x}, x={car2_x}, tracks={len(tracks)}")
        
        if incidents:
            for inc in incidents:
                print(f"  🚨 {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                if inc['type'] == INCIDENT_COLLISION:
                    print("  ✓ COLLISION DETECTED!")
                    return True
    
    print("  ❌ No collision detected")
    return False

def test_stopped_vehicle_scenario():
    """Test tình huống xe dừng lâu."""
    print("\n=== Testing Stopped Vehicle Scenario ===")
    
    detector = Incident_Detector(fps=10.0, pixels_per_meter=10.0)
    
    # Setup ROI
    detector.roi_manager.set_roi(
        "active_lane", 0.0, 0.0, 1.0, 1.0,
        is_dangerous_zone=True
    )
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    print("Simulating a vehicle moving then stopping...")
    
    # Xe di chuyển rồi dừng lại
    car_x = 200
    
    for frame_num in range(50):  # 5 giây với 10 FPS
        # First 10 frames: car is moving
        if frame_num < 10:
            car_x += 10  # Moving
        # After frame 10: car stops
        
        detections = [
            {
                "class": "Car",
                "confidence": 0.9,
                "bbox": [car_x, 200, car_x + 80, 250]
            }
        ]
        
        incidents = detector.process_frame(
            detections=detections,
            frame_rgb=mock_frame,
            camera_id="stopped_test",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        # Debug tracking info
        tracks = detector.object_tracker.tracks
        if tracks:
            track = list(tracks.values())[0]
            if frame_num % 10 == 0:
                stopped_time = max(0, (frame_num - 10) / 10.0)
                print(f"Frame {frame_num+1}: Car at x={car_x}, stopped for {stopped_time:.1f} seconds")
                print(f"  Track speed: {track['speed']:.1f} km/h, ID: {track['id']}")
        
        if incidents:
            for inc in incidents:
                print(f"  🚨 {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                if inc['type'] == INCIDENT_STOPPED_VEHICLE:
                    print("  ✓ STOPPED VEHICLE DETECTED!")
                    return True
    
    print("  ❌ No stopped vehicle detected")
    return False

def test_wrong_way_scenario():
    """Test tình huống xe đi ngược chiều."""
    print("\n=== Testing Wrong Way Scenario ===")
    
    detector = Incident_Detector(fps=10.0, pixels_per_meter=10.0)
    
    # Setup ROI với hướng mong muốn
    detector.roi_manager.set_roi(
        "highway_lane", 0.0, 0.0, 1.0, 1.0,
        expected_direction=90.0,  # Hướng Đông (sang phải)
        is_dangerous_zone=True
    )
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    print("Simulating a vehicle driving wrong way...")
    
    # Xe di chuyển ngược chiều (từ phải sang trái)
    wrong_way_car_x = 500
    
    for frame_num in range(40):
        # Di chuyển ngược chiều
        wrong_way_car_x -= 20  # Di chuyển sang trái (ngược với expected_direction=90°)
        
        if wrong_way_car_x < 0:
            wrong_way_car_x = 500  # Reset
        
        detections = [
            {
                "class": "Car",
                "confidence": 0.9,
                "bbox": [wrong_way_car_x, 200, wrong_way_car_x + 80, 250]
            }
        ]
        
        incidents = detector.process_frame(
            detections=detections,
            frame_rgb=mock_frame,
            camera_id="wrong_way_test",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        # Debug tracking info
        tracks = detector.object_tracker.tracks
        if tracks and frame_num % 10 == 0:
            track = list(tracks.values())[0]
            print(f"Frame {frame_num+1}: Car at x={wrong_way_car_x} (moving left)")
            print(f"  Track speed: {track['speed']:.1f} km/h, heading: {track['heading']:.1f}°")
            print(f"  Expected direction: 90°, deviation: {abs(track['heading'] - 90.0):.1f}°")
        
        if incidents:
            for inc in incidents:
                print(f"  🚨 {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                if inc['type'] == INCIDENT_WRONG_WAY:
                    print("  ✓ WRONG WAY DETECTED!")
                    return True
    
    print("  ❌ No wrong way detected")
    return False

def test_pedestrian_danger_scenario():
    """Test tình huống người đi bộ trong vùng nguy hiểm."""
    print("\n=== Testing Pedestrian Danger Scenario ===")
    
    detector = Incident_Detector(fps=10.0, pixels_per_meter=10.0)
    
    # Setup ROI
    detector.roi_manager.set_roi(
        "active_lane", 0.0, 0.0, 1.0, 1.0,
        is_dangerous_zone=True
    )
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    print("Simulating pedestrian in dangerous zone near moving vehicle...")
    
    for frame_num in range(30):
        detections = [
            {
                "class": "Pedestrian",
                "confidence": 0.8,
                "bbox": [300, 200, 330, 280]  # Người đi bộ đứng yên
            },
            {
                "class": "Car",
                "confidence": 0.9,
                "bbox": [200 + frame_num * 5, 190, 280 + frame_num * 5, 240]  # Xe tiến gần
            }
        ]
        
        incidents = detector.process_frame(
            detections=detections,
            frame_rgb=mock_frame,
            camera_id="pedestrian_test",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        if frame_num % 10 == 0:
            car_x = 200 + frame_num * 5
            distance = abs(300 - car_x)
            print(f"Frame {frame_num+1}: Car at x={car_x}, distance to pedestrian={distance}px")
        
        if incidents:
            for inc in incidents:
                print(f"  🚨 {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                if inc['type'] == INCIDENT_PEDESTRIAN_DANGER:
                    print("  ✓ PEDESTRIAN DANGER DETECTED!")
                    return True
    
    print("  ❌ No pedestrian danger detected")
    return False

def test_fallen_object_scenario():
    """Test tình huống vật thể rơi trên đường."""
    print("\n=== Testing Fallen Object Scenario ===")
    
    detector = Incident_Detector(fps=10.0, pixels_per_meter=10.0)
    
    # Setup ROI
    detector.roi_manager.set_roi(
        "roadway", 0.0, 0.0, 1.0, 1.0,
        is_dangerous_zone=True
    )
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    print("Simulating fallen object on roadway...")
    
    for frame_num in range(30):
        detections = [
            {
                "class": "debris",  # Không phải xe hoặc người
                "confidence": 0.7,
                "bbox": [350, 220, 400, 250]  # Vật thể đứng yên
            }
        ]
        
        incidents = detector.process_frame(
            detections=detections,
            frame_rgb=mock_frame,
            camera_id="debris_test",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        if frame_num % 10 == 0:
            print(f"Frame {frame_num+1}: Object stationary for {frame_num/10:.1f} seconds")
        
        if incidents:
            for inc in incidents:
                print(f"  🚨 {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                if inc['type'] == INCIDENT_FALLEN_OBJECT:
                    print("  ✓ FALLEN OBJECT DETECTED!")
                    return True
    
    print("  ❌ No fallen object detected")
    return False

def main():
    """Chạy tất cả các test scenario."""
    print("Starting Incident Detection Scenario Tests")
    print("=" * 60)
    
    # Initialize database
    db.init_db()
    
    results = {}
    
    # Test các tình huống
    results['collision'] = test_collision_scenario()
    results['stopped_vehicle'] = test_stopped_vehicle_scenario()
    results['wrong_way'] = test_wrong_way_scenario()
    results['pedestrian_danger'] = test_pedestrian_danger_scenario()
    results['fallen_object'] = test_fallen_object_scenario()
    
    # Tổng kết
    print("\n" + "=" * 60)
    print("SCENARIO TEST RESULTS:")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    for scenario, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{scenario.replace('_', ' ').title():<20} {status}")
    
    print("-" * 60)
    print(f"Total: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  Some tests failed. Check configuration and thresholds.")
    
    # Hiển thị thống kê incidents trong DB
    try:
        stats = db.get_incident_stats(hours=1)
        print(f"\nDatabase Stats: {stats}")
    except Exception as e:
        print(f"Could not get database stats: {e}")

if __name__ == "__main__":
    main()