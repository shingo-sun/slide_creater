"""
Segment Anything Model (SAM) ベースのマスク生成サービス
Claude Vision APIで検出した座標を使用してSAMで高精度マスクを生成
"""
import os
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
import cv2

logger = logging.getLogger(__name__)

# SAMの遅延インポート（インストールされていない場合にフォールバック可能）
SAM_AVAILABLE = False
sam_predictor = None

def _init_sam():
    """SAMモデルを初期化（遅延ロード）"""
    global SAM_AVAILABLE, sam_predictor
    
    if sam_predictor is not None:
        return SAM_AVAILABLE
    
    try:
        import torch
        from segment_anything import sam_model_registry, SamPredictor
        
        # モデルのパス設定
        model_dir = Path(__file__).resolve().parent.parent.parent / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # ViT-B (最軽量モデル) を使用
        model_type = "vit_b"
        checkpoint_path = model_dir / "sam_vit_b_01ec64.pth"
        
        if not checkpoint_path.exists():
            logger.warning(f"SAMモデルが見つかりません: {checkpoint_path}")
            logger.info("モデルをダウンロードしてください: https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth")
            SAM_AVAILABLE = False
            return False
        
        # デバイス設定
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"SAM初期化中... デバイス: {device}")
        
        # モデルロード
        sam = sam_model_registry[model_type](checkpoint=str(checkpoint_path))
        sam.to(device=device)
        
        sam_predictor = SamPredictor(sam)
        SAM_AVAILABLE = True
        logger.info("SAM初期化完了")
        return True
        
    except ImportError as e:
        logger.warning(f"SAMライブラリが利用できません: {e}")
        SAM_AVAILABLE = False
        return False
    except Exception as e:
        logger.error(f"SAM初期化エラー: {e}")
        SAM_AVAILABLE = False
        return False


