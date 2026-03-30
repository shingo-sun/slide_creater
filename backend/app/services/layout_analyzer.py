"""
レイアウト解析サービス
画像をブロックに分割してレイアウト構造を抽出
"""
import cv2
import numpy as np
import uuid
from typing import List, Tuple

from app.models.slide_objects import LayoutBlock, BoundingBox, BlockType


class LayoutAnalyzer:
    """レイアウト解析サービス"""
    
    def __init__(self):
        self.min_block_area = 500
        
    def analyze(self, image: np.ndarray) -> List[LayoutBlock]:
        """
        画像からレイアウトブロックを抽出
        
        Args:
            image: 入力画像（BGR）
            
        Returns:
            LayoutBlockのリスト
        """
        blocks = []
        height, width = image.shape[:2]
        
        # 1. タイトル帯検出（上部10-20%）
        title_block = self._detect_title_band(image)
        if title_block:
            blocks.append(title_block)
        
        # 2. メインコンテンツ領域分析
        content_blocks = self._detect_content_blocks(image)
        blocks.extend(content_blocks)
        
        # 3. フッター検出（下部10%）
        footer_block = self._detect_footer(image)
        if footer_block:
            blocks.append(footer_block)
        
        # 4. ブロック間の階層関係を構築
        blocks = self._build_hierarchy(blocks)
        
        return blocks
    
    def _detect_title_band(self, image: np.ndarray) -> LayoutBlock:
        """タイトル帯を検出"""
        height, width = image.shape[:2]
        
        # 上部20%をタイトル領域として解析
        title_region = image[0:int(height * 0.2), :]
        
        # 色の変化を検出してタイトル帯の境界を特定
        gray = cv2.cvtColor(title_region, cv2.COLOR_BGR2GRAY)
        
        # 水平方向のエッジ検出
        edges = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edges = np.abs(edges)
        
        # 行ごとのエッジ強度
        row_edges = np.sum(edges, axis=1)
        
        # 強いエッジがある行をタイトル帯の下端とする
        threshold = np.max(row_edges) * 0.5
        strong_edges = np.where(row_edges > threshold)[0]
        
        if len(strong_edges) > 0:
            title_height = strong_edges[-1] + 10
        else:
            title_height = int(height * 0.15)
        
        return LayoutBlock(
            block_id=f"block_{uuid.uuid4().hex[:8]}",
            block_type=BlockType.TITLE,
            bounding_box=BoundingBox(
                x=0, y=0, width=width, height=title_height
            ),
            z_index=0,
            confidence=0.8
        )
    
    def _detect_content_blocks(self, image: np.ndarray) -> List[LayoutBlock]:
        """メインコンテンツ領域を解析"""
        blocks = []
        height, width = image.shape[:2]
        
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 適応的二値化
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # モルフォロジー処理でブロック化
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
        
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_h)
        vertical = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_v)
        
        combined = cv2.bitwise_or(horizontal, vertical)
        
        # ブロック領域を膨張
        kernel_block = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 30))
        dilated = cv2.dilate(combined, kernel_block, iterations=2)
        
        # 輪郭検出
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        z_index = 1
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_block_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # タイトル領域とフッター領域を除外
            if y < height * 0.15:
                continue
            if y + h > height * 0.9:
                continue
            
            # ブロックタイプを推定
            block_type = self._estimate_block_type(image, x, y, w, h)
            
            block = LayoutBlock(
                block_id=f"block_{uuid.uuid4().hex[:8]}",
                block_type=block_type,
                bounding_box=BoundingBox(x=x, y=y, width=w, height=h),
                z_index=z_index,
                confidence=0.7
            )
            blocks.append(block)
            z_index += 1
        
        return blocks
    
    def _detect_footer(self, image: np.ndarray) -> LayoutBlock:
        """フッター領域を検出"""
        height, width = image.shape[:2]
        
        footer_y = int(height * 0.9)
        footer_height = height - footer_y
        
        return LayoutBlock(
            block_id=f"block_{uuid.uuid4().hex[:8]}",
            block_type=BlockType.NOTE,
            bounding_box=BoundingBox(
                x=0, y=footer_y, width=width, height=footer_height
            ),
            z_index=100,
            confidence=0.6
        )
    
    def _estimate_block_type(
        self, 
        image: np.ndarray, 
        x: int, y: int, w: int, h: int
    ) -> BlockType:
        """ブロックタイプを推定"""
        roi = image[y:y+h, x:x+w]
        
        # 画像かどうか判定（色の分散で判断）
        if len(roi.shape) == 3:
            color_variance = np.var(roi.reshape(-1, 3), axis=0).mean()
            if color_variance > 1000:
                return BlockType.PHOTO
        
        # グレースケール変換
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # テキスト密度を計算
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        text_density = cv2.countNonZero(binary) / (w * h)
        
        # エッジ密度を計算
        edges = cv2.Canny(gray, 50, 150)
        edge_density = cv2.countNonZero(edges) / (w * h)
        
        # アスペクト比
        aspect_ratio = w / h if h > 0 else 1
        
        # 判定
        if text_density > 0.3 and edge_density < 0.1:
            # テキストが多い
            if aspect_ratio > 2:
                return BlockType.HEADING
            return BlockType.BODY
        elif edge_density > 0.15:
            # エッジが多い（図形やフロー図）
            if aspect_ratio > 1.5:
                return BlockType.FLOW
            return BlockType.SHAPE
        else:
            # アイコン領域の可能性
            if w < 100 and h < 100:
                return BlockType.ICON
            return BlockType.BODY
    
    def _build_hierarchy(self, blocks: List[LayoutBlock]) -> List[LayoutBlock]:
        """ブロック間の階層関係を構築"""
        # 位置関係に基づいて親子関係を設定
        for i, block in enumerate(blocks):
            for j, other in enumerate(blocks):
                if i == j:
                    continue
                
                # 包含関係をチェック
                if self._is_contained(block.bounding_box, other.bounding_box):
                    block.parent_block_id = other.block_id
                    if block.block_id not in other.child_block_ids:
                        other.child_block_ids.append(block.block_id)
        
        return blocks
    
    def _is_contained(self, inner: BoundingBox, outer: BoundingBox) -> bool:
        """innerがouterに含まれるか判定"""
        return (
            inner.x >= outer.x and
            inner.y >= outer.y and
            inner.x + inner.width <= outer.x + outer.width and
            inner.y + inner.height <= outer.y + outer.height and
            inner.width < outer.width and
            inner.height < outer.height
        )
    
    def detect_columns(self, image: np.ndarray) -> int:
        """カラム数を検出"""
        height, width = image.shape[:2]
        
        # 中央部分を解析
        center_region = image[int(height*0.2):int(height*0.8), :]
        gray = cv2.cvtColor(center_region, cv2.COLOR_BGR2GRAY)
        
        # 垂直方向の投影
        vertical_projection = np.sum(255 - gray, axis=0)
        
        # 谷（空白領域）を検出
        threshold = np.max(vertical_projection) * 0.3
        valleys = np.where(vertical_projection < threshold)[0]
        
        # 連続した谷をグループ化
        if len(valleys) == 0:
            return 1
        
        gaps = np.diff(valleys)
        significant_gaps = np.where(gaps > 20)[0]
        
        num_columns = len(significant_gaps) + 1
        
        return min(num_columns, 4)  # 最大4カラム
