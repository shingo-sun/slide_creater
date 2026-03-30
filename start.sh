#!/bin/bash

# Slide Creater 起動スクリプト

echo "🚀 Slide Creater を起動します..."

# ディレクトリ設定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# バックエンド起動
echo "📦 バックエンドを起動中..."
cd "$BACKEND_DIR"

# 仮想環境の確認と作成
if [ ! -d "venv" ]; then
    echo "  仮想環境を作成中..."
    python3 -m venv venv
fi

source venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt --quiet

# ディレクトリ作成
mkdir -p uploads outputs

# バックエンド起動（バックグラウンド）
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "  バックエンドPID: $BACKEND_PID"

# フロントエンド起動
echo "🎨 フロントエンドを起動中..."
cd "$FRONTEND_DIR"

# node_modulesの確認
if [ ! -d "node_modules" ]; then
    echo "  依存関係をインストール中..."
    npm install
fi

# フロントエンド起動
npm run dev &
FRONTEND_PID=$!
echo "  フロントエンドPID: $FRONTEND_PID"

echo ""
echo "✅ 起動完了！"
echo "   フロントエンド: http://localhost:3000"
echo "   バックエンドAPI: http://localhost:8000"
echo ""
echo "終了するには Ctrl+C を押してください"

# 終了処理
cleanup() {
    echo ""
    echo "🛑 シャットダウン中..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# プロセス監視
wait
