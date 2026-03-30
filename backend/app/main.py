"""
Slide Creater - Magic Layers API
画像をレイヤーに分解し、編集可能なPPTXを生成
"""
# 環境変数を.envから読み込み
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uuid
import shutil
import logging
import json
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN

from app.services.layer_decomposer import layer_decomposer

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Slide Creater API",
    description="Magic Layers - 画像をレイヤーに分解しPPTXを生成",
    version="2.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ディレクトリ設定（絶対パス）
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# 静的ファイル配信
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


# ============================================================
# ユーティリティ関数
# ============================================================

def hex_to_rgb(hex_color: str) -> RGBColor:
    """HEXカラーをRGBColorに変換"""
    if not hex_color or not hex_color.startswith("#"):
        return RGBColor(0, 0, 0)
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return RGBColor(r, g, b)


def get_shape_type(shape_type_str: str):
    """文字列からMSO_SHAPEを取得"""
    shape_map = {
        "rectangle": MSO_SHAPE.RECTANGLE,
        "rounded_rectangle": MSO_SHAPE.ROUNDED_RECTANGLE,
        "ellipse": MSO_SHAPE.OVAL,
        "oval": MSO_SHAPE.OVAL,
        "circle": MSO_SHAPE.OVAL,
        "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
        "diamond": MSO_SHAPE.DIAMOND,
        "pentagon": MSO_SHAPE.PENTAGON,
        "hexagon": MSO_SHAPE.HEXAGON,
        "arrow": MSO_SHAPE.RIGHT_ARROW,
        "right_arrow": MSO_SHAPE.RIGHT_ARROW,
        "left_arrow": MSO_SHAPE.LEFT_ARROW,
        "up_arrow": MSO_SHAPE.UP_ARROW,
        "down_arrow": MSO_SHAPE.DOWN_ARROW,
    }
    return shape_map.get(shape_type_str, MSO_SHAPE.RECTANGLE)


# ============================================================
# 基本エンドポイント
# ============================================================

@app.get("/")
async def root():
    return {"message": "Slide Creater API - Magic Layers", "version": "2.0.0"}


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """画像ファイルをアップロード"""
    allowed_extensions = {".png", ".jpg", ".jpeg"}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"サポートされていないファイル形式です: {file_ext}"
        )
    
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {
        "file_id": file_id,
        "filename": filename,
        "original_name": file.filename,
        "path": str(file_path)
    }


# ============================================================
# Magic Layers エンドポイント
# ============================================================

@app.post("/api/decompose/{file_id}")
async def decompose_image(file_id: str):
    """
    Magic Layers: 画像を編集可能なレイヤーに分解
    
    処理フロー:
    1. Claude Vision APIで画像内の要素を検出
    2. 各要素を透過PNGとして切り出し
    3. メタデータJSON出力
    """
    file_path = None
    for ext in [".png", ".jpg", ".jpeg"]:
        candidate = UPLOAD_DIR / f"{file_id}{ext}"
        if candidate.exists():
            file_path = str(candidate)
            break
    
    if not file_path:
        raise HTTPException(status_code=404, detail="画像ファイルが見つかりません")
    
    try:
        result = await layer_decomposer.decompose(file_path, file_id)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        layers_response = []
        for layer in result.layers:
            image_url = None
            if layer.image_path:
                relative_path = Path(layer.image_path).relative_to(BASE_DIR)
                image_url = f"/{relative_path}"
            
            layers_response.append({
                "layer_id": layer.layer_id,
                "element_type": layer.element_type,
                "x": layer.x,
                "y": layer.y,
                "width": layer.width,
                "height": layer.height,
                "z_index": layer.z_index,
                "description": layer.description,
                "content": layer.content,
                "color": layer.color,
                "image_url": image_url,
                "confidence": layer.confidence
            })
        
        return {
            "file_id": file_id,
            "success": True,
            "message": result.message,
            "original_size": {
                "width": result.original_width,
                "height": result.original_height
            },
            "background_color": result.background_color,
            "layer_count": len(result.layers),
            "layers": layers_response,
            "output_dir": f"/outputs/{file_id}_layers",
            "metadata_url": f"/outputs/{file_id}_layers/layers_metadata.json"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"レイヤー分解エラー: {str(e)}")


