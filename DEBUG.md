第一步：确认 Key 属于哪个站

KEY=$(grep SALON_DASHSCOPE_API_KEY /home/ecs-user/SOLAN/SALON/src/agent/.env | cut -d= -f2)
echo "--- 国内站 ---"
curl -s -H "Authorization: Bearer $KEY" \
  "https://dashscope.aliyuncs.com/api/v1/tasks?page_size=1"
echo "--- 国际站 ---"
curl -s -H "Authorization: Bearer $KEY" \
  "https://dashscope-intl.aliyuncs.com/api/v1/tasks?page_size=1"
第二步：根据结果在 .env 加一行

# 如果国际站 200：
echo "SALON_DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1" \
  >> /home/ecs-user/SOLAN/SALON/src/agent/.env
# 如果两个都 401：说明 Key 本身无效，需到百炼控制台重新生成
第三步：拉取新代码并重启


cd /home/ecs-user/SOLAN/SALON && git pull
sudo systemctl restart salon-gateway.service