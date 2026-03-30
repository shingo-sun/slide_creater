"""
図形切り抜きサービス
元画像から図形領域を切り抜いて画像として保存
"""
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import os
import uuid
import logging

logger = logging.getLogger(__name__)


class ShapeCropper:
    """図形を元画像から切り抜いて画像化するサービス"""
    
    def __init__(self, output_dir: str = "outputs/cropped"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def crop_shapes_from_image(
        self,
        image_path: str,
        shape_objects: List[Dict[str, Any]],
        file_id: str
    ) -> List[Dict[str, Any]]:
        """
        元画像から図形領域を切り抜いて画像として保存
        
        Args:
            image_path: 元画像パス
            shape_objects: 図形オブジェクトのリスト
            file_id: ファイルID
            
        Returns:
            画像パスが追加された図形オブジェクトのリスト
        """
        # 元画像を読み込み
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"画像を読み込めません: {image_path}")
            return shape_objects
        
        height, width = image.shape[:2]
        cropped_shapes = []
        
        for i, shape in enumerate(shape_objects):
            try:
                # 座標を取得（画像座標系）
                x = int(shape.get("x", 0))
                y = int(shape.get("y", 0))
                w = int(shape.get("width", 100))
                h = int(shape.get("height", 100))
                
                # 境界チェック
                x = max(0, x)
                y = max(0, y)
                w = min(w, width - x)
                h = min(h, height - y)
                
                if w <= 0 or h <= 0:
                    logger.warning(f"無効な図形サイズ: {shape}")
                    continue
                
                # 切り抜き（余白を少し追加）
                margin = 2
                x1 = max(0, x - margin)
                y1 = max(0, y - margin)
                x2 = min(width, x + w + margin)
                y2 = min(height, y + h + margin)
                
                cropped = image[y1:y2, x1:x2]
                
                # PNG形式で保存（透明度対応）
                crop_filename = f"{file_id}_shape_{i}_{uuid.uuid4().hex[:6]}.png"
                crop_path = self.output_dir / crop_filename
                
                # BGRA形式に変換（透明度チャンネル追加）
                if cropped.shape[2] == 3:
                    cropped_rgba = cv2.cvtColor(cropped, cv2.COLOR_BGR2BGRA)
                else:
                    cropped_rgba = cropped
                
                cv2.imwrite(str(crop_path), cropped_rgba)
                
                # 元の座標を保持しつつ画像パスを追加
                cropped_shape = shape.copy()
                cropped_shape["image_path"] = str(crop_path)
                cropped_shape["cropped_from_original"] = True
                # 座標は元のまま（切り抜きマージン影響を考慮）
                cropped_shape["x"] = x1
                cropped_shape["y"] = y1
                cropped_shape["width"] = x2 - x1
                cropped_shape["height"] = y2 - y1
                
                cropped_shapes.append(cropped_shape)
                logger.debug(f"図形を切り抜きました: {crop_path}")
                
            except Exception as e:
                logger.error(f"図形切り抜きエラー: {e}")
                # エラー時は元の図形データを保持
                cropped_shapes.append(shape)
        
        return cropped_shapes
    
    def crop_non_text_regions(
        self,
        image_path: str,
        text_objects: List[Dict[str, Any]],
        file_id: str,
        min_region_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        テキスト以外の領域を検出して切り抜き
        
        Args:
            image_path: 元画像パス
            text_objects: テキストオブジェクトのリスト（除外領域）
            file_id: ファイルID
            min_region_size: 最小領域サイズ
            
        Returns:
            切り抜いた図形リスト, 背景画像パス
        """
        image = cv2.imread(image_path)
        if image is None:
            return [], ""
        
        height, width = image.shape[:2]
        
        # テキスト領域のマスクを作成
        text_mask = np.zeros((height, width), dtype=np.uint8)
        for text in text_objects:
            x = int(text.get("x", 0))
            y = int(text.get("y", 0))
            w = int(text.get("width", 0))
            h = int(text.get("height", 0))
            
            # テキスト領域を白（除外）
            cv2.rectangle(text_mask, (x, y), (x + w, y + h), 255, -1)
        
        # テキスト以外の領域を検出
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150)
        
        # テキスト領域を除外
        edges = cv2.bitwise_and(edges, cv2.bitwise_not(text_mask))
        
        # 輪郭検出
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 図形領域を抽出
        shape_regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_region_size * min_region_size:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # テキスト領域と重ならないか確認
            overlap_ratio = self._calculate_overlap_with_mask(
                text_mask, x, y, w, h
            )
            
            if overlap_ratio < 0.3:  # 30%未満の重なりなら図形として扱う
                shape_regions.append({
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "object_type": "cropped_shape",
                    "z_index": 5
                })
        
        # 検出した図形領域を切り抜き
        cropped_shapes = self.crop_shapes_from_image(
            image_path, shape_regions, file_id
        )
        
        # 背景画像を保存（図形・テキストを除去した状態）
        background_path = str(self.output_dir / f"{file_id}_background.png")
        # 簡易的に元画像をそのまま背景として使用
        cv2.imwrite(background_path, image)
        
        return cropped_shapes, background_path
    
    def _calculate_overlap_with_mask(
        self,
        mask: np.ndarray,
        x: int, y: int, w: int, h: int
    ) -> float:
        """マスクとの重なり率を計算"""
        if w <= 0 or h <= 0:
            return 0.0
        
        region = mask[y:y+h, x:x+w]
        overlap_pixels = np.sum(region > 0)
        total_pixels = w * h
        
        return overlap_pixels / total_pixels if total_pixels > 0 else 0.0
    
    def create_hybrid_slide_data(
        self,
        image_path: str,
        analysis_result: Dict[str, Any],
        file_id: str
    ) -> Dict[str, Any]:
        """
        ハイブリッドスライドデータを作成
        - 図形: 元画像から切り抜いた画像として配置
        - テキスト: 編集可能なテキストボックスとして配置
        
        Args:
            image_path: 元画像パス
            analysis_result: 解析結果
            file_id: ファイルID
            
        Returns:
            ハイブリッド構成の解析結果
        """
        result = analysis_result.copy()
        
        # 図形オブジェクトを画像として切り抜き
        shape_objects = result.get("shape_objects", [])
        icon_objects = result.get("icon_objects", [])
        
        # 図形とアイコンを統合して切り抜き
        all_shapes = shape_objects + icon_objects
        
        if all_shapes:
            cropped_shapes = self.crop_shapes_from_image(
                image_path, all_shapes, file_id
            )
            # shape_objectsを切り抜き画像に置換
            result["shape_objects"] = []
            result["icon_objects"] = []
            result["cropped_images"] = cropped_shapes
        else:
            result["cropped_images"] = []
        
        # テキストオブジェクトはそのまま編集可能として保持
        # （変更不要）
        
        # モードをハイブリッドに設定
        result["mode"] = "hybrid"
        result["hybrid_config"] = {
            "shapes_as_images": True,
            "text_editable": True,
            "preserve_positions": True
        }
        
        logger.info(
            f"ハイブリッドデータ作成完了: "
            f"切り抜き画像 {len(result.get('cropped_images', []))}個, "
            f"テキスト {len(result.get('text_objects', []))}個"
        )
        
        return result


# シングルトンインスタンス
shape_cropper = ShapeCropper()
