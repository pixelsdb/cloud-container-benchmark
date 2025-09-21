#!/bin/bash
CLUSTER_NAME="ec2-startup-test-cluster"
TASK_DEFINITION="ec2-startup-test-task"
REGION="us-east-2"

# 获取CloudFormation堆栈输出
echo "获取CloudFormation堆栈输出..."
SUBNET_ID=$(aws cloudformation describe-stacks --stack-name ec2-test --query "Stacks[0].Outputs[?OutputKey=='SubnetId'].OutputValue" --output text --region $REGION)
SECURITY_GROUP_ID=$(aws cloudformation describe-stacks --stack-name ec2-test --query "Stacks[0].Outputs[?OutputKey=='SecurityGroupId'].OutputValue" --output text --region $REGION)

echo "子网ID: $SUBNET_ID"
echo "安全组ID: $SECURITY_GROUP_ID"

# 等待EC2实例注册到集群
echo "等待EC2实例注册到集群..."
INSTANCE_READY=false
ATTEMPTS=0
MAX_ATTEMPTS=20

while [ "$INSTANCE_READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
  INSTANCE_COUNT=$(aws ecs list-container-instances --cluster $CLUSTER_NAME --region $REGION --query "length(containerInstanceArns)" --output text)
  
  if [ "$INSTANCE_COUNT" -gt 0 ]; then
    INSTANCE_READY=true
    echo "发现 $INSTANCE_COUNT 个容器实例"
  else
    echo "等待容器实例注册... (尝试 $((ATTEMPTS+1))/$MAX_ATTEMPTS)"
    sleep 30
    ATTEMPTS=$((ATTEMPTS+1))
  fi
done

if [ "$INSTANCE_READY" = false ]; then
  echo "错误：容器实例未在预期时间内注册到集群"
  exit 1
fi

# 冷启动测试
echo "开始冷启动测试..."
START_TIME_COLD=$(date +%s%3N)

COLD_TASK_ARN=$(aws ecs run-task \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEFINITION \
  --launch-type EC2 \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text 2>/dev/null)

# 检查任务是否成功启动
if [ -z "$COLD_TASK_ARN" ] || [ "$COLD_TASK_ARN" == "None" ]; then
    echo "错误：冷启动任务创建失败"
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

COLD_CREATED_AT=$(echo $COLD_TASK_DETAILS | jq -r '.tasks[0].createdAt')
COLD_STARTED_AT=$(echo $COLD_TASK_DETAILS | jq -r '.tasks[0].startedAt')

echo "任务创建时间: $COLD_CREATED_AT"
echo "任务开始时间: $COLD_STARTED_AT"

# 等待任务完全停止并清理
echo "停止冷启动任务..."
aws ecs stop-task \
  --cluster $CLUSTER_NAME \
  --task $COLD_TASK_ARN \
  --region $REGION >/dev/null 2>&1

# 等待一段时间确保实例上的容器已清理
echo "等待30秒确保容器已清理..."
sleep 30

# 热启动测试
echo "开始热启动测试..."
START_TIME_HOT=$(date +%s%3N)

HOT_TASK_ARN=$(aws ecs run-task \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEFINITION \
  --launch-type EC2 \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text 2>/dev/null)

# 检查任务是否成功启动
if [ -z "$HOT_TASK_ARN" ] || [ "$HOT_TASK_ARN" == "None" ]; then
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
  --task $HOT_TASK_ARN \
  --region $REGION >/dev/null 2>&1

echo "测试完成!"

# 输出详细时间戳
echo "冷启动时间戳："
aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $COLD_TASK_ARN \
  --region $REGION \
  --query 'tasks[0].{createdAt: createdAt, startedAt: startedAt, pullStartedAt: pullStartedAt, pullStoppedAt: pullStoppedAt}'

echo "热启动时间戳："
aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $HOT_TASK_ARN \
  --region $REGION \
  --query 'tasks[0].{createdAt: createdAt, startedAt: startedAt, pullStartedAt: pullStartedAt, pullStoppedAt: pullStoppedAt}'