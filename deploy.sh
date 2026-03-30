#!/bin/bash
# デプロイスクリプト

set -e

echo "=== Slide Creater デプロイ ==="

# .envファイル確認
if [ ! -f .env ]; then
    echo "エラー: .env ファイルが見つかりません"
    echo ".env.example をコピーして .env を作成し、ANTHROPIC_API_KEY を設定してください"
    exit 1
fi

# Docker確認
if ! command -v docker &> /dev/null; then
    echo "エラー: Docker がインストールされていません"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "エラー: Docker Compose がインストールされていません"
    exit 1
fi

# ビルド＆起動
echo ""
echo "Docker イメージをビルド中..."
docker compose build

echo ""
echo "コンテナを起動中..."
docker compose up -d

echo ""
echo "=== デプロイ完了 ==="
echo "フロントエンド: http://localhost"
echo "バックエンドAPI: http://localhost:8000"
echo ""
echo "ログ確認: docker compose logs -f"
echo "停止: docker compose down"
