#!/usr/bin/env python3
"""
Quick test script to debug bbox coordinates
"""
from PIL import Image
from services.inference import run_inference
from utils.helpers import draw_detections_on_image
import sys

def test_bbox():
    # Create a simple test image
    img = Image.new('RGB', (300, 168), color='blue')
    
    print("Testing inference...")
    result = run_inference(img, model_key="traffic", conf=0.25, iou=0.45)
    
    print(f"Image size: {img.width}x{img.height}")
    print(f"Detections: {len(result['detections'])}")
    
    for i, det in enumerate(result['detections']):
        print(f"  {i}: {det}")
    
    if result['detections']:
        annotated = draw_detections_on_image(img, result['detections'])
        annotated.save('test_output.jpg')
        print("Saved test_output.jpg")
    
if __name__ == "__main__":
    test_bbox()