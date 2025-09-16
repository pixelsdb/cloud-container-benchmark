#!/bin/bash
CLUSTER_NAME="fargate-startup-test-cluster"
TASK_DEFINITION="startup-test-task"
REGION="us-east-2"

# 获取CloudFormation堆栈输出
echo "获取CloudFormation堆栈输出..."
SUBNET_ID=$(aws cloudformation describe-stacks --stack-name fargate-test --query "Stacks[0].Outputs[?OutputKey=='SubnetId'].OutputValue" --output text --region $REGION)
SECURITY_GROUP_ID=$(aws cloudformation describe-stacks --stack-name fargate-test --query "Stacks[0].Outputs[?OutputKey=='SecurityGroupId'].OutputValue" --output text --region $REGION)

echo "子网ID: $SUBNET_ID"
echo "安全组ID: $SECURITY_GROUP_ID"

# 网络配置
NETWORK_CONFIGURATION="{\"awsvpcConfiguration\": {\"subnets\": [\"$SUBNET_ID\"], \"securityGroups\": [\"$SECURITY_GROUP_ID\"], \"assignPublicIp\": \"ENABLED\"}}"
# 冷启动测试
echo "开始冷启动测试..."
START_TIME_COLD=$(date +%s%3N)

# # 运行任务并捕获完整输出
# RUN_TASK_OUTPUT=$(aws ecs run-task \
#   --cluster $CLUSTER_NAME \
#   --task-definition $TASK_DEFINITION \
#   --launch-type FARGATE \
#   --platform-version LATEST \
#   --network-configuration "$NETWORK_CONFIGURATION" \
#   --region $REGION \
#   --output json 2>&1)

# echo "Run task output: $RUN_TASK_OUTPUT"


# # 提取任务ARN
# COLD_TASK_ARN=$(echo "$RUN_TASK_OUTPUT" | jq -r '.tasks[0].taskArn' 2>/dev/null)

COLD_TASK_ARN=$(aws ecs run-task \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEFINITION \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "$NETWORK_CONFIGURATION" \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text 2>/dev/null)

# 检查任务是否成功启动
if [ -z "$COLD_TASK_ARN" ] || [ "$COLD_TASK_ARN" == "null" ]; then
    echo "错误：冷启动任务创建失败"
    echo "详细错误信息: $RUN_TASK_OUTPUT"
    exit 1
fi

echo "冷启动任务ARN: $COLD_TASK_ARN"

# 等待冷启动任务运行
echo "等待冷启动任务运行..."
aws ecs wait tasks-running \
  --cluster $CLUSTER_NAME \
  --tasks $COLD_TASK_ARN \
  --region $REGION

END_TIME_COLD=$(date +%s%3N)
COLD_START_TIME=$((END_TIME_COLD - START_TIME_COLD))

echo "冷启动完成，耗时: ${COLD_START_TIME}ms"

# 获取冷启动任务的详细时间信息
COLD_TASK_DETAILS=$(aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $COLD_TASK_ARN \
  --region $REGION)

CREATED_AT=$(echo $COLD_TASK_DETAILS | jq -r '.tasks[0].createdAt')
STARTED_AT=$(echo $COLD_TASK_DETAILS | jq -r '.tasks[0].startedAt')

echo "任务创建时间: $CREATED_AT"
echo "任务开始时间: $STARTED_AT"

# 热启动测试
echo "等待10秒后开始热启动测试..."
sleep 10

echo "开始热启动测试..."
START_TIME_HOT=$(date +%s%3N)

HOT_TASK_ARN=$(aws ecs run-task \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEFINITION \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "$NETWORK_CONFIGURATION" \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text 2>/dev/null)

# 检查任务是否成功启动
if [ -z "$HOT_TASK_ARN" ]; then
    echo "错误：热启动任务创建失败"
    exit 1
fi

echo "热启动任务ARN: $HOT_TASK_ARN"

# 等待热启动任务运行
echo "等待热启动任务运行..."
aws ecs wait tasks-running \
  --cluster $CLUSTER_NAME \
  --tasks $HOT_TASK_ARN \
  --region $REGION

END_TIME_HOT=$(date +%s%3N)
HOT_START_TIME=$((END_TIME_HOT - START_TIME_HOT))

echo "热启动完成，耗时: ${HOT_START_TIME}ms"

# 获取热启动任务的详细时间信息
HOT_TASK_DETAILS=$(aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $HOT_TASK_ARN \
  --region $REGION)

HOT_CREATED_AT=$(echo $HOT_TASK_DETAILS | jq -r '.tasks[0].createdAt')
HOT_STARTED_AT=$(echo $HOT_TASK_DETAILS | jq -r '.tasks[0].startedAt')

echo "热启动任务创建时间: $HOT_CREATED_AT"
echo "热启动任务开始时间: $HOT_STARTED_AT"

# 输出结果
echo "=== 测试结果 ==="
echo "冷启动时间: ${COLD_START_TIME}ms"
echo "热启动时间: ${HOT_START_TIME}ms"
echo "时间节省: $(($COLD_START_TIME - $HOT_START_TIME))ms"

# 清理任务
echo "清理测试任务..."
aws ecs stop-task \
  --cluster $CLUSTER_NAME \
  --task $COLD_TASK_ARN \
  --region $REGION >/dev/null 2>&1

aws ecs stop-task \
  --cluster $CLUSTER_NAME \
  --task $HOT_TASK_ARN \
  --region $REGION >/dev/null 2>&1

echo "测试完成!"

echo "冷启动时间戳："
aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $COLD_TASK_ARN \
  --region $REGION\
  --query 'tasks[0].{createdAt: createdAt, startedAt: startedAt, pullStartedAt: pullStartedAt, pullStoppedAt: pullStoppedAt}'

  echo "热启动时间戳："
aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $HOT_TASK_ARN \
  --region $REGION\
  --query 'tasks[0].{createdAt: createdAt, startedAt: startedAt, pullStartedAt: pullStartedAt, pullStoppedAt: pullStoppedAt}'