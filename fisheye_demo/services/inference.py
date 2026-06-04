"""
services/inference.py — Single Image Inference Wrapper

Chuẩn hóa output của YOLO thành dict để các module khác dùng thống nhất.
"""

import logging
import numpy as np
from PIL import Image
from typing import Any, Optional
from services.model_registry import load_model
from config import Config

logger = logging.getLogger(__name__)


def run_inference(
    image: Image.Image,
    model_key: Optional[str] = None,
    conf: float = None,
    iou: float = None,
    device: Optional[str] = None,
    filter_classes: Optional[set] = None,
) -> dict[str, Any]:
    """
    Chạy YOLO inference trên ảnh PIL.
    
    Returns
    -------
    dict:
        detections  : list[dict] — mỗi item: {class_name, confidence, bbox: [x1,y1,x2,y2]}
        counts      : dict[str, int] — đếm theo class
        image_width : int
        image_height: int
        model_key   : str
    """
    conf   = conf or Config.DEFAULT_CONF
    iou    = iou or Config.DEFAULT_IOU
    device = device or Config.DEFAULT_DEVICE
    filter_classes = filter_classes or Config.VEHICLE_CLASSES
    
    model = load_model(model_key, device)
    
    # YOLO accept PIL Image trực tiếp
    results = model.predict(
        source=image,
        conf=conf,
        iou=iou,
        device=device,
        verbose=False,
    )
    
    detections = []
    counts: dict[str, int] = {}
    
    if results and results[0].boxes is not None:
        boxes = results[0].boxes
        for box in boxes:
            cls_id   = int(box.cls.item())
            cls_name = model.names[cls_id]
            
            # Filter: chỉ giữ vehicle classes
            if filter_classes and cls_name not in filter_classes:
                continue
            
            conf_val = float(box.conf.item())
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            
            display_name = Config.VEHICLE_NAME_MAP.get(cls_name, cls_name)
            
            detections.append({
                "class_name":  display_name,
                "class_raw":   cls_name,
                "confidence":  round(conf_val, 3),
                "bbox":        [x1, y1, x2, y2],
                "center":      [(x1+x2)//2, (y1+y2)//2],
            })
            counts[display_name] = counts.get(display_name, 0) + 1
    
    return {
        "detections":   detections,
        "counts":       counts,
        "total":        len(detections),
        "image_width":  image.width,
        "image_height": image.height,
        "model_key":    model_key or Config.DEFAULT_MODEL_KEY,
    }
