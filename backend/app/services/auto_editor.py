"""
自動再編集エンジン
AI分析結果に基づいてPPTXを自動修正
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import copy

logger = logging.getLogger(__name__)


@dataclass
class EditAction:
    """編集アクション"""
    action_type: str  # move, resize, recolor, add, remove, edit_text
    target_type: str  # text, shape, line, arrow
    target_index: int  # 対象オブジェクトのインデックス
    parameters: Dict[str, Any]
    priority: int
    reason: str


class AutoEditor:
    """自動再編集エンジン"""
    
    def __init__(self):
        self.max_iterations = 3  # 最大編集イテレーション
    
    def apply_corrections(
        self,
        analysis_result: Dict[str, Any],
        ai_corrections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        AI提案の修正を適用
        
        Args:
            analysis_result: 現在の解析結果
            ai_corrections: AIからの修正提案
            
        Returns:
            修正後の解析結果
        """
        result = copy.deepcopy(analysis_result)
        applied_actions = []
        
        # 修正を優先度順にソート
        sorted_corrections = sorted(
            ai_corrections,
            key=lambda c: c.get("priority", 5)
        )
        
        for correction in sorted_corrections:
            action = self._parse_correction(correction)
            if action:
                try:
                    result = self._apply_action(result, action)
                    applied_actions.append({
                        "action": action.action_type,
                        "target": f"{action.target_type}[{action.target_index}]",
                        "reason": action.reason
                    })
                except Exception as e:
                    logger.error(f"修正適用エラー: {e}")
        
        result["_applied_corrections"] = applied_actions
        return result
    
    def _parse_correction(
        self,
        correction: Dict[str, Any]
    ) -> Optional[EditAction]:
        """修正提案をEditActionに変換"""
        try:
            target = correction.get("target", "")
            action = correction.get("action", "")
            params = correction.get("parameters", {})
            priority = correction.get("priority", 5)
            
            # ターゲットタイプとインデックスを抽出
            target_type, target_index = self._parse_target(target)
            
            if not target_type or target_index < 0:
                return None
            
            return EditAction(
                action_type=action,
                target_type=target_type,
                target_index=target_index,
                parameters=params,
                priority=priority,
                reason=correction.get("description", "AI提案による修正")
            )
        except Exception as e:
            logger.error(f"修正パースエラー: {e}")
            return None
    
    def _parse_target(self, target: str) -> tuple:
        """ターゲット文字列をパース"""
        # "text[0]", "shape[1]" などの形式
        target_lower = target.lower()
        
        if "text" in target_lower:
            target_type = "text"
        elif "shape" in target_lower:
            target_type = "shape"
        elif "line" in target_lower:
            target_type = "line"
        elif "arrow" in target_lower:
            target_type = "arrow"
        else:
            return None, -1
        
        # インデックス抽出
        try:
            if "[" in target and "]" in target:
                idx_str = target.split("[")[1].split("]")[0]
                target_index = int(idx_str)
            else:
                target_index = 0
        except (ValueError, IndexError):
            target_index = 0
        
        return target_type, target_index
    
    def _apply_action(
        self,
        result: Dict[str, Any],
        action: EditAction
    ) -> Dict[str, Any]:
        """アクションを適用"""
        # オブジェクトリストを取得
        obj_key = f"{action.target_type}_objects"
        objects = result.get(obj_key, [])
        
        if action.target_index >= len(objects):
            logger.warning(f"インデックス範囲外: {action.target_index}")
            return result
        
        if action.action_type == "move":
            result = self._apply_move(result, obj_key, action)
        elif action.action_type == "resize":
            result = self._apply_resize(result, obj_key, action)
        elif action.action_type == "recolor":
            result = self._apply_recolor(result, obj_key, action)
        elif action.action_type == "edit_text":
            result = self._apply_edit_text(result, obj_key, action)
        elif action.action_type == "remove":
            result = self._apply_remove(result, obj_key, action)
        elif action.action_type == "add":
            result = self._apply_add(result, obj_key, action)
        
        return result
    
    def _apply_move(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """移動を適用"""
        obj = result[obj_key][action.target_index]
        
        if "x" in action.parameters:
            obj["x"] = action.parameters["x"]
        if "y" in action.parameters:
            obj["y"] = action.parameters["y"]
        if "dx" in action.parameters:
            obj["x"] = obj.get("x", 0) + action.parameters["dx"]
        if "dy" in action.parameters:
            obj["y"] = obj.get("y", 0) + action.parameters["dy"]
        
        return result
    
    def _apply_resize(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """リサイズを適用"""
        obj = result[obj_key][action.target_index]
        
        if "width" in action.parameters:
            obj["width"] = action.parameters["width"]
        if "height" in action.parameters:
            obj["height"] = action.parameters["height"]
        if "scale" in action.parameters:
            scale = action.parameters["scale"]
            obj["width"] = obj.get("width", 100) * scale
            obj["height"] = obj.get("height", 100) * scale
        
        return result
    
    def _apply_recolor(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """色変更を適用"""
        obj = result[obj_key][action.target_index]
        
        if "fill_color" in action.parameters:
            obj["fill_color"] = action.parameters["fill_color"]
        if "text_color" in action.parameters:
            obj["text_color"] = action.parameters["text_color"]
        if "border_color" in action.parameters:
            obj["border_color"] = action.parameters["border_color"]
        
        return result
    
    def _apply_edit_text(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """テキスト編集を適用"""
        obj = result[obj_key][action.target_index]
        
        if "text" in action.parameters:
            obj["text"] = action.parameters["text"]
        if "font_size" in action.parameters:
            obj["font_size"] = action.parameters["font_size"]
        if "font_family" in action.parameters:
            obj["font_family"] = action.parameters["font_family"]
        
        return result
    
    def _apply_remove(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """削除を適用"""
        objects = result[obj_key]
        
        if 0 <= action.target_index < len(objects):
            del objects[action.target_index]
        
        return result
    
    def _apply_add(
        self,
        result: Dict[str, Any],
        obj_key: str,
        action: EditAction
    ) -> Dict[str, Any]:
        """追加を適用"""
        new_obj = action.parameters.copy()
        
        # 必須フィールドのデフォルト値
        new_obj.setdefault("x", 0)
        new_obj.setdefault("y", 0)
        new_obj.setdefault("width", 100)
        new_obj.setdefault("height", 50)
        new_obj.setdefault("z_index", len(result.get(obj_key, [])))
        
        if obj_key not in result:
            result[obj_key] = []
        
        result[obj_key].append(new_obj)
        
        return result
    
    def suggest_automated_fixes(
        self,
        comparison_result: Dict[str, Any],
        analysis_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        比較結果から自動修正を提案
        
        Args:
            comparison_result: 画像比較結果
            analysis_result: 現在の解析結果
            
        Returns:
            修正提案リスト
        """
        suggestions = []
        
        difference_regions = comparison_result.get("difference_regions", [])
        
        for i, region in enumerate(difference_regions):
            suggestion = self._analyze_region_for_fix(
                region, analysis_result, i
            )
            if suggestion:
                suggestions.append(suggestion)
        
        return suggestions
    
    def _analyze_region_for_fix(
        self,
        region: Dict[str, Any],
        analysis_result: Dict[str, Any],
        index: int
    ) -> Optional[Dict[str, Any]]:
        """差分領域から修正提案を生成"""
        diff_type = region.get("type", "unknown")
        severity = region.get("severity", 0)
        x, y = region.get("x", 0), region.get("y", 0)
        w, h = region.get("width", 0), region.get("height", 0)
        
        # 低深刻度はスキップ
        if severity < 0.3:
            return None
        
        # 差分タイプに応じた提案
        if diff_type == "missing":
            return {
                "target": f"region_{index}",
                "action": "investigate",
                "parameters": {
                    "location": {"x": x, "y": y, "width": w, "height": h},
                    "note": "元画像に存在する要素が欠落している可能性"
                },
                "priority": 1,
                "description": f"位置({x},{y})に欠落要素の可能性"
            }
        
        elif diff_type == "extra":
            # 該当位置のオブジェクトを特定
            target_obj = self._find_object_at_position(
                analysis_result, x, y, w, h
            )
            if target_obj:
                return {
                    "target": target_obj["target"],
                    "action": "remove",
                    "parameters": {},
                    "priority": 2,
                    "description": f"余分な要素を削除: {target_obj['target']}"
                }
        
        elif diff_type == "layout":
            target_obj = self._find_object_at_position(
                analysis_result, x, y, w, h
            )
            if target_obj:
                return {
                    "target": target_obj["target"],
                    "action": "move",
                    "parameters": {
                        "note": "位置調整が必要"
                    },
                    "priority": 3,
                    "description": f"レイアウト調整: {target_obj['target']}"
                }
        
        elif diff_type == "color":
            target_obj = self._find_object_at_position(
                analysis_result, x, y, w, h
            )
            if target_obj:
                return {
                    "target": target_obj["target"],
                    "action": "recolor",
                    "parameters": {
                        "note": "色調整が必要"
                    },
                    "priority": 4,
                    "description": f"色調整: {target_obj['target']}"
                }
        
        return None
    
    def _find_object_at_position(
        self,
        analysis_result: Dict[str, Any],
        x: int, y: int, w: int, h: int
    ) -> Optional[Dict[str, Any]]:
        """指定位置のオブジェクトを検索"""
        for obj_type in ["text_objects", "shape_objects", "line_objects"]:
            objects = analysis_result.get(obj_type, [])
            
            for i, obj in enumerate(objects):
                obj_x = obj.get("x", 0)
                obj_y = obj.get("y", 0)
                obj_w = obj.get("width", 0)
                obj_h = obj.get("height", 0)
                
                # 重なりチェック
                if self._rectangles_overlap(
                    x, y, w, h,
                    obj_x, obj_y, obj_w, obj_h
                ):
                    type_name = obj_type.replace("_objects", "")
                    return {
                        "target": f"{type_name}[{i}]",
                        "object": obj
                    }
        
        return None
    
    def _rectangles_overlap(
        self,
        x1: int, y1: int, w1: int, h1: int,
        x2: int, y2: int, w2: int, h2: int
    ) -> bool:
        """矩形が重なるかチェック"""
        return not (
            x1 + w1 < x2 or
            x2 + w2 < x1 or
            y1 + h1 < y2 or
            y2 + h2 < y1
        )


# シングルトンインスタンス
auto_editor = AutoEditor()
