"""
AI画像分析サービス
Claude APIを使用して画像の差分を分析し、改善点を提案
"""
import os
import base64
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysisResult:
    """AI分析結果"""
    differences: List[Dict[str, Any]]  # 検出された差分
    corrections: List[Dict[str, Any]]  # 修正提案
    quality_assessment: str  # 品質評価
    detailed_feedback: str  # 詳細フィードバック
    learning_insights: List[Dict[str, Any]]  # 学習用インサイト
    confidence: float  # 分析の信頼度


class AIImageAnalyzer:
    """AI画像分析サービス"""
    
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"
        
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
    
    async def analyze_difference(
        self,
        original_path: str,
        generated_path: str,
        comparison_summary: Optional[str] = None
    ) -> AIAnalysisResult:
        """
        2つの画像の差分をAIで分析
        
        Args:
            original_path: 元画像パス
            generated_path: 生成画像パス
            comparison_summary: 画像比較のサマリー（オプション）
            
        Returns:
            AIAnalysisResult
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY が設定されていません。ダミー分析を返します。")
            return self._create_dummy_result()
        
        # 画像をエンコード
        original_b64 = self._encode_image(original_path)
        generated_b64 = self._encode_image(generated_path)
        
        original_media_type = self._get_media_type(original_path)
        generated_media_type = self._get_media_type(generated_path)
        
        # プロンプト構築
        system_prompt = """あなたはスライド画像の品質分析エキスパートです。
元のスライド画像と、それを再構成して生成したスライド画像を比較し、差分を詳細に分析してください。

分析結果は以下のJSON形式で返してください：
{
    "differences": [
        {
            "location": "画像内の位置（例: 左上、中央など）",
            "type": "差分タイプ（text/shape/color/layout/missing/extra）",
            "original": "元画像での状態",
            "generated": "生成画像での状態",
            "severity": "深刻度（high/medium/low）"
        }
    ],
    "corrections": [
        {
            "target": "修正対象",
            "action": "修正アクション（move/resize/recolor/add/remove/edit_text）",
            "parameters": {
                "具体的なパラメータ": "値"
            },
            "priority": "優先度（1-5、1が最高）"
        }
    ],
    "quality_assessment": "全体の品質評価（excellent/good/fair/poor）",
    "detailed_feedback": "詳細なフィードバック文章",
    "learning_insights": [
        {
            "pattern": "検出されたエラーパターン",
            "cause": "推定される原因",
            "prevention": "今後の防止策"
        }
    ],
    "confidence": 0.0-1.0の信頼度
}"""

        user_content = []
        
        # 元画像
        user_content.append({
            "type": "text",
            "text": "【元のスライド画像】"
        })
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": original_media_type,
                "data": original_b64
            }
        })
        
        # 生成画像
        user_content.append({
            "type": "text",
            "text": "【生成されたスライド画像】"
        })
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": generated_media_type,
                "data": generated_b64
            }
        })
        
        # 追加コンテキスト
        analysis_request = "上記2つの画像を比較し、差分を詳細に分析してください。"
        if comparison_summary:
            analysis_request += f"\n\n参考情報（画像処理による差分検出結果）:\n{comparison_summary}"
        
        user_content.append({
            "type": "text",
            "text": analysis_request
        })
        
        # API呼び出し
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
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
                    return self._create_dummy_result()
                
                result = response.json()
                content = result["content"][0]["text"]
                
                # JSONを抽出
                return self._parse_ai_response(content)
                
        except Exception as e:
            logger.error(f"AI分析エラー: {e}")
            return self._create_dummy_result()
    
    def _parse_ai_response(self, content: str) -> AIAnalysisResult:
        """AI応答をパース"""
        try:
            # JSON部分を抽出
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                
                return AIAnalysisResult(
                    differences=data.get("differences", []),
                    corrections=data.get("corrections", []),
                    quality_assessment=data.get("quality_assessment", "unknown"),
                    detailed_feedback=data.get("detailed_feedback", ""),
                    learning_insights=data.get("learning_insights", []),
                    confidence=data.get("confidence", 0.5)
                )
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
        
        # パース失敗時はテキストをそのまま使用
        return AIAnalysisResult(
            differences=[],
            corrections=[],
            quality_assessment="unknown",
            detailed_feedback=content,
            learning_insights=[],
            confidence=0.3
        )
    
    def _create_dummy_result(self) -> AIAnalysisResult:
        """APIキーがない場合のダミー結果"""
        return AIAnalysisResult(
            differences=[
                {
                    "location": "不明",
                    "type": "unknown",
                    "original": "API未設定のため分析不可",
                    "generated": "API未設定のため分析不可",
                    "severity": "unknown"
                }
            ],
            corrections=[],
            quality_assessment="unknown",
            detailed_feedback="ANTHROPIC_API_KEYが設定されていないため、AI分析を実行できません。"
                             "環境変数にAPIキーを設定してください。",
            learning_insights=[],
            confidence=0.0
        )
    
    async def suggest_improvements(
        self,
        analysis_result: Dict[str, Any],
        original_path: str
    ) -> List[Dict[str, Any]]:
        """
        解析結果に基づく改善提案を生成
        
        Args:
            analysis_result: 現在の解析結果
            original_path: 元画像パス
            
        Returns:
            改善提案のリスト
        """
        if not self.api_key:
            return []
        
        original_b64 = self._encode_image(original_path)
        original_media_type = self._get_media_type(original_path)
        
        system_prompt = """あなたはスライド再構成の改善エキスパートです。
元のスライド画像と現在の解析結果を見て、より正確な再構成のための改善提案を行ってください。

以下のJSON形式で返してください：
{
    "improvements": [
        {
            "target": "改善対象（例: text_detection, shape_detection, layout）",
            "current_issue": "現在の問題点",
            "suggestion": "改善提案",
            "expected_impact": "期待される効果（high/medium/low）"
        }
    ]
}"""
        
        user_content = [
            {
                "type": "text",
                "text": "【元のスライド画像】"
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": original_media_type,
                    "data": original_b64
                }
            },
            {
                "type": "text",
                "text": f"【現在の解析結果】\n{json.dumps(analysis_result, ensure_ascii=False, indent=2)}\n\nこの解析結果を改善するための提案をしてください。"
            }
        ]
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 2048,
                        "system": system_prompt,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_content
                            }
                        ]
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["content"][0]["text"]
                    
                    json_start = content.find("{")
                    json_end = content.rfind("}") + 1
                    
                    if json_start >= 0:
                        data = json.loads(content[json_start:json_end])
                        return data.get("improvements", [])
                        
        except Exception as e:
            logger.error(f"改善提案エラー: {e}")
        
        return []


# シングルトンインスタンス
ai_image_analyzer = AIImageAnalyzer()
