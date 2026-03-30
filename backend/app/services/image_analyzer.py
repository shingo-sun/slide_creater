"""
画像解析サービス
前処理（傾き補正、ノイズ除去、解像度補正等）を実施
"""
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Tuple, Dict, Any

from app.models.slide_objects import ImageInfo


class ImageAnalyzer:
    """画像前処理・解析クラス"""
    
    def __init__(self):
        self.target_dpi = 150  # 処理用DPI
        
    def preprocess(self, image_path: str) -> Tuple[np.ndarray, ImageInfo]:
        """
        画像前処理パイプライン
        
        Args:
            image_path: 入力画像パス
            
        Returns:
            処理済み画像(numpy配列)と画像情報
        """
        # 画像読み込み
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"画像を読み込めません: {image_path}")
        
        # 元画像情報を取得
        height, width = image.shape[:2]
        channels = image.shape[2] if len(image.shape) > 2 else 1
        
        # PILで追加情報取得
        pil_image = Image.open(image_path)
        format_str = pil_image.format or Path(image_path).suffix[1:].upper()
        dpi = pil_image.info.get('dpi', (72, 72))
        dpi_value = int(dpi[0]) if isinstance(dpi, tuple) else int(dpi)
        
        image_info = ImageInfo(
            width=width,
            height=height,
            channels=channels,
            format=format_str,
            dpi=dpi_value
        )
        
        # 前処理パイプライン
        processed = image.copy()
        
        # 1. グレースケール変換（傾き検出用）
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        
        # 2. 傾き補正
        processed = self._correct_skew(processed, gray)
        
        # 3. ノイズ除去（軽度）
        processed = self._denoise(processed)
        
        # 4. コントラスト調整
        processed = self._adjust_contrast(processed)
        
        return processed, image_info
    
    def _correct_skew(self, image: np.ndarray, gray: np.ndarray) -> np.ndarray:
        """
        傾き補正
        微小な傾きのみ補正（大きな傾きは意図的な場合があるため）
        """
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # ハフ変換で直線検出
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        
        if lines is None:
            return image
        
        # 角度の中央値を計算
        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            # 垂直・水平に近い線のみ考慮
            if abs(angle) < 10:
                angles.append(angle)
        
        if not angles:
            return image
        
        median_angle = np.median(angles)
        
        # 微小傾きのみ補正（±5度以内）
        if abs(median_angle) > 5:
            return image
        
        if abs(median_angle) < 0.5:
            return image
        
        # 回転補正
        height, width = image.shape[:2]
        center = (width // 2, height // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            image, rotation_matrix, (width, height),
            borderMode=cv2.BORDER_REPLICATE
        )
        
        return rotated
    
    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """ノイズ除去（軽度）"""
        # 軽いガウシアンブラー
        return cv2.GaussianBlur(image, (3, 3), 0)
    
    def _adjust_contrast(self, image: np.ndarray) -> np.ndarray:
        """コントラスト調整"""
        # LAB色空間でコントラスト調整
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # CLAHEでコントラスト向上
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def extract_background_color(self, image: np.ndarray) -> Tuple[int, int, int]:
        """背景色を推定"""
        # 画像の端からサンプリング
        border_pixels = []
        height, width = image.shape[:2]
        
        # 上下左右の端から10ピクセル
        border_pixels.extend(image[0:10, :].reshape(-1, 3).tolist())
        border_pixels.extend(image[-10:, :].reshape(-1, 3).tolist())
        border_pixels.extend(image[:, 0:10].reshape(-1, 3).tolist())
        border_pixels.extend(image[:, -10:].reshape(-1, 3).tolist())
        
        # 最頻値を背景色とする
        border_pixels = np.array(border_pixels)
        # 色をビニングして最頻値を求める
        bins = 16
        quantized = (border_pixels // bins) * bins
        unique, counts = np.unique(quantized, axis=0, return_counts=True)
        bg_color = unique[np.argmax(counts)]
        
        return tuple(bg_color.tolist())
    
    def separate_foreground_background(
        self, image: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """前景と背景を分離"""
        bg_color = self.extract_background_color(image)
        
        # 背景色との差分でマスク作成
        diff = np.abs(image.astype(np.float32) - np.array(bg_color))
        diff_gray = np.mean(diff, axis=2)
        
        # 閾値でマスク生成
        _, mask = cv2.threshold(diff_gray.astype(np.uint8), 20, 255, cv2.THRESH_BINARY)
        
        # モルフォロジー処理でノイズ除去
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 前景・背景分離
        foreground = cv2.bitwise_and(image, image, mask=mask)
        background = cv2.bitwise_and(image, image, mask=cv2.bitwise_not(mask))
        
        return foreground, background
