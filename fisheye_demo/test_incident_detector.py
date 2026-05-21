#!/usr/bin/env python3
"""
test_incident_detector.py — Test script để kiểm tra tính năng Incident Detection
"""

import os
import sys
import time
import json
import numpy as np
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from incident_detector import (
        Incident_Detector,
        Config_Parser,
        Config_Pretty_Printer,
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

def test_config_parser():
    """Test config parser và pretty printer."""
    print("=== Testing Config Parser ===")
    
    # Test valid config
    valid_config = {
        "collision": {
            "confidence_threshold": 0.75,
            "duration_seconds": 2.0
        },
        "stopped_vehicle": {
            "confidence_threshold": 0.65,
            "duration_seconds": 30.0
        }
    }
    
    config_str = json.dumps(valid_config)
    try:
        parsed = Config_Parser.parse(config_str)
        print("✓ Valid config parsed successfully")
        
        pretty = Config_Pretty_Printer.print_config(parsed)
        reparsed = Config_Parser.parse(pretty)
        
        if parsed == reparsed:
            print("✓ Round-trip test passed")
        else:
            print("✗ Round-trip test failed")
            
    except Exception as e:
        print(f"✗ Config parser test failed: {e}")
    
    # Test invalid config
    try:
        invalid_config = '{"collision": {"confidence_threshold": 1.5}}'  # Invalid threshold > 1.0
        Config_Parser.parse(invalid_config)
        print("✗ Should have failed on invalid threshold")
    except ValueError:
        print("✓ Correctly rejected invalid threshold")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

def create_mock_detections():
    """Tạo mock detections để test."""
    return [
        {
            "class": "Car",
            "confidence": 0.85,
            "bbox": [100, 100, 200, 150]  # x1, y1, x2, y2
        },
        {
            "class": "Car", 
            "confidence": 0.90,
            "bbox": [300, 120, 400, 170]
        },
        {
            "class": "Pedestrian",
            "confidence": 0.75,
            "bbox": [150, 200, 180, 280]
        },
        {
            "class": "Motorbike",
            "confidence": 0.80,
            "bbox": [250, 180, 290, 220]
        }
    ]

def test_incident_detector():
    """Test core incident detector functionality."""
    print("\n=== Testing Incident Detector ===")
    
    # Initialize database
    try:
        db.init_db()
        print("✓ Database initialized")
    except Exception as e:
        print(f"✗ Database init failed: {e}")
        return
    
    # Create detector instance
    detector = Incident_Detector(
        fps=10.0,
        pixels_per_meter=8.0,
        results_dir="test_results"
    )
    
    # Setup ROIs for testing
    detector.roi_manager.set_roi(
        "test_lane", 0.0, 0.0, 1.0, 1.0,
        expected_direction=90.0,
        is_dangerous_zone=True
    )
    
    print("✓ Incident detector initialized")
    
    # Create mock frame
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    # Test multiple frames to simulate movement
    print("Processing test frames...")
    
    for i in range(5):
        detections = create_mock_detections()
        
        # Simulate some movement by adjusting bbox positions
        for det in detections:
            det["bbox"][0] += i * 10  # Move objects to the right
            det["bbox"][2] += i * 10
        
        try:
            incidents = detector.process_frame(
                detections=detections,
                frame_rgb=mock_frame,
                camera_id="test_cam_01",
                frame_w=frame_w,
                frame_h=frame_h
            )
            
            print(f"Frame {i+1}: {len(incidents)} incidents detected")
            for inc in incidents:
                print(f"  - {inc['type']}: {inc['description']} (confidence: {inc['confidence']:.2f})")
                
        except Exception as e:
            print(f"✗ Frame processing failed: {e}")
            import traceback
            traceback.print_exc()
            return
    
    print("✓ Frame processing completed")

def test_database_functions():
    """Test database incident functions."""
    print("\n=== Testing Database Functions ===")
    
    try:
        # Test incident insertion
        test_incident = {
            "id": f"test_inc_{int(time.time())}",
            "type": INCIDENT_COLLISION,
            "severity": "severe",
            "confidence": 0.85,
            "camera_id": "test_cam",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"cx": 0.5, "cy": 0.5},
            "state": "active",
            "duration": 0.0,
            "metadata": {"test": True},
            "description": "Test collision incident"
        }
        
        db.insert_incident(test_incident)
        print("✓ Incident inserted successfully")
        
        # Test incident retrieval
        retrieved = db.get_incident(test_incident["id"])
        if retrieved:
            print("✓ Incident retrieved successfully")
            print(f"  Retrieved: {retrieved['type']} - {retrieved.get('description', 'No description')}")
        else:
            print("✗ Failed to retrieve incident")
        
        # Test incident listing
        incidents = db.list_incidents(limit=10)
        print(f"✓ Listed {len(incidents)} incidents")
        
        # Test incident stats
        stats = db.get_incident_stats(hours=24)
        print(f"✓ Incident stats: {stats}")
        
        # Test config functions
        test_config = {
            INCIDENT_COLLISION: {"confidence_threshold": 0.75},
            INCIDENT_STOPPED_VEHICLE: {"duration_seconds": 30.0}
        }
        
        db.insert_incident_config("test_cam", test_config)
        print("✓ Incident config inserted")
        
        retrieved_config = db.get_incident_config("test_cam")
        if retrieved_config:
            print("✓ Incident config retrieved")
        else:
            print("✗ Failed to retrieve incident config")
            
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        import traceback
        traceback.print_exc()

def test_specific_incident_types():
    """Test specific incident detection scenarios."""
    print("\n=== Testing Specific Incident Types ===")
    
    detector = Incident_Detector()
    
    # Test collision scenario - two cars very close with sudden speed drop
    print("Testing collision detection...")
    collision_detections = [
        {"class": "Car", "confidence": 0.9, "bbox": [100, 100, 150, 140]},
        {"class": "Car", "confidence": 0.85, "bbox": [145, 105, 195, 145]}  # Very close
    ]
    
    frame_w, frame_h = 960, 540
    mock_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
    
    # Process several frames to build up tracking history
    for i in range(10):
        # Simulate cars moving fast then suddenly stopping
        speed_factor = 1.0 if i < 7 else 0.1  # Sudden stop at frame 7
        
        for det in collision_detections:
            det["bbox"][0] += int(20 * speed_factor)  # Simulate movement
            det["bbox"][2] += int(20 * speed_factor)
        
        incidents = detector.process_frame(
            detections=collision_detections,
            frame_rgb=mock_frame,
            camera_id="test_collision",
            frame_w=frame_w,
            frame_h=frame_h
        )
        
        if incidents:
            print(f"  Frame {i+1}: Detected {len(incidents)} incidents")
            for inc in incidents:
                if inc['type'] == INCIDENT_COLLISION:
                    print(f"    ✓ Collision detected! Confidence: {inc['confidence']:.2f}")
    
    print("Collision test completed")

def main():
    """Run all tests."""
    print("Starting Incident Detection System Tests")
    print("=" * 50)
    
    # Test 1: Config Parser
    test_config_parser()
    
    # Test 2: Database Functions  
    test_database_functions()
    
    # Test 3: Core Incident Detector
    test_incident_detector()
    
    # Test 4: Specific Incident Types
    test_specific_incident_types()
    
    print("\n" + "=" * 50)
    print("All tests completed!")

if __name__ == "__main__":
    main()