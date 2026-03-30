"""
品質検証サービス
ダブルループ学習による整合性分析
"""
import cv2
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

from app.models.slide_objects import (
    SlideAnalysisResult, TextObject, ShapeObject, IconObject
)


@dataclass
class QualityReport:
    """品質レポート"""
    is_acceptable: bool
    overall_score: float
    text_coverage_score: float
    layout_score: float
    object_count_reasonable: bool
    issues: List[str]
    recommendations: List[str]


class QualityChecker:
    """
    品質検証クラス
    ダブルループ学習による整合性分析を実行
    """
    
    def __init__(self):
        self.min_acceptable_score = 0.5
        self.max_text_objects = 50
        self.max_shape_objects = 30
    
    def validate_analysis_result(
        self,
        original_image: np.ndarray,
        analysis_result: SlideAnalysisResult
    ) -> QualityReport:
        """
        解析結果の品質を検証
        
        Args:
            original_image: 元画像
            analysis_result: 解析結果
            
        Returns:
            QualityReport: 品質レポート
        """
        issues = []
        recommendations = []
        
        # 1. オブジェクト数の妥当性チェック
        text_count = len(analysis_result.text_objects)
        shape_count = len(analysis_result.shape_objects)
        
        object_count_reasonable = True
        if text_count > self.max_text_objects:
            issues.append(f"テキストオブジェクト数が多すぎます: {text_count}")
            object_count_reasonable = False
        if shape_count > self.max_shape_objects:
            issues.append(f"図形オブジェクト数が多すぎます: {shape_count}")
            object_count_reasonable = False
        
        # 2. テキストカバレッジスコア
        text_coverage_score = self._calculate_text_coverage(
            original_image, analysis_result.text_objects
        )
        
        # 3. レイアウトスコア
        layout_score = self._calculate_layout_score(
            original_image, analysis_result
        )
        
        # 4. 重複テキストの検出
        duplicate_texts = self._detect_duplicate_texts(
            analysis_result.text_objects
        )
        if duplicate_texts:
            issues.append(f"重複テキスト検出: {len(duplicate_texts)}件")
            recommendations.append("テキスト統合を推奨")
        
        # 5. 総合スコア計算
        overall_score = (text_coverage_score + layout_score) / 2
        
        if overall_score < self.min_acceptable_score:
            recommendations.append("忠実再現モード（背景画像使用）を推奨")
        
        is_acceptable = (
            overall_score >= self.min_acceptable_score and 
            object_count_reasonable
        )
        
        return QualityReport(
            is_acceptable=bool(is_acceptable),  # numpy.bool_ -> Python bool
            overall_score=float(overall_score),
            text_coverage_score=float(text_coverage_score),
            layout_score=float(layout_score),
            object_count_reasonable=bool(object_count_reasonable),
            issues=issues,
            recommendations=recommendations
        )
    
    def _calculate_text_coverage(
        self,
        image: np.ndarray,
        text_objects: List[TextObject]
    ) -> float:
        """テキストカバレッジスコアを計算"""
        if not text_objects:
            return 0.0
        
        h, w = image.shape[:2]
        
        # 元画像からテキスト領域を検出（グレースケール + 閾値処理）
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # テキストらしい領域のマスク作成
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # 検出されたテキストオブジェクトのマスク
        detected_mask = np.zeros((h, w), dtype=np.uint8)
        for text in text_objects:
            x1 = max(0, int(text.x))
            y1 = max(0, int(text.y))
            x2 = min(w, int(text.x + text.width))
            y2 = min(h, int(text.y + text.height))
            cv2.rectangle(detected_mask, (x1, y1), (x2, y2), 255, -1)
        
        # オーバーラップ計算
        original_area = np.sum(binary > 0)
        if original_area == 0:
            return 1.0
        
        overlap = np.sum((binary > 0) & (detected_mask > 0))
        coverage = overlap / original_area
        
        return min(1.0, coverage)
    
    def _calculate_layout_score(
        self,
        image: np.ndarray,
        analysis_result: SlideAnalysisResult
    ) -> float:
        """レイアウトスコアを計算"""
        h, w = image.shape[:2]
        
        # オブジェクトが画像境界内にあるかチェック
        all_objects = (
            list(analysis_result.text_objects) +
            list(analysis_result.shape_objects)
        )
        
        if not all_objects:
            return 0.5
        
        in_bounds_count = 0
        for obj in all_objects:
            if (0 <= obj.x < w and 
                0 <= obj.y < h and
                obj.x + obj.width <= w * 1.1 and
                obj.y + obj.height <= h * 1.1):
                in_bounds_count += 1
        
        return in_bounds_count / len(all_objects)
    
    def _detect_duplicate_texts(
        self,
        text_objects: List[TextObject]
    ) -> List[Tuple[TextObject, TextObject]]:
        """重複テキストを検出"""
        duplicates = []
        
        for i, text1 in enumerate(text_objects):
            for text2 in text_objects[i+1:]:
                # 位置が近い場合
                if (abs(text1.x - text2.x) < 50 and 
                    abs(text1.y - text2.y) < 30):
                    duplicates.append((text1, text2))
        
        return duplicates
    
    def optimize_analysis_result(
        self,
        analysis_result: SlideAnalysisResult,
        quality_report: QualityReport
    ) -> SlideAnalysisResult:
        """
        品質レポートに基づいて解析結果を最適化
        """
        # テキストオブジェクトの統合・フィルタリング
        optimized_texts = self._optimize_text_objects(
            analysis_result.text_objects
        )
        
        # 図形オブジェクトのフィルタリング
        optimized_shapes = self._optimize_shape_objects(
            analysis_result.shape_objects
        )
        
        # 新しい解析結果を作成
        return SlideAnalysisResult(
            file_id=analysis_result.file_id,
            image_info=analysis_result.image_info,
            layout_blocks=analysis_result.layout_blocks,
            text_objects=optimized_texts,
            shape_objects=optimized_shapes,
            icon_objects=analysis_result.icon_objects,
            mode=analysis_result.mode,
            slide_ratio=analysis_result.slide_ratio
        )
    
    def _optimize_text_objects(
        self,
        text_objects: List[TextObject]
    ) -> List[TextObject]:
        """テキストオブジェクトを最適化"""
        if not text_objects:
            return []
        
        # 信頼度でソート
        sorted_texts = sorted(
            text_objects, 
            key=lambda t: t.source_confidence, 
            reverse=True
        )
        
        optimized = []
        used_regions = []
        
        for text in sorted_texts:
            # 既存領域との重複チェック
            is_duplicate = False
            for region in used_regions:
                rx, ry, rw, rh = region
                overlap_x = max(0, min(text.x + text.width, rx + rw) - max(text.x, rx))
                overlap_y = max(0, min(text.y + text.height, ry + rh) - max(text.y, ry))
                overlap_area = overlap_x * overlap_y
                text_area = text.width * text.height
                
                if text_area > 0 and overlap_area / text_area > 0.5:
                    is_duplicate = True
                    break
            
            if not is_duplicate and text.text.strip():
                optimized.append(text)
                used_regions.append((text.x, text.y, text.width, text.height))
        
        # 最大30個まで
        return optimized[:30]
    
    def _optimize_shape_objects(
        self,
        shape_objects: List[ShapeObject]
    ) -> List[ShapeObject]:
        """図形オブジェクトを最適化"""
        if not shape_objects:
            return []
        
        # 極端に小さい図形を除外
        filtered = [
            s for s in shape_objects 
            if s.width > 20 and s.height > 20
        ]
        
        # 最大20個まで
        return filtered[:20]
