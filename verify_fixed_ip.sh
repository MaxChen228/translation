#!/bin/bash

echo "=== 驗證固定 IP 設定 ==="

# 檢查當前 IP
CURRENT_IP=$(ifconfig en0 | grep "inet " | awk '{print $2}')
echo "🔍 目前 IP 位址: $CURRENT_IP"

# 預期的固定 IP
EXPECTED_IP="192.168.1.100"

if [ "$CURRENT_IP" = "$EXPECTED_IP" ]; then
    echo "✅ 固定 IP 設定成功！"
    echo "🎉 你的開發環境 URL 永遠是: http://$EXPECTED_IP:8080"
else
    echo "⚠️  IP 不是預期的固定值"
    echo "💡 請檢查："
    echo "   1. 路由器設定是否正確"
    echo "   2. 是否已重啟路由器"
    echo "   3. 是否已重新連接 Wi-Fi"
fi

# 測試後端連接
echo ""
echo "🧪 測試後端連接..."
if curl -s http://$CURRENT_IP:8080/healthz > /dev/null 2>&1; then
    echo "✅ 後端連接正常"
else
    echo "❌ 後端無法連接，請確認後端服務是否啟動"
fi