@app.get("/api/layers/{file_id}")
async def get_decomposed_layers(file_id: str):
    """分解済みレイヤー情報を取得"""
    metadata_path = OUTPUT_DIR / f"{file_id}_layers" / "layers_metadata.json"
    
    if not metadata_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="レイヤーデータが見つかりません。先に /api/decompose/{file_id} を実行してください。"
        )
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    for layer in metadata.get("layers", []):
        if layer.get("image_path"):
            relative_path = Path(layer["image_path"]).relative_to(BASE_DIR)
            layer["image_url"] = f"/{relative_path}"
    
    return {"file_id": file_id, **metadata}


@app.delete("/api/layers/{file_id}")
async def delete_decomposed_layers(file_id: str):
    """分解済みレイヤーを削除"""
    layers_dir = OUTPUT_DIR / f"{file_id}_layers"
    
    if not layers_dir.exists():
        raise HTTPException(status_code=404, detail="レイヤーデータが見つかりません")
    
    deleted_count = len(list(layers_dir.glob("*.png")))
    shutil.rmtree(layers_dir)
    
    return {
        "file_id": file_id,
        "deleted_layers": deleted_count,
        "message": "レイヤーデータを削除しました"
    }


@app.post("/api/layers/{file_id}/pptx")
async def generate_pptx_from_layers(file_id: str):
    """
    分解されたレイヤーからPPTXを生成
    - テキスト要素 → 編集可能なテキストボックス
    - 図形 → PowerPointネイティブシェイプ
    - 画像/アイコン → PNG画像として配置
    """
    metadata_path = OUTPUT_DIR / f"{file_id}_layers" / "layers_metadata.json"
    
    if not metadata_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="レイヤーデータが見つかりません。先に /api/decompose/{file_id} を実行してください。"
        )
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    try:
        # プレゼンテーション作成（16:9）
        prs = Presentation()
        slide_width_inches = 13.333
        slide_height_inches = 7.5
        prs.slide_width = Inches(slide_width_inches)
        prs.slide_height = Inches(slide_height_inches)
        
        blank_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank_layout)
        
        # 元画像サイズ（ピクセル）
        original_width = metadata.get("original_size", {}).get("width", 1920)
        original_height = metadata.get("original_size", {}).get("height", 1080)
        
        # スケーリング計算
        scale_x = slide_width_inches / (original_width / 96)
        scale_y = slide_height_inches / (original_height / 96)
        scale = min(scale_x, scale_y) * 0.95
        
        scaled_width = (original_width / 96) * scale
        scaled_height = (original_height / 96) * scale
        offset_x = (slide_width_inches - scaled_width) / 2
        offset_y = (slide_height_inches - scaled_height) / 2
        
        # 背景色設定
        bg_color = metadata.get("background_color")
        if bg_color and bg_color.startswith("#"):
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = hex_to_rgb(bg_color)
        
        # レイヤー配置
        layers = sorted(metadata.get("layers", []), key=lambda x: x.get("z_index", 0))
        
        placed_count = 0
        text_count = 0
        shape_count = 0
        image_count = 0
        
        for layer in layers:
            element_type = layer.get("element_type", "image")
            
            left_inches = offset_x + (layer.get("x", 0) / 96) * scale
            top_inches = offset_y + (layer.get("y", 0) / 96) * scale
            width_inches = max((layer.get("width", 100) / 96) * scale, 0.1)
            height_inches = max((layer.get("height", 100) / 96) * scale, 0.1)
            
            try:
                # テキスト要素
                if element_type == "text":
                    content = layer.get("content", "")
                    if content:
                        textbox = slide.shapes.add_textbox(
                            Inches(left_inches),
                            Inches(top_inches),
                            Inches(width_inches),
                            Inches(height_inches)
                        )
                        tf = textbox.text_frame
                        tf.word_wrap = True
                        
                        p = tf.paragraphs[0]
                        p.text = content
                        
                        font_size = layer.get("font_size", 12)
                        font_color = layer.get("font_color", "#000000")
                        font_bold = layer.get("font_bold", False)
                        text_align = layer.get("text_align", "left")
                        
                        run = p.runs[0] if p.runs else p.add_run()
                        run.text = content
                        run.font.size = Pt(font_size)
                        run.font.color.rgb = hex_to_rgb(font_color)
                        run.font.bold = font_bold
                        
                        align_map = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
                        p.alignment = align_map.get(text_align, PP_ALIGN.LEFT)
                        
                        text_count += 1
                        placed_count += 1
                        continue
                
                # 図形要素
                elif element_type in ["shape", "line", "arrow"]:
                    shape_type_str = layer.get("shape_type", "rectangle")
                    fill_color = layer.get("fill_color")
                    border_color = layer.get("border_color")
                    border_width = layer.get("border_width", 1)
                    
                    if element_type == "line" or shape_type_str == "line":
                        line_shape = slide.shapes.add_shape(
                            MSO_SHAPE.RECTANGLE,
                            Inches(left_inches),
                            Inches(top_inches),
                            Inches(width_inches),
                            Inches(max(height_inches, 0.02))
                        )
                        line_shape.fill.solid()
                        line_shape.fill.fore_color.rgb = hex_to_rgb(border_color) if border_color else RGBColor(0, 0, 0)
                        line_shape.line.fill.background()
                        shape_count += 1
                        placed_count += 1
                        continue
                    
                    shape_type = MSO_SHAPE.RIGHT_ARROW if element_type == "arrow" or shape_type_str == "arrow" else get_shape_type(shape_type_str)
                    
                    shape = slide.shapes.add_shape(
                        shape_type,
                        Inches(left_inches),
                        Inches(top_inches),
                        Inches(width_inches),
                        Inches(height_inches)
                    )
                    
                    if fill_color:
                        shape.fill.solid()
                        shape.fill.fore_color.rgb = hex_to_rgb(fill_color)
                    else:
                        shape.fill.background()
                    
                    if border_color:
                        shape.line.color.rgb = hex_to_rgb(border_color)
                        shape.line.width = Pt(border_width or 1)
                    else:
                        shape.line.fill.background()
                    
                    shape_count += 1
                    placed_count += 1
                    continue
                
                # 画像/アイコン
                image_path = layer.get("image_path")
                if image_path and Path(image_path).exists():
                    slide.shapes.add_picture(
                        image_path,
                        Inches(left_inches),
                        Inches(top_inches),
                        Inches(width_inches),
                        Inches(height_inches)
                    )
                    image_count += 1
                    placed_count += 1
                
            except Exception as e:
                logger.warning(f"レイヤー配置エラー: {layer.get('layer_id')} - {e}")
                image_path = layer.get("image_path")
                if image_path and Path(image_path).exists():
                    try:
                        slide.shapes.add_picture(
                            image_path,
                            Inches(left_inches),
                            Inches(top_inches),
                            Inches(width_inches),
                            Inches(height_inches)
                        )
                        image_count += 1
                        placed_count += 1
                    except:
                        pass
        
        # PPTX保存
        output_filename = f"{file_id}_layers.pptx"
        output_path = OUTPUT_DIR / output_filename
        prs.save(str(output_path))
        
        return {
            "file_id": file_id,
            "success": True,
            "pptx_path": str(output_path),
            "download_url": f"/api/layers/{file_id}/download",
            "layer_count": placed_count,
            "text_count": text_count,
            "shape_count": shape_count,
            "image_count": image_count,
            "message": f"{placed_count}個のレイヤーをPPTXに配置しました"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PPTX生成エラー: {str(e)}")


@app.get("/api/layers/{file_id}/download")
async def download_layers_pptx(file_id: str):
    """分解レイヤーから生成したPPTXをダウンロード"""
    output_path = OUTPUT_DIR / f"{file_id}_layers.pptx"
    
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="PPTXファイルが見つかりません")
    
    return FileResponse(
        path=str(output_path),
        filename=f"layers_{file_id}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
