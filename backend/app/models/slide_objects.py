"""
スライドオブジェクトのデータモデル定義
要件定義書 12.2 データ構造に準拠
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum


class ConversionMode(str, Enum):
    FAITHFUL = "faithful"    # 忠実再現モード
    EDITABLE = "editable"    # 編集優先モード
    HYBRID = "hybrid"        # ハイブリッドモード


class ObjectType(str, Enum):
    TEXT = "text"
    RECTANGLE = "rectangle"
    ROUNDED_RECTANGLE = "rounded_rectangle"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    CONNECTOR = "connector"
    CALLOUT = "callout"
    TABLE = "table"
    ICON = "icon"
    IMAGE = "image"
    TITLE_BAND = "title_band"
    HEADING_BOX = "heading_box"


class BlockType(str, Enum):
    TITLE = "title"
    HEADING = "heading"
    BODY = "body"
    PHOTO = "photo"
    SHAPE = "shape"
    FLOW = "flow"
    ICON = "icon"
    NOTE = "note"
    BACKGROUND = "background"


class TextAlignment(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class Color(BaseModel):
    """色情報"""
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)
    a: float = Field(default=1.0, ge=0.0, le=1.0)
    
    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"
    
    def to_rgb_tuple(self) -> tuple:
        return (self.r, self.g, self.b)


class BoundingBox(BaseModel):
    """境界ボックス"""
    x: float
    y: float
    width: float
    height: float
    
    @property
    def x2(self) -> float:
        return self.x + self.width
    
    @property
    def y2(self) -> float:
        return self.y + self.height
    
    @property
    def center_x(self) -> float:
        return self.x + self.width / 2
    
    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


class BaseSlideObject(BaseModel):
    """スライドオブジェクトの基底クラス"""
    object_id: str
    object_type: ObjectType
    x: float
    y: float
    width: float
    height: float
    z_index: int = 0
    rotation: float = 0.0
    group_id: Optional[str] = None
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    editable_flag: bool = True
    fallback_image_flag: bool = False


class TextObject(BaseSlideObject):
    """テキストオブジェクト"""
    object_type: ObjectType = ObjectType.TEXT
    text: str
    font_size: float = 12.0
    font_weight: Literal["normal", "bold"] = "normal"
    font_family: str = "Meiryo"
    text_color: Color = Field(default_factory=lambda: Color(r=0, g=0, b=0))
    alignment: TextAlignment = TextAlignment.LEFT
    line_spacing: float = 1.0
    is_title: bool = False
    is_heading: bool = False
    is_bullet: bool = False
    bullet_level: int = 0


class ShapeObject(BaseSlideObject):
    """図形オブジェクト"""
    fill_color: Optional[Color] = None
    line_color: Optional[Color] = None
    line_width: float = 1.0
    corner_radius: float = 0.0
    transparency: float = 0.0
    has_shadow: bool = False


class RectangleObject(ShapeObject):
    """長方形"""
    object_type: ObjectType = ObjectType.RECTANGLE


class RoundedRectangleObject(ShapeObject):
    """角丸長方形"""
    object_type: ObjectType = ObjectType.ROUNDED_RECTANGLE
    corner_radius: float = 10.0


class CircleObject(ShapeObject):
    """円"""
    object_type: ObjectType = ObjectType.CIRCLE


class EllipseObject(ShapeObject):
    """楕円"""
    object_type: ObjectType = ObjectType.ELLIPSE


class LineObject(ShapeObject):
    """線"""
    object_type: ObjectType = ObjectType.LINE
    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    is_dashed: bool = False


class ArrowObject(LineObject):
    """矢印"""
    object_type: ObjectType = ObjectType.ARROW
    arrow_head: Literal["start", "end", "both"] = "end"
    arrow_style: Literal["triangle", "stealth", "oval"] = "triangle"


class ConnectorObject(BaseSlideObject):
    """コネクタ"""
    object_type: ObjectType = ObjectType.CONNECTOR
    start_shape_id: Optional[str] = None
    end_shape_id: Optional[str] = None
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    line_color: Color = Field(default_factory=lambda: Color(r=0, g=0, b=0))
    line_width: float = 1.0
    connector_type: Literal["straight", "elbow", "curved"] = "straight"
    has_arrow: bool = True


class IconObject(BaseSlideObject):
    """アイコン・ピクト"""
    object_type: ObjectType = ObjectType.ICON
    icon_type: Optional[str] = None  # 推定されたアイコン種別
    image_path: Optional[str] = None  # 切り出し画像パス
    is_vector: bool = False
    original_colors: List[Color] = Field(default_factory=list)


class ImageObject(BaseSlideObject):
    """画像オブジェクト（フォールバック用）"""
    object_type: ObjectType = ObjectType.IMAGE
    image_path: str
    original_width: int
    original_height: int
    crop_x: int = 0
    crop_y: int = 0
    crop_width: Optional[int] = None
    crop_height: Optional[int] = None


class LayoutBlock(BaseModel):
    """レイアウトブロック"""
    block_id: str
    block_type: BlockType
    bounding_box: BoundingBox
    z_index: int = 0
    parent_block_id: Optional[str] = None
    child_block_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ImageInfo(BaseModel):
    """画像情報"""
    width: int
    height: int
    channels: int
    format: str
    dpi: Optional[int] = None


class SlideAnalysisResult(BaseModel):
    """スライド解析結果"""
    file_id: str
    image_info: ImageInfo
    layout_blocks: List[LayoutBlock] = Field(default_factory=list)
    text_objects: List[TextObject] = Field(default_factory=list)
    shape_objects: List[ShapeObject] = Field(default_factory=list)
    icon_objects: List[IconObject] = Field(default_factory=list)
    mode: str = "faithful"
    slide_ratio: str = "16:9"
    
    @property
    def all_objects(self) -> List[BaseSlideObject]:
        """全オブジェクトをz_index順で取得"""
        all_objs = (
            list(self.text_objects) + 
            list(self.shape_objects) + 
            list(self.icon_objects)
        )
        return sorted(all_objs, key=lambda x: x.z_index)
    
    @property
    def editable_rate(self) -> float:
        """編集可能オブジェクト率"""
        all_objs = self.all_objects
        if not all_objs:
            return 0.0
        editable_count = sum(1 for obj in all_objs if obj.editable_flag)
        return editable_count / len(all_objs)


class QualityMetrics(BaseModel):
    """品質評価指標"""
    layout_match_rate: float = 0.0
    text_match_rate: float = 0.0
    shape_reproduction_rate: float = 0.0
    color_match_rate: float = 0.0
    line_reproduction_rate: float = 0.0
    connector_match_rate: float = 0.0
    editable_object_rate: float = 0.0
