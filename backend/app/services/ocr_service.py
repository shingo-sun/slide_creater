"""
OCRサービス
Google Cloud Vision APIを使用した日本語OCR処理
"""
import os
import uuid
from typing import List, Optional
import numpy as np
import cv2

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from app.models.slide_objects import (
    TextObject, Color, TextAlignment, ObjectType
)


class OCRService:
    """OCR処理サービス"""
    
    def __init__(self):
        self.use_cloud_vision = self._check_cloud_vision_available()
        
    def _check_cloud_vision_available(self) -> bool:
        """Google Cloud Vision APIが利用可能か確認"""
        try:
            # 環境変数または認証ファイルの確認
            if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                from google.cloud import vision
                return True
        except ImportError:
            pass
        return False
    
    def extract_text(
        self, 
        image_path: str, 
        processed_image: np.ndarray
    ) -> List[TextObject]:
        """
        画像からテキストを抽出
        
        Args:
            image_path: 元画像パス
            processed_image: 前処理済み画像
            
        Returns:
            TextObjectのリスト
        """
        if self.use_cloud_vision:
            return self._extract_with_cloud_vision(image_path)
        else:
            return self._extract_with_fallback(processed_image)
    
    def _extract_with_cloud_vision(self, image_path: str) -> List[TextObject]:
        """Google Cloud Vision APIでOCR"""
        from google.cloud import vision
        
        client = vision.ImageAnnotatorClient()
        
        with open(image_path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        
        # ドキュメントテキスト検出（より詳細な情報を取得）
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")
        
        text_objects = []
        z_index = 100  # テキストは前面に配置
        
        if not response.full_text_annotation.pages:
            return text_objects
        
        # ページ情報から抽出
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    # 段落単位でテキストボックス作成
                    text_obj = self._create_text_object_from_paragraph(
                        paragraph, z_index
                    )
                    if text_obj:
                        text_objects.append(text_obj)
                        z_index += 1
        
        return text_objects
    
    def _create_text_object_from_paragraph(
        self, paragraph, z_index: int
    ) -> Optional[TextObject]:
        """Vision API段落からTextObjectを作成"""
        # テキスト抽出
        text_parts = []
        for word in paragraph.words:
            word_text = ''.join([
                symbol.text for symbol in word.symbols
            ])
            text_parts.append(word_text)
        
        text = ' '.join(text_parts)
        if not text.strip():
            return None
        
        # バウンディングボックス計算
        vertices = paragraph.bounding_box.vertices
        x_coords = [v.x for v in vertices]
        y_coords = [v.y for v in vertices]
        
        x = min(x_coords)
        y = min(y_coords)
        width = max(x_coords) - x
        height = max(y_coords) - y
        
        if width <= 0 or height <= 0:
            return None
        
        # フォントサイズ推定（高さベース）
        estimated_font_size = self._estimate_font_size(height, len(text))
        
        # 太字判定（confidence等から推定）
        font_weight = "normal"
        
        # アライメント推定
        alignment = self._estimate_alignment(paragraph)
        
        # 色推定（デフォルト黒）
        text_color = Color(r=0, g=0, b=0)
        
        return TextObject(
            object_id=f"text_{uuid.uuid4().hex[:8]}",
            object_type=ObjectType.TEXT,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            z_index=z_index,
            text=text,
            font_size=estimated_font_size,
            font_weight=font_weight,
            text_color=text_color,
            alignment=alignment
        )
    
    def _extract_with_fallback(
        self, processed_image: np.ndarray
    ) -> List[TextObject]:
        """
        フォールバック：Tesseract OCRまたはテキスト領域検出
        """
        # Tesseractが利用可能な場合は使用
        if TESSERACT_AVAILABLE:
            return self._extract_with_tesseract(processed_image)
        
        # それ以外は領域検出のみ（テキスト内容なし）
        return self._detect_text_regions_only(processed_image)
    
    def _extract_with_tesseract(
        self, processed_image: np.ndarray
    ) -> List[TextObject]:
        """Tesseract OCRでテキスト抽出"""
        text_objects = []
        
        # グレースケール変換
        gray = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY)
        
        # コントラスト強調
        gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
        
        try:
            # Tesseractでテキスト検出（日本語+英語）
            data = pytesseract.image_to_data(
                gray, 
                lang='jpn+eng', 
                output_type=pytesseract.Output.DICT,
                config='--psm 6'  # Assume a single uniform block of text
            )
            
            z_index = 100
            n_boxes = len(data['text'])
            
            # 単語を行単位でグループ化
            current_line = []
            prev_top = -1
            line_threshold = 10
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = int(data['conf'][i])
                
                # 信頼度が低いか空のテキストはスキップ
                if conf < 30 or not text:
                    continue
                
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                # 同じ行かどうか判定
                if prev_top >= 0 and abs(y - prev_top) < line_threshold:
                    current_line.append({
                        'text': text, 'x': x, 'y': y, 'w': w, 'h': h, 'conf': conf
                    })
                else:
                    # 前の行を処理
                    if current_line:
                        text_obj = self._create_text_from_line(current_line, z_index)
                        if text_obj:
                            text_objects.append(text_obj)
                            z_index += 1
                    # 新しい行開始
                    current_line = [{
                        'text': text, 'x': x, 'y': y, 'w': w, 'h': h, 'conf': conf
                    }]
                
                prev_top = y
            
            # 最後の行を処理
            if current_line:
                text_obj = self._create_text_from_line(current_line, z_index)
                if text_obj:
                    text_objects.append(text_obj)
            
        except Exception as e:
            print(f"Tesseract OCR error: {e}")
            # エラー時は領域検出のみ
            return self._detect_text_regions_only(processed_image)
        
        return text_objects
    
    def _create_text_from_line(
        self, line_words: List[dict], z_index: int
    ) -> Optional[TextObject]:
        """行単位でTextObjectを作成"""
        if not line_words:
            return None
        
        # テキスト結合
        text = ' '.join([w['text'] for w in line_words])
        if not text.strip():
            return None
        
        # バウンディングボックス計算
        x = min(w['x'] for w in line_words)
        y = min(w['y'] for w in line_words)
        x2 = max(w['x'] + w['w'] for w in line_words)
        y2 = max(w['y'] + w['h'] for w in line_words)
        
        width = x2 - x
        height = y2 - y
        
        if width <= 0 or height <= 0:
            return None
        
        # フォントサイズ推定
        avg_height = sum(w['h'] for w in line_words) / len(line_words)
        font_size = max(8, min(72, avg_height * 0.75))
        
        # 平均信頼度
        avg_conf = sum(w['conf'] for w in line_words) / len(line_words) / 100.0
        
        return TextObject(
            object_id=f"text_{uuid.uuid4().hex[:8]}",
            object_type=ObjectType.TEXT,
            x=float(x),
            y=float(y),
            width=float(width),
            height=float(height),
            z_index=z_index,
            text=text,
            font_size=font_size,
            source_confidence=avg_conf
        )
    
    def _detect_text_regions_only(
        self, processed_image: np.ndarray
    ) -> List[TextObject]:
        """テキスト領域のみ検出（内容なし）- 上限付き"""
        text_objects = []
        
        # グレースケール変換
        gray = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY)
        
        # 二値化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # テキスト領域検出（MSER）
        mser = cv2.MSER_create()
        mser.setMinArea(100)  # 最小面積を設定
        mser.setMaxArea(10000)  # 最大面積を設定
        
        try:
            regions, _ = mser.detectRegions(gray)
        except:
            return text_objects
        
        if not regions:
            return text_objects
        
        # 領域をグループ化してテキストブロックを形成
        hulls = [cv2.convexHull(p.reshape(-1, 1, 2)) for p in regions]
        
        # 重複除去と統合
        merged_boxes = self._merge_text_regions(hulls, processed_image.shape)
        
        # 最大30個まで
        merged_boxes = merged_boxes[:30]
        
        z_index = 100
        for box in merged_boxes:
            x, y, w, h = box
            # 極端に小さいまたは大きいボックスをスキップ
            if w < 20 or h < 10 or w > processed_image.shape[1] * 0.9:
                continue
            
            text_obj = TextObject(
                object_id=f"text_{uuid.uuid4().hex[:8]}",
                object_type=ObjectType.TEXT,
                x=float(x),
                y=float(y),
                width=float(w),
                height=float(h),
                z_index=z_index,
                text="",  # 空のテキスト（OCR不可時）
                font_size=12.0,
                source_confidence=0.3
            )
            text_objects.append(text_obj)
            z_index += 1
        
        return text_objects
    
    def _merge_text_regions(
        self, hulls: List, image_shape: tuple
    ) -> List[tuple]:
        """テキスト領域を統合"""
        if not hulls:
            return []
        
        # 各hullのバウンディングボックスを取得
        boxes = []
        for hull in hulls:
            x, y, w, h = cv2.boundingRect(hull)
            # 小さすぎる領域を除外
            if w > 10 and h > 5:
                boxes.append([x, y, x + w, y + h])
        
        if not boxes:
            return []
        
        # Non-Maximum Suppressionで重複除去
        boxes_array = np.array(boxes)
        merged = self._non_max_suppression(boxes_array, 0.5)
        
        # x, y, w, h形式に変換
        result = []
        for box in merged:
            x1, y1, x2, y2 = box
            result.append((x1, y1, x2 - x1, y2 - y1))
        
        return result
    
    def _non_max_suppression(
        self, boxes: np.ndarray, overlap_thresh: float
    ) -> List[tuple]:
        """Non-Maximum Suppression"""
        if len(boxes) == 0:
            return []
        
        boxes = boxes.astype(float)
        
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        
        area = (x2 - x1) * (y2 - y1)
        idxs = np.argsort(y2)
        
        pick = []
        
        while len(idxs) > 0:
            last = len(idxs) - 1
            i = idxs[last]
            pick.append(i)
            
            xx1 = np.maximum(x1[i], x1[idxs[:last]])
            yy1 = np.maximum(y1[i], y1[idxs[:last]])
            xx2 = np.minimum(x2[i], x2[idxs[:last]])
            yy2 = np.minimum(y2[i], y2[idxs[:last]])
            
            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            
            overlap = (w * h) / area[idxs[:last]]
            
            idxs = np.delete(
                idxs, 
                np.concatenate(([last], np.where(overlap > overlap_thresh)[0]))
            )
        
        return [tuple(boxes[i].astype(int)) for i in pick]
    
    def _estimate_font_size(self, box_height: float, text_length: int) -> float:
        """フォントサイズを推定"""
        # 1行と仮定した場合の推定
        # 日本語1文字 ≈ フォントサイズのピクセル
        estimated = box_height * 0.75  # ベースライン調整
        
        # 妥当な範囲に制限
        return max(8.0, min(72.0, estimated))
    
    def _estimate_alignment(self, paragraph) -> TextAlignment:
        """テキストアライメントを推定"""
        # 段落の位置から推定（簡易版）
        # 実際にはページ幅との比較が必要
        return TextAlignment.LEFT
