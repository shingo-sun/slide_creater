"""
Magic Layers風レイヤー分解サービス
Claude Vision APIを使用して画像を編集可能なレイヤーに分解
"""
import os
import base64
import httpx
import cv2
import numpy as np
import json
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class LayerElement:
    """分解されたレイヤー要素"""
    layer_id: str
    element_type: str  # text, shape, image, icon, line, arrow
    x: int
    y: int
    width: int
    height: int
    z_index: int
    description: str
    content: Optional[str] = None  # テキスト要素の場合の内容
    color: Optional[str] = None    # 主要色（HEX）
    image_path: Optional[str] = None  # 切り出し画像パス
    confidence: float = 0.8
    # 編集可能な要素の詳細情報
    shape_type: Optional[str] = None  # rectangle, rounded_rectangle, ellipse, line, arrow, triangle
    fill_color: Optional[str] = None  # 塗りつぶし色（HEX）
    border_color: Optional[str] = None  # 線の色（HEX）
    border_width: Optional[float] = None  # 線の太さ（ピクセル）
    font_size: Optional[int] = None  # フォントサイズ（ポイント）
    font_color: Optional[str] = None  # フォント色（HEX）
    font_bold: Optional[bool] = None  # 太字かどうか
    text_align: Optional[str] = None  # left, center, right
    is_editable: bool = False  # PPTXで編集可能な要素か（text, shapeの場合True）


@dataclass
class DecompositionResult:
    """分解結果"""
    file_id: str
    original_width: int
    original_height: int
    layers: List[LayerElement]
    background_color: Optional[str]
    output_dir: str
    metadata_path: str
    success: bool
    message: str