class SAMMaskGenerator:
    """SAMベースのマスク生成クラス"""
    
    def __init__(self):
        self.initialized = False
        self._cached_image = None
        self._cached_image_hash = None
    
    def is_available(self) -> bool:
        """SAMが利用可能かチェック"""
        if not self.initialized:
            self.initialized = _init_sam()
        return SAM_AVAILABLE
    
    def set_image(self, image: np.ndarray):
        """SAMに画像を設定（一度設定すれば複数のマスク生成で再利用）"""
        if not self.is_available():
            return False
        
        # 画像が変わったかチェック
        image_hash = hash(image.tobytes())
        if self._cached_image_hash == image_hash:
            return True
        
        try:
            # BGRをRGBに変換
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            sam_predictor.set_image(image_rgb)
            self._cached_image_hash = image_hash
            return True
        except Exception as e:
            logger.error(f"SAM set_image エラー: {e}")
            return False
    
    def generate_mask_from_box(
        self, 
        box: Tuple[int, int, int, int],
        multimask: bool = False
    ) -> Optional[np.ndarray]:
        """
        ボックス座標からマスクを生成
        
        Args:
            box: (x1, y1, x2, y2) 形式のバウンディングボックス
            multimask: 複数マスクを生成するか
            
        Returns:
            マスク画像（0-255のグレースケール）
        """
        if not self.is_available():
            return None
        
        try:
            import torch
            
            x1, y1, x2, y2 = box
            input_box = np.array([x1, y1, x2, y2])
            
            masks, scores, logits = sam_predictor.predict(
                point_coords=None,
                point_labels=None,
                box=input_box,
                multimask_output=multimask
            )
            
            # 最もスコアの高いマスクを選択
            best_idx = np.argmax(scores)
            mask = masks[best_idx]
            
            # 0-255にスケール
            mask_uint8 = (mask * 255).astype(np.uint8)
            
            return mask_uint8
            
        except Exception as e:
            logger.error(f"SAMマスク生成エラー: {e}")
            return None
    
    def generate_mask_from_point(
        self, 
        point: Tuple[int, int],
        is_foreground: bool = True,
        multimask: bool = False
    ) -> Optional[np.ndarray]:
        """
        ポイント座標からマスクを生成
        
        Args:
            point: (x, y) 座標
            is_foreground: 前景ポイントか
            multimask: 複数マスクを生成するか
            
        Returns:
            マスク画像（0-255のグレースケール）
        """
        if not self.is_available():
            return None
        
        try:
            import torch
            
            input_point = np.array([[point[0], point[1]]])
            input_label = np.array([1 if is_foreground else 0])
            
            masks, scores, logits = sam_predictor.predict(
                point_coords=input_point,
                point_labels=input_label,
                multimask_output=multimask
            )
            
            best_idx = np.argmax(scores)
            mask = masks[best_idx]
            mask_uint8 = (mask * 255).astype(np.uint8)
            
            return mask_uint8
            
        except Exception as e:
            logger.error(f"SAMマスク生成エラー: {e}")
            return None
    
    def generate_mask_with_refinement(
        self,
        image: np.ndarray,
        box: Tuple[int, int, int, int],
        element_type: str = "image"
    ) -> np.ndarray:
        """
        SAMマスク + 後処理で高精度マスクを生成
        SAMが利用できない場合はフォールバック
        
        Args:
            image: 入力画像（BGR）
            box: (x1, y1, x2, y2) 形式のバウンディングボックス
            element_type: 要素タイプ
            
        Returns:
            マスク画像（0-255のグレースケール）
        """
        x1, y1, x2, y2 = box
        height, width = image.shape[:2]
        
        # 切り出し領域を計算
        crop_x1 = max(0, x1)
        crop_y1 = max(0, y1)
        crop_x2 = min(width, x2)
        crop_y2 = min(height, y2)
        
        roi = image[crop_y1:crop_y2, crop_x1:crop_x2]
        
        if roi.size == 0:
            return np.zeros((crop_y2 - crop_y1, crop_x2 - crop_x1), dtype=np.uint8)
        
        # SAMが利用可能な場合
        if self.is_available():
            # 全体画像を設定
            if self.set_image(image):
                # ボックスからマスク生成
                sam_mask = self.generate_mask_from_box((x1, y1, x2, y2))
                
                if sam_mask is not None:
                    # マスクを切り出し領域に合わせる
                    mask_roi = sam_mask[crop_y1:crop_y2, crop_x1:crop_x2]
                    
                    # 後処理
                    mask_refined = self._refine_mask(mask_roi, element_type)
                    return mask_refined
        
        # フォールバック: シンプルな背景除去
        return self._fallback_mask_generation(roi, element_type)
    
    def _refine_mask(self, mask: np.ndarray, element_type: str) -> np.ndarray:
        """マスクの後処理"""
        # モルフォロジー処理
        kernel = np.ones((3, 3), np.uint8)
        
        # 小さな穴を埋める
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        # 小さなノイズを除去
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # エッジを滑らかに
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        
        # 閾値処理で2値化
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        
        return mask
    
    def _fallback_mask_generation(self, roi: np.ndarray, element_type: str) -> np.ndarray:
        """SAMが使えない場合のフォールバックマスク生成"""
        if roi.size == 0:
            return np.zeros((1, 1), dtype=np.uint8)
        
        height, width = roi.shape[:2]
        
        # 背景色を推定（四隅からサンプリング）
        corners = [
            roi[0, 0],
            roi[0, -1] if width > 1 else roi[0, 0],
            roi[-1, 0] if height > 1 else roi[0, 0],
            roi[-1, -1] if height > 1 and width > 1 else roi[0, 0]
        ]
        bg_color = np.median(corners, axis=0).astype(np.uint8)
        
        # 背景色との差分でマスク生成
        diff = np.abs(roi.astype(np.float32) - bg_color.astype(np.float32))
        diff_gray = np.mean(diff, axis=2)
        
        # 閾値処理
        threshold = 15
        mask = np.where(diff_gray > threshold, 255, 0).astype(np.uint8)
        
        # モルフォロジー処理でノイズ除去
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # エッジを滑らかに
        mask = cv2.GaussianBlur(mask, (3, 3), 0)
        
        return mask


# シングルトンインスタンス
sam_mask_generator = SAMMaskGenerator()
