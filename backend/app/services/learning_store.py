"""
学習データストア
間違いパターンを蓄積し、次回の生成に活用
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ErrorPattern:
    """エラーパターン"""
    id: str
    pattern_type: str  # text_detection, shape_detection, layout, color, etc.
    description: str
    original_state: Dict[str, Any]  # 元画像での状態
    incorrect_state: Dict[str, Any]  # 誤った生成結果
    correct_state: Dict[str, Any]  # 正しい状態
    frequency: int  # 発生回数
    last_occurred: str  # 最終発生日時
    prevention_rule: Optional[str]  # 防止ルール
    confidence: float  # パターンの信頼度


@dataclass
class LearningEntry:
    """学習エントリ"""
    id: str
    timestamp: str
    original_image_hash: str
    similarity_score: float
    error_patterns: List[str]  # ErrorPattern IDs
    ai_feedback: Dict[str, Any]
    corrections_applied: List[Dict[str, Any]]
    result_improvement: float  # 改善率


class LearningDataStore:
    """学習データストア"""
    
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "data", "learning"
            )
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.patterns_file = self.storage_dir / "error_patterns.json"
        self.entries_file = self.storage_dir / "learning_entries.json"
        self.rules_file = self.storage_dir / "prevention_rules.json"
        
        self._load_data()
    
    def _load_data(self):
        """データを読み込み"""
        self.error_patterns: Dict[str, ErrorPattern] = {}
        self.learning_entries: List[LearningEntry] = []
        self.prevention_rules: Dict[str, Dict[str, Any]] = {}
        
        # エラーパターン読み込み
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        pattern = ErrorPattern(**item)
                        self.error_patterns[pattern.id] = pattern
            except Exception as e:
                logger.error(f"エラーパターン読み込みエラー: {e}")
        
        # 学習エントリ読み込み
        if self.entries_file.exists():
            try:
                with open(self.entries_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.learning_entries = [LearningEntry(**item) for item in data]
            except Exception as e:
                logger.error(f"学習エントリ読み込みエラー: {e}")
        
        # 防止ルール読み込み
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    self.prevention_rules = json.load(f)
            except Exception as e:
                logger.error(f"防止ルール読み込みエラー: {e}")
    
    def _save_data(self):
        """データを保存"""
        # エラーパターン保存
        with open(self.patterns_file, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(p) for p in self.error_patterns.values()],
                f, ensure_ascii=False, indent=2
            )
        
        # 学習エントリ保存
        with open(self.entries_file, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(e) for e in self.learning_entries],
                f, ensure_ascii=False, indent=2
            )
        
        # 防止ルール保存
        with open(self.rules_file, "w", encoding="utf-8") as f:
            json.dump(self.prevention_rules, f, ensure_ascii=False, indent=2)
    
    def _generate_pattern_id(self, pattern_type: str, description: str) -> str:
        """パターンIDを生成"""
        content = f"{pattern_type}:{description}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _generate_entry_id(self) -> str:
        """エントリIDを生成"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"entry_{timestamp}"
    
    def add_error_pattern(
        self,
        pattern_type: str,
        description: str,
        original_state: Dict[str, Any],
        incorrect_state: Dict[str, Any],
        correct_state: Dict[str, Any],
        prevention_rule: Optional[str] = None
    ) -> ErrorPattern:
        """
        エラーパターンを追加または更新
        
        Args:
            pattern_type: パターンタイプ
            description: 説明
            original_state: 元の状態
            incorrect_state: 誤った状態
            correct_state: 正しい状態
            prevention_rule: 防止ルール
            
        Returns:
            追加/更新されたErrorPattern
        """
        pattern_id = self._generate_pattern_id(pattern_type, description)
        
        if pattern_id in self.error_patterns:
            # 既存パターンを更新
            pattern = self.error_patterns[pattern_id]
            pattern.frequency += 1
            pattern.last_occurred = datetime.now().isoformat()
            pattern.confidence = min(pattern.confidence + 0.05, 1.0)
            
            if prevention_rule:
                pattern.prevention_rule = prevention_rule
        else:
            # 新規パターン追加
            pattern = ErrorPattern(
                id=pattern_id,
                pattern_type=pattern_type,
                description=description,
                original_state=original_state,
                incorrect_state=incorrect_state,
                correct_state=correct_state,
                frequency=1,
                last_occurred=datetime.now().isoformat(),
                prevention_rule=prevention_rule,
                confidence=0.5
            )
            self.error_patterns[pattern_id] = pattern
        
        self._save_data()
        return pattern
    
    def add_learning_entry(
        self,
        original_image_path: str,
        similarity_score: float,
        error_pattern_ids: List[str],
        ai_feedback: Dict[str, Any],
        corrections_applied: List[Dict[str, Any]],
        result_improvement: float
    ) -> LearningEntry:
        """
        学習エントリを追加
        
        Args:
            original_image_path: 元画像パス
            similarity_score: 類似度スコア
            error_pattern_ids: 関連エラーパターンID
            ai_feedback: AIフィードバック
            corrections_applied: 適用された修正
            result_improvement: 改善率
            
        Returns:
            追加されたLearningEntry
        """
        # 画像ハッシュ計算
        with open(original_image_path, "rb") as f:
            image_hash = hashlib.md5(f.read()).hexdigest()
        
        entry = LearningEntry(
            id=self._generate_entry_id(),
            timestamp=datetime.now().isoformat(),
            original_image_hash=image_hash,
            similarity_score=similarity_score,
            error_patterns=error_pattern_ids,
            ai_feedback=ai_feedback,
            corrections_applied=corrections_applied,
            result_improvement=result_improvement
        )
        
        self.learning_entries.append(entry)
        
        # 最大1000エントリに制限
        if len(self.learning_entries) > 1000:
            self.learning_entries = self.learning_entries[-1000:]
        
        self._save_data()
        return entry
    
    def get_relevant_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_frequency: int = 1,
        min_confidence: float = 0.0
    ) -> List[ErrorPattern]:
        """
        関連するエラーパターンを取得
        
        Args:
            pattern_type: フィルタするパターンタイプ
            min_frequency: 最小発生回数
            min_confidence: 最小信頼度
            
        Returns:
            ErrorPatternのリスト
        """
        patterns = []
        
        for pattern in self.error_patterns.values():
            if pattern_type and pattern.pattern_type != pattern_type:
                continue
            if pattern.frequency < min_frequency:
                continue
            if pattern.confidence < min_confidence:
                continue
            
            patterns.append(pattern)
        
        # 頻度と信頼度でソート
        patterns.sort(
            key=lambda p: (p.frequency * p.confidence),
            reverse=True
        )
        
        return patterns
    
    def get_prevention_rules(
        self,
        pattern_types: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        防止ルールを取得
        
        Args:
            pattern_types: フィルタするパターンタイプ
            
        Returns:
            パターンタイプごとの防止ルールリスト
        """
        rules: Dict[str, List[str]] = {}
        
        for pattern in self.error_patterns.values():
            if pattern.prevention_rule:
                if pattern_types and pattern.pattern_type not in pattern_types:
                    continue
                
                if pattern.pattern_type not in rules:
                    rules[pattern.pattern_type] = []
                
                rules[pattern.pattern_type].append(pattern.prevention_rule)
        
        return rules
    
    def get_statistics(self) -> Dict[str, Any]:
        """学習データの統計を取得"""
        total_patterns = len(self.error_patterns)
        total_entries = len(self.learning_entries)
        
        # パターンタイプ別集計
        type_counts = {}
        for pattern in self.error_patterns.values():
            type_counts[pattern.pattern_type] = type_counts.get(
                pattern.pattern_type, 0
            ) + 1
        
        # 平均改善率
        if self.learning_entries:
            avg_improvement = sum(
                e.result_improvement for e in self.learning_entries
            ) / len(self.learning_entries)
        else:
            avg_improvement = 0.0
        
        # 高頻度パターン
        top_patterns = sorted(
            self.error_patterns.values(),
            key=lambda p: p.frequency,
            reverse=True
        )[:5]
        
        return {
            "total_patterns": total_patterns,
            "total_entries": total_entries,
            "pattern_types": type_counts,
            "average_improvement": avg_improvement,
            "top_frequent_patterns": [
                {
                    "id": p.id,
                    "type": p.pattern_type,
                    "description": p.description,
                    "frequency": p.frequency
                }
                for p in top_patterns
            ]
        }
    
    def apply_learned_rules(
        self,
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        学習したルールを解析結果に適用
        
        Args:
            analysis_result: 現在の解析結果
            
        Returns:
            ルール適用後の解析結果
        """
        # 高信頼度パターンの防止ルールを適用
        high_confidence_patterns = self.get_relevant_patterns(
            min_frequency=3,
            min_confidence=0.7
        )
        
        applied_rules = []
        
        for pattern in high_confidence_patterns:
            if pattern.prevention_rule:
                # ルールに基づいて解析結果を調整
                result = self._apply_single_rule(
                    analysis_result, pattern
                )
                if result:
                    analysis_result = result
                    applied_rules.append({
                        "pattern_id": pattern.id,
                        "rule": pattern.prevention_rule
                    })
        
        # 適用されたルールを記録
        analysis_result["_applied_learning_rules"] = applied_rules
        
        return analysis_result
    
    def _apply_single_rule(
        self,
        analysis_result: Dict[str, Any],
        pattern: ErrorPattern
    ) -> Optional[Dict[str, Any]]:
        """単一ルールを適用"""
        rule = pattern.prevention_rule
        if not rule:
            return None
        
        # ルールの種類に応じた処理
        if "duplicate" in rule.lower():
            # 重複除去ルール
            return self._apply_duplicate_removal(analysis_result, pattern)
        
        if "position" in rule.lower() or "layout" in rule.lower():
            # 位置調整ルール
            return self._apply_position_adjustment(analysis_result, pattern)
        
        if "text" in rule.lower():
            # テキスト調整ルール
            return self._apply_text_adjustment(analysis_result, pattern)
        
        return None
    
    def _apply_duplicate_removal(
        self,
        analysis_result: Dict[str, Any],
        pattern: ErrorPattern
    ) -> Dict[str, Any]:
        """重複除去を適用"""
        # 該当するオブジェクトタイプを特定
        if "line" in pattern.description.lower():
            target_key = "line_objects"
        elif "shape" in pattern.description.lower():
            target_key = "shape_objects"
        else:
            return analysis_result
        
        objects = analysis_result.get(target_key, [])
        if len(objects) <= 1:
            return analysis_result
        
        # 重複を除去（簡易版）
        seen_positions = set()
        unique_objects = []
        
        for obj in objects:
            pos_key = (
                round(obj.get("x", 0) / 10),
                round(obj.get("y", 0) / 10)
            )
            if pos_key not in seen_positions:
                seen_positions.add(pos_key)
                unique_objects.append(obj)
        
        analysis_result[target_key] = unique_objects
        return analysis_result
    
    def _apply_position_adjustment(
        self,
        analysis_result: Dict[str, Any],
        pattern: ErrorPattern
    ) -> Dict[str, Any]:
        """位置調整を適用"""
        # パターンから調整値を抽出
        correct = pattern.correct_state
        incorrect = pattern.incorrect_state
        
        if "x_offset" in correct and "x_offset" in incorrect:
            diff = correct["x_offset"] - incorrect["x_offset"]
            
            for obj_type in ["text_objects", "shape_objects"]:
                for obj in analysis_result.get(obj_type, []):
                    obj["x"] = obj.get("x", 0) + diff
        
        return analysis_result
    
    def _apply_text_adjustment(
        self,
        analysis_result: Dict[str, Any],
        pattern: ErrorPattern
    ) -> Dict[str, Any]:
        """テキスト調整を適用"""
        # 特定のテキストパターンを修正
        incorrect_text = pattern.incorrect_state.get("text", "")
        correct_text = pattern.correct_state.get("text", "")
        
        if incorrect_text and correct_text:
            for obj in analysis_result.get("text_objects", []):
                if obj.get("text") == incorrect_text:
                    obj["text"] = correct_text
        
        return analysis_result


# シングルトンインスタンス
learning_data_store = LearningDataStore()
