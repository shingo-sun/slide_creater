#!/bin/bash
# SAM (Segment Anything Model) セットアップスクリプト

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$SCRIPT_DIR/models"
MODEL_URL="https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
MODEL_FILE="$MODEL_DIR/sam_vit_b_01ec64.pth"

echo "=== SAM セットアップ ==="

# modelsディレクトリ作成
mkdir -p "$MODEL_DIR"

# モデルダウンロード
if [ -f "$MODEL_FILE" ]; then
    echo "モデルは既にダウンロード済みです: $MODEL_FILE"
else
    echo "SAM ViT-B モデルをダウンロード中..."
    echo "URL: $MODEL_URL"
    
    if command -v curl &> /dev/null; then
        curl -L -o "$MODEL_FILE" "$MODEL_URL"
    elif command -v wget &> /dev/null; then
        wget -O "$MODEL_FILE" "$MODEL_URL"
    else
        echo "エラー: curl または wget が必要です"
        exit 1
    fi
    
    echo "ダウンロード完了: $MODEL_FILE"
fi

# ファイルサイズ確認
FILE_SIZE=$(ls -la "$MODEL_FILE" | awk '{print $5}')
echo "モデルファイルサイズ: $FILE_SIZE bytes"

# Python依存関係インストール
echo ""
echo "Python依存関係をインストール中..."
cd "$SCRIPT_DIR"
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate

pip install torch torchvision --quiet
pip install git+https://github.com/facebookresearch/segment-anything.git --quiet

echo ""
echo "=== セットアップ完了 ==="
echo "SAMモデル: $MODEL_FILE"
echo ""
echo "バックエンドを再起動してください:"
echo "  cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000"
