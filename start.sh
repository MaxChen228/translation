#!/bin/bash

echo "🔧 正在準備開發環境..."

# 1. 停止所有佔用 8080 端口的進程
echo "🛑 停止現有的 8080 端口進程..."
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
sleep 1

# 2. 獲取當前 IP 位址
IP=$(ifconfig en0 | grep "inet " | awk '{print $2}')

if [ -z "$IP" ]; then
    echo "❌ 無法獲取 IP 位址，請檢查網路連線"
    exit 1
fi

# 3. 顯示網路資訊
echo ""
echo "=== 🌐 網路資訊 ==="
echo "📱 目前 IP 位址: $IP"
echo "🔗 後端 URL: http://$IP:8080"
echo "📱 iOS 前端請設定 BACKEND_URL: http://$IP:8080"
echo "====================="
echo ""

# 4. 確認虛擬環境
if [ ! -d ".venv" ]; then
    echo "❌ 找不到虛擬環境 .venv"
    exit 1
fi

# 5. 檢查後端是否可以啟動
if [ ! -f "main.py" ]; then
    echo "❌ 找不到 main.py"
    exit 1
fi

# 6. 更新 .env 確保正確配置
if [ -f ".env" ]; then
    # 確保 HOST 和 PORT 設定正確
    sed -i '' '/^HOST=/d' .env 2>/dev/null || true
    sed -i '' '/^PORT=/d' .env 2>/dev/null || true
    echo "" >> .env
    echo "# Server configuration (auto-updated)" >> .env
    echo "HOST=0.0.0.0" >> .env
    echo "PORT=8080" >> .env
fi

# 7. 啟動後端服務
echo "🚀 啟動後端服務..."
source .venv/bin/activate

# 在背景執行並捕獲 PID
python main.py &
BACKEND_PID=$!

# 等待服務啟動
sleep 3

# 8. 檢查服務是否成功啟動
if kill -0 $BACKEND_PID 2>/dev/null; then
    echo ""
    echo "✅ 後端服務啟動成功！"
    echo "🔍 進程 ID: $BACKEND_PID"

    # 測試健康檢查
    if curl -s http://localhost:8080/healthz > /dev/null 2>&1; then
        echo "🩺 健康檢查: ✅ 正常"
    else
        echo "🩺 健康檢查: ⚠️  可能需要稍等片刻"
    fi

    echo ""
    echo "📋 快速指令:"
    echo "  檢查狀態: curl http://localhost:8080/healthz"
    echo "  停止服務: kill $BACKEND_PID"
    echo "  查看日誌: tail -f 日誌檔案"
    echo ""
    echo "🎯 開發環境就緒！按 Ctrl+C 停止服務"

    # 保持腳本運行，讓用戶可以看到日誌
    wait $BACKEND_PID
else
    echo "❌ 後端服務啟動失敗"
    exit 1
fi