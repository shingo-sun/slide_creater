#!/bin/bash
# 停止スクリプト

echo "=== Slide Creater 停止 ==="

pkill -f "uvicorn app.main" 2>/dev/null && echo "バックエンド停止" || echo "バックエンドは起動していません"
pkill -f "vite" 2>/dev/null && echo "フロントエンド停止" || echo "フロントエンドは起動していません"

echo "完了"