class LayerDecomposer:
    """Magic Layers風レイヤー分解サービス"""
    
    def __init__(self, output_base_dir: str = "outputs"):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
    def _encode_image(self, image_path: str) -> str:
        """画像をBase64エンコード"""
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")
    
    def _get_media_type(self, image_path: str) -> str:
        """画像のメディアタイプを取得"""
        ext = Path(image_path).suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        return media_types.get(ext, "image/jpeg")
    
    async def decompose(self, image_path: str, file_id: str) -> DecompositionResult:
        """
        画像を編集可能なレイヤーに分解
        
        Args:
            image_path: 入力画像パス
            file_id: ファイルID
            
        Returns:
            DecompositionResult
        """
        # 出力ディレクトリ作成
        output_dir = self.output_base_dir / f"{file_id}_layers"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 元画像情報取得
        image = cv2.imread(image_path)
        if image is None:
            return DecompositionResult(
                file_id=file_id,
                original_width=0,
                original_height=0,
                layers=[],
                background_color=None,
                output_dir=str(output_dir),
                metadata_path="",
                success=False,
                message=f"画像を読み込めません: {image_path}"
            )
        
        original_height, original_width = image.shape[:2]
        
        # Phase 1: Claude Vision APIで要素検出
        detected_elements = await self._detect_elements_with_ai(image_path, original_width, original_height)
        
        if not detected_elements:
            logger.warning("AI要素検出に失敗。OpenCVフォールバックを使用")
            detected_elements = self._detect_elements_with_opencv(image)
        
        # Phase 2: 境界精密化
        refined_elements = self._refine_boundaries(image, detected_elements)
        
        # Phase 3: 各要素を透過PNGとして切り出し
        layers = self._extract_layers(image, refined_elements, output_dir, file_id)
        
        # 背景色推定
        background_color = self._estimate_background_color(image)
        
        # Phase 4: メタデータJSON出力
        metadata_path = output_dir / "layers_metadata.json"
        self._save_metadata(layers, original_width, original_height, background_color, metadata_path)
        
        return DecompositionResult(
            file_id=file_id,
            original_width=original_width,
            original_height=original_height,
            layers=layers,
            background_color=background_color,
            output_dir=str(output_dir),
            metadata_path=str(metadata_path),
            success=True,
            message=f"{len(layers)}個のレイヤーを検出しました"
        )
    
    async def _detect_elements_with_ai(
        self, 
        image_path: str, 
        width: int, 
        height: int
    ) -> List[Dict[str, Any]]:
        """Claude Vision APIで要素を検出"""
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY が設定されていません")
            return []
        
        image_b64 = self._encode_image(image_path)
        media_type = self._get_media_type(image_path)
        
        system_prompt = f"""あなたはスライド画像の要素分析エキスパートです。
提供された画像を分析し、含まれるすべての視覚要素を特定してください。
重要: PowerPointで編集可能な形式に変換するため、テキストと図形を正確に分類してください。

画像サイズ: {width}x{height}ピクセル

各要素について、以下の情報を特定してください：

【要素タイプの分類】
- "text": テキストのみ（編集可能なテキストボックスとして出力）
- "shape": 図形（四角形、角丸、円、線など - PowerPointシェイプとして出力）
- "line": 直線・線分
- "arrow": 矢印
- "image": 写真・複雑な画像（PNG画像として出力）
- "icon": アイコン・ロゴ（PNG画像として出力）

【テキスト要素の場合】
- content: テキストの正確な内容（改行は\\nで）
- font_size: 推定フォントサイズ（ポイント単位）
- font_color: フォント色（HEX）
- font_bold: 太字かどうか
- text_align: "left", "center", "right"

【図形要素（shape, line, arrow）の場合】
- shape_type: "rectangle", "rounded_rectangle", "ellipse", "line", "arrow", "triangle"
- fill_color: 塗りつぶし色（HEX、透明の場合null）
- border_color: 線の色（HEX、線なしの場合null）
- border_width: 線の太さ（ピクセル）

結果は以下のJSON形式で返してください：
{{
    "elements": [
        {{
            "element_type": "shape",
            "shape_type": "rectangle",
            "x": 0,
            "y": 0,
            "width": {width},
            "height": 80,
            "z_index": 1,
            "description": "青色のタイトル帯",
            "fill_color": "#0066CC",
            "border_color": null,
            "border_width": 0
        }},
        {{
            "element_type": "text",
            "x": 50,
            "y": 20,
            "width": 400,
            "height": 50,
            "z_index": 5,
            "description": "タイトルテキスト",
            "content": "プレゼンテーションタイトル",
            "font_size": 32,
            "font_color": "#FFFFFF",
            "font_bold": true,
            "text_align": "left"
        }},
        {{
            "element_type": "shape",
            "shape_type": "rounded_rectangle",
            "x": 100,
            "y": 200,
            "width": 200,
            "height": 120,
            "z_index": 2,
            "description": "角丸の青いボックス",
            "fill_color": "#4A90D9",
            "border_color": "#2E5C8A",
            "border_width": 2
        }},
        {{
            "element_type": "line",
            "shape_type": "line",
            "x": 50,
            "y": 300,
            "width": 500,
            "height": 2,
            "z_index": 3,
            "description": "区切り線",
            "fill_color": null,
            "border_color": "#CCCCCC",
            "border_width": 1
        }},
        {{
            "element_type": "image",
            "x": 600,
            "y": 150,
            "width": 300,
            "height": 200,
            "z_index": 4,
            "description": "製品写真"
        }}
    ],
    "background_color": "#FFFFFF"
}}

注意点：
- 座標は必ずピクセル単位で指定
- テキストは必ず別要素として検出（図形上にテキストがある場合、図形とテキストを分離）
- テキストのcontent（内容）は正確に読み取る
- 単色の四角形や帯は shape (rectangle) として検出
- 複雑な画像やグラデーションは image として検出
- すべての視覚要素を漏れなく検出
- 重なり合う要素はz_indexで前後関係を表現
"""

        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_b64
                }
            },
            {
                "type": "text",
                "text": "この画像に含まれるすべての視覚要素を分析し、JSON形式で返してください。"
            }
        ]
        
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 4096,
                        "system": system_prompt,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_content
                            }
                        ]
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Claude API エラー: {response.status_code} - {response.text}")
                    return []
                
                result = response.json()
                content = result["content"][0]["text"]
                
                # JSONを抽出
                return self._parse_elements_response(content)
                
        except Exception as e:
            logger.error(f"AI要素検出エラー: {e}")
            return []
    
    def _parse_elements_response(self, content: str) -> List[Dict[str, Any]]:
        """AI応答から要素リストをパース（堅牢なJSON修復付き）"""
        import re
        
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                
                # JSON修復を試みる
                json_str = self._repair_json(json_str)
                
                data = json.loads(json_str)
                elements = data.get("elements", [])
                logger.info(f"AI検出成功: {len(elements)}個の要素")
                return elements
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            # 部分的なelementsだけ抽出を試みる
            return self._extract_elements_fallback(content)
        
        return []
    
    def _repair_json(self, json_str: str) -> str:
        """よくあるJSON問題を修復"""
        import re
        
        # 制御文字を除去（改行・タブは保持）
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
        
        # 末尾カンマを修正: },] → }] や ,} → }
        json_str = re.sub(r',\s*]', ']', json_str)
        json_str = re.sub(r',\s*}', '}', json_str)
        
        # 欠落したカンマを追加: }{ → },{  や ][ → ],[
        json_str = re.sub(r'}\s*{', '},{', json_str)
        json_str = re.sub(r']\s*\[', '],[', json_str)
        
        # 文字列内の改行をエスケープ
        # "..." 内の生の改行を \n に置換
        def escape_newlines_in_strings(match):
            s = match.group(0)
            return s.replace('\n', '\\n').replace('\r', '\\r')
        
        json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', escape_newlines_in_strings, json_str)
        
        return json_str
    
    def _extract_elements_fallback(self, content: str) -> List[Dict[str, Any]]:
        """JSONパース失敗時に部分的な要素を抽出"""
        import re
        elements = []
        
        # element_typeとx,y,width,heightを持つオブジェクトを正規表現で抽出
        pattern = r'\{\s*"element_type"\s*:\s*"([^"]+)"[^}]*"x"\s*:\s*(\d+)[^}]*"y"\s*:\s*(\d+)[^}]*"width"\s*:\s*(\d+)[^}]*"height"\s*:\s*(\d+)[^}]*\}'
        
        for match in re.finditer(pattern, content, re.DOTALL):
            try:
                elem = {
                    "element_type": match.group(1),
                    "x": int(match.group(2)),
                    "y": int(match.group(3)),
                    "width": int(match.group(4)),
                    "height": int(match.group(5)),
                    "z_index": len(elements) + 1,
                    "description": f"{match.group(1)}要素"
                }
                elements.append(elem)
            except (ValueError, IndexError):
                continue
        
        if elements:
            logger.info(f"フォールバック抽出: {len(elements)}個の要素")
        
        return elements
    
    def _detect_elements_with_opencv(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """OpenCVによるフォールバック要素検出"""
        elements = []
        height, width = image.shape[:2]
        
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150)
        
        # 膨張処理
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        # 輪郭検出
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        z_index = 1
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 500:  # 小さすぎる要素を除外
                continue
            if area > width * height * 0.9:  # 画像全体を覆う要素を除外
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # 要素タイプを推定
            aspect_ratio = w / h if h > 0 else 1
            element_type = self._estimate_element_type(image, x, y, w, h, aspect_ratio)
            
            # 主要色を抽出
            roi = image[y:y+h, x:x+w]
            color = self._get_dominant_color(roi)
            
            elements.append({
                "element_type": element_type,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "z_index": z_index,
                "description": f"{element_type}要素",
                "content": None,
                "color": color
            })
            z_index += 1
        
        return elements
    
    def _estimate_element_type(
        self, 
        image: np.ndarray, 
        x: int, y: int, w: int, h: int,
        aspect_ratio: float
    ) -> str:
        """要素タイプを推定"""
        height, width = image.shape[:2]
        
        # タイトル帯（上部の横長要素）
        if y < height * 0.15 and w > width * 0.5 and aspect_ratio > 3:
            return "title_band"
        
        # 横長の細い要素は線
        if aspect_ratio > 5 or aspect_ratio < 0.2:
            return "connector"
        
        # 小さい正方形に近い要素はアイコン
        if w < 100 and h < 100 and 0.7 < aspect_ratio < 1.3:
            return "icon"
        
        # デフォルトは図形
        return "shape"
    
    def _get_dominant_color(self, roi: np.ndarray) -> str:
        """ROIの主要色を取得"""
        if roi.size == 0:
            return "#FFFFFF"
        
        # 色をクラスタリング
        pixels = roi.reshape(-1, 3)
        pixels = np.float32(pixels)
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        k = 1
        _, _, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        dominant = centers[0].astype(int)
        # BGR -> RGB
        return f"#{dominant[2]:02x}{dominant[1]:02x}{dominant[0]:02x}"
    
    def _refine_boundaries(
        self, 
        image: np.ndarray, 
        elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """境界を検証・クリップ（AIの座標をそのまま使用）"""
        height, width = image.shape[:2]
        refined = []
        
        for elem in elements:
            x = max(0, int(elem.get("x", 0)))
            y = max(0, int(elem.get("y", 0)))
            w = int(elem.get("width", 100))
            h = int(elem.get("height", 100))
            
            # 境界チェック（画像外にはみ出さないように）
            x = min(x, width - 1)
            y = min(y, height - 1)
            w = min(w, width - x)
            h = min(h, height - y)
            
            # 最小サイズ保証
            w = max(w, 10)
            h = max(h, 10)
            
            if w <= 0 or h <= 0:
                continue
            
            # AIの座標をそのまま使用（OpenCVによる精密化はスキップ）
            refined_elem = elem.copy()
            refined_elem.update({
                "x": x,
                "y": y,
                "width": w,
                "height": h
            })
            refined.append(refined_elem)
        
        return refined
    
    def _refine_single_boundary(
        self, 
        roi: np.ndarray, 
        offset_x: int, 
        offset_y: int
    ) -> Tuple[int, int, int, int]:
        """単一要素の境界を精密化"""
        if roi.size == 0:
            return (offset_x, offset_y, roi.shape[1] if len(roi.shape) > 1 else 0, roi.shape[0])
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 100)
        
        # 輪郭検出
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return (offset_x, offset_y, roi.shape[1], roi.shape[0])
        
        # 最大輪郭のバウンディングボックス
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        
        return (offset_x + x, offset_y + y, w, h)
    
    def _extract_layers(
        self, 
        image: np.ndarray, 
        elements: List[Dict[str, Any]],
        output_dir: Path,
        file_id: str
    ) -> List[LayerElement]:
        """各要素を透過PNGとして切り出し（テキストと図形は編集可能情報も保存）"""
        layers = []
        height, width = image.shape[:2]
        
        for i, elem in enumerate(elements):
            x = int(elem.get("x", 0))
            y = int(elem.get("y", 0))
            w = int(elem.get("width", 100))
            h = int(elem.get("height", 100))
            
            # 境界チェック
            x = max(0, min(x, width - 1))
            y = max(0, min(y, height - 1))
            w = min(w, width - x)
            h = min(h, height - y)
            
            if w <= 0 or h <= 0:
                continue
            
            element_type = elem.get("element_type", "image")
            
            # テキストと図形は編集可能
            is_editable = element_type in ["text", "shape", "line", "arrow"]
            
            # 余白を追加して切り出し
            margin = 2
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(width, x + w + margin)
            y2 = min(height, y + h + margin)
            
            cropped = image[y1:y2, x1:x2].copy()
            
            # 透過マスクを生成
            mask = self._create_element_mask(cropped, element_type)
            
            # BGRA形式に変換
            if cropped.shape[2] == 3:
                cropped_rgba = cv2.cvtColor(cropped, cv2.COLOR_BGR2BGRA)
            else:
                cropped_rgba = cropped.copy()
            
            # マスクをアルファチャンネルに適用
            cropped_rgba[:, :, 3] = mask
            
            # 保存
            layer_id = f"layer_{i:03d}_{uuid.uuid4().hex[:6]}"
            filename = f"{layer_id}.png"
            filepath = output_dir / filename
            cv2.imwrite(str(filepath), cropped_rgba)
            
            # LayerElement作成（新しいフィールドも含む）
            layer = LayerElement(
                layer_id=layer_id,
                element_type=element_type,
                x=x1,
                y=y1,
                width=x2 - x1,
                height=y2 - y1,
                z_index=elem.get("z_index", i),
                description=elem.get("description", ""),
                content=elem.get("content"),
                color=elem.get("color"),
                image_path=str(filepath),
                confidence=elem.get("confidence", 0.8),
                # 編集可能な要素の詳細情報
                shape_type=elem.get("shape_type"),
                fill_color=elem.get("fill_color"),
                border_color=elem.get("border_color"),
                border_width=elem.get("border_width"),
                font_size=elem.get("font_size"),
                font_color=elem.get("font_color"),
                font_bold=elem.get("font_bold"),
                text_align=elem.get("text_align"),
                is_editable=is_editable
            )
            layers.append(layer)
        
        # Z-indexでソート
        layers.sort(key=lambda x: x.z_index)
        
        return layers
    
    def _create_element_mask(self, roi: np.ndarray, element_type: str) -> np.ndarray:
        """要素のマスクを生成（シンプルな背景除去）"""
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
    
    def _estimate_background_color(self, image: np.ndarray) -> str:
        """背景色を推定"""
        height, width = image.shape[:2]
        
        # 四隅と辺からサンプリング
        samples = []
        margin = 10
        
        # 四隅
        samples.extend(image[0:margin, 0:margin].reshape(-1, 3).tolist())
        samples.extend(image[0:margin, -margin:].reshape(-1, 3).tolist())
        samples.extend(image[-margin:, 0:margin].reshape(-1, 3).tolist())
        samples.extend(image[-margin:, -margin:].reshape(-1, 3).tolist())
        
        # 中央値を背景色とする
        samples = np.array(samples)
        bg_color = np.median(samples, axis=0).astype(int)
        
        return f"#{bg_color[2]:02x}{bg_color[1]:02x}{bg_color[0]:02x}"
    
    def _save_metadata(
        self, 
        layers: List[LayerElement],
        original_width: int,
        original_height: int,
        background_color: Optional[str],
        metadata_path: Path
                try:
                    result = response.json()
                    content = result["content"][0]["text"]
                except Exception as e:
                    logger.error(f"Claude API レスポンスJSON解析エラー: {e}")
                    logger.error(f"Status: {response.status_code}")
                    logger.error(f"Headers: {response.headers}")
                    logger.error(f"Text: {response.text}")
                    return []
                try:
                    # JSONを抽出
                    return self._parse_elements_response(content)
                except Exception as e:
                    logger.error(f"_parse_elements_responseでエラー: {e}")
                    logger.error(f"content: {content}")
                    return []
        
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"メタデータを保存: {metadata_path}")


# シングルトンインスタンス - 絶対パスを使用
BASE_DIR = Path(__file__).resolve().parent.parent.parent
layer_decomposer = LayerDecomposer(output_base_dir=str(BASE_DIR / "outputs"))
