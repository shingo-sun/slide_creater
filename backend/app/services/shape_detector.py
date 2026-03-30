"""
図形検出サービス
OpenCVを使用した図形（長方形、円、線、矢印等）の検出
"""
import cv2
import numpy as np
import uuid
from pathlib import Path
from typing import List, Tuple, Optional

from app.models.slide_objects import (
    ShapeObject, RectangleObject, RoundedRectangleObject,
    CircleObject, EllipseObject, LineObject, ArrowObject,
    IconObject, Color, ObjectType
)


class ShapeDetector:
    """図形検出サービス"""
    
    def __init__(self):
        self.min_shape_area = 100  # 最小図形面積
        self.max_shape_area_ratio = 0.9  # 画像面積に対する最大比率
        
    def detect(self, image: np.ndarray) -> List[ShapeObject]:
        """
        画像から図形を検出
        
        Args:
            image: 入力画像（BGR）
            
        Returns:
            検出されたShapeObjectのリスト
        """
        shapes = []
        z_index = 0
        
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150)
        
        # 膨張処理で近接エッジを接続
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        
        # 輪郭検出
        contours, hierarchy = cv2.findContours(
            edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        
        image_area = image.shape[0] * image.shape[1]
        
        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            
            # 面積フィルタリング
            if area < self.min_shape_area:
                continue
            if area > image_area * self.max_shape_area_ratio:
                continue
            
            # 形状判定と図形オブジェクト作成
            shape_obj = self._classify_and_create_shape(
                contour, image, z_index
            )
            
            if shape_obj:
                shapes.append(shape_obj)
                z_index += 1
        
        # 線・矢印の検出
        lines = self._detect_lines(image, z_index)
        shapes.extend(lines)
        
        return shapes
    
    def _classify_and_create_shape(
        self, 
        contour: np.ndarray, 
        image: np.ndarray,
        z_index: int
    ) -> Optional[ShapeObject]:
        """輪郭から図形を分類してオブジェクト作成"""
        # 輪郭の近似
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        
        # バウンディングボックス
        x, y, w, h = cv2.boundingRect(contour)
        
        # 形状の特徴量
        num_vertices = len(approx)
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        circularity = 4 * np.pi * area / (perimeter ** 2) if perimeter > 0 else 0
        
        # 色情報抽出
        fill_color, line_color = self._extract_colors(image, contour, x, y, w, h)
        
        # 形状判定
        if num_vertices == 4:
            # 四角形
            return self._create_rectangle(
                approx, x, y, w, h, fill_color, line_color, z_index
            )
        elif circularity > 0.8:
            # 円または楕円
            return self._create_circle_or_ellipse(
                contour, x, y, w, h, fill_color, line_color, z_index
            )
        elif num_vertices >= 5 and num_vertices <= 8:
            # 角丸四角形として扱う
            return self._create_rounded_rectangle(
                x, y, w, h, fill_color, line_color, z_index
            )
        
        return None
    
    def _create_rectangle(
        self,
        approx: np.ndarray,
        x: int, y: int, w: int, h: int,
        fill_color: Optional[Color],
        line_color: Optional[Color],
        z_index: int
    ) -> RectangleObject:
        """長方形オブジェクトを作成"""
        return RectangleObject(
            object_id=f"rect_{uuid.uuid4().hex[:8]}",
            object_type=ObjectType.RECTANGLE,
            x=float(x),
            y=float(y),
            width=float(w),
            height=float(h),
            z_index=z_index,
            fill_color=fill_color,
            line_color=line_color,
            line_width=1.0
        )
    
    def _create_rounded_rectangle(
        self,
        x: int, y: int, w: int, h: int,
        fill_color: Optional[Color],
        line_color: Optional[Color],
        z_index: int
    ) -> RoundedRectangleObject:
        """角丸長方形オブジェクトを作成"""
        # 角丸半径を推定（サイズの10%程度）
        corner_radius = min(w, h) * 0.1
        
        return RoundedRectangleObject(
            object_id=f"rrect_{uuid.uuid4().hex[:8]}",
            object_type=ObjectType.ROUNDED_RECTANGLE,
            x=float(x),
            y=float(y),
            width=float(w),
            height=float(h),
            z_index=z_index,
            fill_color=fill_color,
            line_color=line_color,
            line_width=1.0,
            corner_radius=corner_radius
        )
    
    def _create_circle_or_ellipse(
        self,
        contour: np.ndarray,
        x: int, y: int, w: int, h: int,
        fill_color: Optional[Color],
        line_color: Optional[Color],
        z_index: int
    ) -> ShapeObject:
        """円または楕円オブジェクトを作成"""
        # 幅と高さの比率で円か楕円か判定
        aspect_ratio = w / h if h > 0 else 1
        
        if 0.9 < aspect_ratio < 1.1:
            # 円
            return CircleObject(
                object_id=f"circle_{uuid.uuid4().hex[:8]}",
                object_type=ObjectType.CIRCLE,
                x=float(x),
                y=float(y),
                width=float(w),
                height=float(h),
                z_index=z_index,
                fill_color=fill_color,
                line_color=line_color,
                line_width=1.0
            )
        else:
            # 楕円
            return EllipseObject(
                object_id=f"ellipse_{uuid.uuid4().hex[:8]}",
                object_type=ObjectType.ELLIPSE,
                x=float(x),
                y=float(y),
                width=float(w),
                height=float(h),
                z_index=z_index,
                fill_color=fill_color,
                line_color=line_color,
                line_width=1.0
            )
    
    def _detect_lines(
        self, 
        image: np.ndarray, 
        start_z_index: int
    ) -> List[LineObject]:
        """線と矢印を検出（厳格なフィルタリング）"""
        lines_detected = []
        z_index = start_z_index
        
        # 画像サイズを取得
        h, w = image.shape[:2]
        min_line_length = max(80, min(h, w) * 0.05)  # 最小線長を画像サイズの5%以上に
        
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # ぼかしでノイズ除去
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # エッジ検出（閾値を上げる）
        edges = cv2.Canny(gray, 100, 200, apertureSize=3)
        
        # 確率的ハフ変換で線分検出（厳格なパラメータ）
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, 
            threshold=100,  # 50から100に増加
            minLineLength=int(min_line_length),  # 動的に設定
            maxLineGap=5  # 10から5に減少
        )
        
        if lines is None:
            return lines_detected
        
        # 重複除去と上限設定
        unique_lines = self._filter_duplicate_lines(lines, threshold=20)
        
        # 最大20本まで（過剰検出防止）
        max_lines = 20
        if len(unique_lines) > max_lines:
            # 長い線を優先
            unique_lines = sorted(unique_lines, key=lambda l: 
                np.sqrt((l[2]-l[0])**2 + (l[3]-l[1])**2), reverse=True)[:max_lines]
        
        for x1, y1, x2, y2 in unique_lines:
            # 水平・垂直に近い線のみ検出（斜め線は図形の輪郭の可能性が高い）
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            is_horizontal = angle < 15 or angle > 165
            is_vertical = 75 < angle < 105
            
            if not (is_horizontal or is_vertical):
                continue  # 斜め線はスキップ
            
            # 線の色を取得
            line_color = self._get_line_color(image, x1, y1, x2, y2)
            
            # 背景色に近い線はスキップ（白や薄いグレー）
            if line_color.r > 200 and line_color.g > 200 and line_color.b > 200:
                continue
            
            # 矢印判定
            is_arrow = self._is_arrow(image, x1, y1, x2, y2)
            
            # 線の幅を推定
            line_width = self._estimate_line_width(image, x1, y1, x2, y2)
            
            if is_arrow:
                arrow_obj = ArrowObject(
                    object_id=f"arrow_{uuid.uuid4().hex[:8]}",
                    object_type=ObjectType.ARROW,
                    x=float(min(x1, x2)),
                    y=float(min(y1, y2)),
                    width=float(abs(x2 - x1)) or 1,
                    height=float(abs(y2 - y1)) or 1,
                    z_index=z_index,
                    start_x=float(x1),
                    start_y=float(y1),
                    end_x=float(x2),
                    end_y=float(y2),
                    line_color=line_color,
                    line_width=line_width,
                    arrow_head="end"
                )
                lines_detected.append(arrow_obj)
            else:
                line_obj = LineObject(
                    object_id=f"line_{uuid.uuid4().hex[:8]}",
                    object_type=ObjectType.LINE,
                    x=float(min(x1, x2)),
                    y=float(min(y1, y2)),
                    width=float(abs(x2 - x1)) or 1,
                    height=float(abs(y2 - y1)) or 1,
                    z_index=z_index,
                    start_x=float(x1),
                    start_y=float(y1),
                    end_x=float(x2),
                    end_y=float(y2),
                    line_color=line_color,
                    line_width=line_width
                )
                lines_detected.append(line_obj)
            
            z_index += 1
        
        return lines_detected
    
    def _filter_duplicate_lines(
        self, 
        lines: np.ndarray, 
        threshold: int = 20
    ) -> List[tuple]:
        """重複する線を除去"""
        if lines is None or len(lines) == 0:
            return []
        
        unique = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            is_duplicate = False
            
            for ux1, uy1, ux2, uy2 in unique:
                # 始点と終点の距離で重複判定
                dist1 = np.sqrt((x1-ux1)**2 + (y1-uy1)**2)
                dist2 = np.sqrt((x2-ux2)**2 + (y2-uy2)**2)
                dist3 = np.sqrt((x1-ux2)**2 + (y1-uy2)**2)
                dist4 = np.sqrt((x2-ux1)**2 + (y2-uy1)**2)
                
                if (dist1 < threshold and dist2 < threshold) or \
                   (dist3 < threshold and dist4 < threshold):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append((x1, y1, x2, y2))
        
        return unique
    
    def _extract_colors(
        self, 
        image: np.ndarray, 
        contour: np.ndarray,
        x: int, y: int, w: int, h: int
    ) -> Tuple[Optional[Color], Optional[Color]]:
        """図形の塗り色と線色を抽出"""
        # マスク作成
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        
        # 内部の色（塗り色）
        inner_mask = cv2.erode(mask, np.ones((5, 5), np.uint8), iterations=2)
        if cv2.countNonZero(inner_mask) > 0:
            inner_colors = image[inner_mask > 0]
            if len(inner_colors) > 0:
                mean_color = np.mean(inner_colors, axis=0).astype(int)
                fill_color = Color(
                    r=int(mean_color[2]), 
                    g=int(mean_color[1]), 
                    b=int(mean_color[0])
                )
            else:
                fill_color = None
        else:
            fill_color = None
        
        # 輪郭の色（線色）
        edge_mask = cv2.dilate(mask, np.ones((3, 3), np.uint8)) - mask
        if cv2.countNonZero(edge_mask) > 0:
            edge_colors = image[edge_mask > 0]
            if len(edge_colors) > 0:
                mean_edge_color = np.mean(edge_colors, axis=0).astype(int)
                line_color = Color(
                    r=int(mean_edge_color[2]), 
                    g=int(mean_edge_color[1]), 
                    b=int(mean_edge_color[0])
                )
            else:
                line_color = Color(r=0, g=0, b=0)
        else:
            line_color = Color(r=0, g=0, b=0)
        
        return fill_color, line_color
    
    def _get_line_color(
        self, 
        image: np.ndarray, 
        x1: int, y1: int, x2: int, y2: int
    ) -> Color:
        """線の色を取得"""
        # 線上のピクセルをサンプリング
        num_samples = 5
        colors = []
        
        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0.5
            px = int(x1 + t * (x2 - x1))
            py = int(y1 + t * (y2 - y1))
            
            # 境界チェック
            if 0 <= py < image.shape[0] and 0 <= px < image.shape[1]:
                colors.append(image[py, px])
        
        if colors:
            mean_color = np.mean(colors, axis=0).astype(int)
            return Color(
                r=int(mean_color[2]), 
                g=int(mean_color[1]), 
                b=int(mean_color[0])
            )
        
        return Color(r=0, g=0, b=0)
    
    def _is_arrow(
        self, 
        image: np.ndarray, 
        x1: int, y1: int, x2: int, y2: int
    ) -> bool:
        """線が矢印かどうか判定"""
        # 端点周辺の形状を解析
        # 簡易実装：端点周辺のエッジ密度で判定
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        
        # 終点周辺のROI
        roi_size = 15
        y_start = max(0, y2 - roi_size)
        y_end = min(image.shape[0], y2 + roi_size)
        x_start = max(0, x2 - roi_size)
        x_end = min(image.shape[1], x2 + roi_size)
        
        roi = edges[y_start:y_end, x_start:x_end]
        
        # エッジ密度が高ければ矢印の可能性
        edge_density = cv2.countNonZero(roi) / (roi.size + 1)
        
        return edge_density > 0.15
    
    def _estimate_line_width(
        self, 
        image: np.ndarray, 
        x1: int, y1: int, x2: int, y2: int
    ) -> float:
        """線の幅を推定"""
        # 簡易実装：デフォルト値
        # 実際には垂直方向のエッジ解析が必要
        return 2.0
    
    def detect_icons(
        self, 
        image: np.ndarray, 
        output_dir: Path,
        file_id: str
    ) -> List[IconObject]:
        """
        アイコン・ピクトを検出して切り出し
        
        Args:
            image: 入力画像
            output_dir: 切り出し画像の保存先
            file_id: ファイルID
            
        Returns:
            IconObjectのリスト
        """
        icons = []
        
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 輪郭検出
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        image_area = image.shape[0] * image.shape[1]
        icon_idx = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            
            # アイコンサイズの範囲（小さめの独立したオブジェクト）
            if area < 200 or area > image_area * 0.05:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # アスペクト比チェック（極端に細長いものは除外）
            aspect = w / h if h > 0 else 0
            if aspect < 0.3 or aspect > 3:
                continue
            
            # アイコン画像を切り出して保存
            icon_image = image[y:y+h, x:x+w]
            icon_filename = f"{file_id}_icon_{icon_idx}.png"
            icon_path = output_dir / icon_filename
            cv2.imwrite(str(icon_path), icon_image)
            
            # 主要な色を抽出
            colors = self._extract_icon_colors(icon_image)
            
            icon_obj = IconObject(
                object_id=f"icon_{uuid.uuid4().hex[:8]}",
                object_type=ObjectType.ICON,
                x=float(x),
                y=float(y),
                width=float(w),
                height=float(h),
                z_index=50 + icon_idx,
                image_path=str(icon_path),
                original_colors=colors
            )
            icons.append(icon_obj)
            icon_idx += 1
        
        return icons
    
    def _extract_icon_colors(self, icon_image: np.ndarray) -> List[Color]:
        """アイコンの主要色を抽出"""
        # K-meansで主要色抽出
        pixels = icon_image.reshape(-1, 3).astype(np.float32)
        
        # 白と黒に近い色を除外
        mask = np.all(
            (pixels > 30) & (pixels < 225), 
            axis=1
        )
        filtered_pixels = pixels[mask]
        
        if len(filtered_pixels) < 10:
            return []
        
        # K-means
        k = min(3, len(filtered_pixels) // 10)
        if k < 1:
            return []
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(
            filtered_pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
        )
        
        colors = []
        for center in centers:
            colors.append(Color(
                r=int(center[2]),
                g=int(center[1]),
                b=int(center[0])
            ))
        
        return colors
