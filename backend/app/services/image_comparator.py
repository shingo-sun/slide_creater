"""
画像比較サービス
元画像と生成画像の差分を検出・分析
"""
import cv2
import numpy as np
from PIL import Image
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from skimage.metrics import structural_similarity as ssim
import logging

logger = logging.getLogger(__name__)


@dataclass
class DifferenceRegion:
    """差分領域"""
    x: int
    y: int
    width: int
    height: int
    severity: float  # 0-1 差分の深刻度
    type: str  # "text", "shape", "color", "layout", "missing", "extra"
    description: str


@dataclass
class ComparisonResult:
    """比較結果"""
    similarity_score: float  # 0-1 全体の類似度
    ssim_score: float  # 構造的類似度
    pixel_diff_ratio: float  # ピクセル差分率
    difference_regions: List[DifferenceRegion]
    diff_image_path: Optional[str]  # 差分可視化画像
    summary: str


class ImageComparator:
    """画像比較サービス"""
    
    def __init__(self):
        self.min_diff_area = 100  # 最小差分領域（ピクセル数）
        self.diff_threshold = 30  # 差分検出閾値
    
    def compare_images(
        self,
        original_path: str,
        generated_path: str,
        output_diff_path: Optional[str] = None
    ) -> ComparisonResult:
        """
        2つの画像を比較
        
        Args:
            original_path: 元画像パス
            generated_path: 生成画像パス
            output_diff_path: 差分画像の出力パス（オプション）
            
        Returns:
            ComparisonResult
        """
        # 画像読み込み
        original = cv2.imread(original_path)
        generated = cv2.imread(generated_path)
        
        if original is None:
            raise ValueError(f"元画像を読み込めません: {original_path}")
        if generated is None:
            raise ValueError(f"生成画像を読み込めません: {generated_path}")
        
        # サイズを合わせる
        original, generated = self._resize_to_match(original, generated)
        
        # 各種スコア計算
        ssim_score = self._calculate_ssim(original, generated)
        pixel_diff_ratio = self._calculate_pixel_diff(original, generated)
        
        # 差分領域検出
        difference_regions = self._detect_difference_regions(
            original, generated
        )
        
        # 差分画像生成
        diff_image_path = None
        if output_diff_path:
            diff_image_path = self._create_diff_visualization(
                original, generated, difference_regions, output_diff_path
            )
        
        # 総合スコア計算
        similarity_score = self._calculate_overall_score(
            ssim_score, pixel_diff_ratio, difference_regions
        )
        
        # サマリー生成
        summary = self._generate_summary(
            similarity_score, ssim_score, pixel_diff_ratio, difference_regions
        )
        
        return ComparisonResult(
            similarity_score=similarity_score,
            ssim_score=ssim_score,
            pixel_diff_ratio=pixel_diff_ratio,
            difference_regions=difference_regions,
            diff_image_path=diff_image_path,
            summary=summary
        )
    
    def _resize_to_match(
        self,
        img1: np.ndarray,
        img2: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """画像サイズを合わせる"""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        if h1 != h2 or w1 != w2:
            # 大きい方に合わせる
            target_h = max(h1, h2)
            target_w = max(w1, w2)
            
            img1 = cv2.resize(img1, (target_w, target_h))
            img2 = cv2.resize(img2, (target_w, target_h))
        
        return img1, img2
    
    def _calculate_ssim(
        self,
        img1: np.ndarray,
        img2: np.ndarray
    ) -> float:
        """構造的類似度を計算"""
        # グレースケールに変換
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        
        score, _ = ssim(gray1, gray2, full=True)
        return float(score)
    
    def _calculate_pixel_diff(
        self,
        img1: np.ndarray,
        img2: np.ndarray
    ) -> float:
        """ピクセル差分率を計算"""
        diff = cv2.absdiff(img1, img2)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # 閾値以上の差分ピクセル数
        _, thresh = cv2.threshold(
            gray_diff, self.diff_threshold, 255, cv2.THRESH_BINARY
        )
        
        diff_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.shape[0] * thresh.shape[1]
        
        return diff_pixels / total_pixels
    
    def _detect_difference_regions(
        self,
        original: np.ndarray,
        generated: np.ndarray
    ) -> List[DifferenceRegion]:
        """差分領域を検出"""
        regions = []
        
        # 差分画像生成
        diff = cv2.absdiff(original, generated)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # 二値化
        _, thresh = cv2.threshold(
            gray_diff, self.diff_threshold, 255, cv2.THRESH_BINARY
        )
        
        # モルフォロジー処理でノイズ除去
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # 輪郭検出
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_diff_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # 差分タイプを推定
            diff_type, description = self._classify_difference(
                original, generated, x, y, w, h
            )
            
            # 深刻度計算
            severity = self._calculate_severity(
                original, generated, x, y, w, h
            )
            
            regions.append(DifferenceRegion(
                x=x, y=y, width=w, height=h,
                severity=severity,
                type=diff_type,
                description=description
            ))
        
        # 深刻度でソート
        regions.sort(key=lambda r: r.severity, reverse=True)
        
        return regions[:20]  # 最大20領域
    
    def _classify_difference(
        self,
        original: np.ndarray,
        generated: np.ndarray,
        x: int, y: int, w: int, h: int
    ) -> Tuple[str, str]:
        """差分タイプを分類"""
        orig_region = original[y:y+h, x:x+w]
        gen_region = generated[y:y+h, x:x+w]
        
        # 平均色の差
        orig_mean = np.mean(orig_region, axis=(0, 1))
        gen_mean = np.mean(gen_region, axis=(0, 1))
        color_diff = np.linalg.norm(orig_mean - gen_mean)
        
        # エッジ検出で形状の違いを判定
        orig_edges = cv2.Canny(orig_region, 50, 150)
        gen_edges = cv2.Canny(gen_region, 50, 150)
        
        orig_edge_count = np.count_nonzero(orig_edges)
        gen_edge_count = np.count_nonzero(gen_edges)
        
        # 分類ロジック
        if orig_edge_count > gen_edge_count * 1.5:
            return "missing", f"要素が欠落している可能性 (位置: {x},{y})"
        elif gen_edge_count > orig_edge_count * 1.5:
            return "extra", f"余分な要素がある可能性 (位置: {x},{y})"
        elif color_diff > 50:
            return "color", f"色の違い (位置: {x},{y})"
        elif abs(orig_edge_count - gen_edge_count) > 100:
            return "shape", f"形状の違い (位置: {x},{y})"
        else:
            return "layout", f"レイアウトのずれ (位置: {x},{y})"
    
    def _calculate_severity(
        self,
        original: np.ndarray,
        generated: np.ndarray,
        x: int, y: int, w: int, h: int
    ) -> float:
        """差分の深刻度を計算"""
        orig_region = original[y:y+h, x:x+w]
        gen_region = generated[y:y+h, x:x+w]
        
        # ピクセル差分
        diff = cv2.absdiff(orig_region, gen_region)
        mean_diff = np.mean(diff)
        
        # 領域サイズの重み
        total_area = original.shape[0] * original.shape[1]
        region_area = w * h
        size_factor = min(region_area / total_area * 10, 1.0)
        
        # 0-1 に正規化
        severity = min((mean_diff / 128) * (0.5 + size_factor * 0.5), 1.0)
        
        return severity
    
    def _create_diff_visualization(
        self,
        original: np.ndarray,
        generated: np.ndarray,
        regions: List[DifferenceRegion],
        output_path: str
    ) -> str:
        """差分可視化画像を生成"""
        # 3つの画像を横に並べる: 元画像、生成画像、差分ハイライト
        h, w = original.shape[:2]
        
        # 差分ヒートマップ作成
        diff = cv2.absdiff(original, generated)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        heatmap = cv2.applyColorMap(gray_diff, cv2.COLORMAP_JET)
        
        # 差分領域を矩形でハイライト
        highlighted = generated.copy()
        for region in regions:
            color = (0, 0, 255) if region.severity > 0.5 else (0, 165, 255)
            cv2.rectangle(
                highlighted,
                (region.x, region.y),
                (region.x + region.width, region.y + region.height),
                color, 2
            )
        
        # 結合
        combined = np.hstack([original, highlighted, heatmap])
        
        # ラベル追加
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(combined, "Original", (10, 30), font, 1, (255, 255, 255), 2)
        cv2.putText(combined, "Generated + Diff", (w + 10, 30), font, 1, (255, 255, 255), 2)
        cv2.putText(combined, "Heatmap", (w * 2 + 10, 30), font, 1, (255, 255, 255), 2)
        
        cv2.imwrite(output_path, combined)
        
        return output_path
    
    def _calculate_overall_score(
        self,
        ssim_score: float,
        pixel_diff_ratio: float,
        regions: List[DifferenceRegion]
    ) -> float:
        """総合スコアを計算"""
        # SSIM: 40%
        # ピクセル差分: 30%
        # 差分領域数・深刻度: 30%
        
        pixel_score = 1.0 - pixel_diff_ratio
        
        if regions:
            avg_severity = sum(r.severity for r in regions) / len(regions)
            region_penalty = min(len(regions) / 20, 1.0) * avg_severity
            region_score = 1.0 - region_penalty
        else:
            region_score = 1.0
        
        overall = (
            ssim_score * 0.4 +
            pixel_score * 0.3 +
            region_score * 0.3
        )
        
        return max(0.0, min(1.0, overall))
    
    def _generate_summary(
        self,
        similarity_score: float,
        ssim_score: float,
        pixel_diff_ratio: float,
        regions: List[DifferenceRegion]
    ) -> str:
        """サマリーを生成"""
        lines = []
        
        # 総合評価
        if similarity_score >= 0.9:
            lines.append("✅ 高精度再現: 元画像とほぼ一致しています")
        elif similarity_score >= 0.7:
            lines.append("⚠️ 中程度の差分: いくつかの違いが検出されました")
        else:
            lines.append("❌ 大きな差分: 再生成を推奨します")
        
        lines.append(f"- 類似度スコア: {similarity_score:.1%}")
        lines.append(f"- 構造的類似度 (SSIM): {ssim_score:.1%}")
        lines.append(f"- ピクセル差分率: {pixel_diff_ratio:.1%}")
        
        # 差分領域の内訳
        if regions:
            type_counts = {}
            for r in regions:
                type_counts[r.type] = type_counts.get(r.type, 0) + 1
            
            lines.append(f"- 検出された差分領域: {len(regions)}箇所")
            for diff_type, count in type_counts.items():
                type_labels = {
                    "text": "テキスト",
                    "shape": "形状",
                    "color": "色",
                    "layout": "レイアウト",
                    "missing": "要素欠落",
                    "extra": "余分な要素"
                }
                lines.append(f"  - {type_labels.get(diff_type, diff_type)}: {count}箇所")
        
        return "\n".join(lines)


# シングルトンインスタンス
image_comparator = ImageComparator()
