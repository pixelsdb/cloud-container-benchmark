#!/bin/bash
STACK_NAME="ec2-test"
REGION="us-east-2"
CLUSTER_NAME="ec2-startup-test-cluster"

# 1. 自动注销所有ECS容器实例
echo "正在检查集群 '$CLUSTER_NAME' 中的活动容器实例..."
INSTANCE_ARNS=$(aws ecs list-container-instances --cluster $CLUSTER_NAME --region $REGION --query 'containerInstanceArns' --output text)

if [ -n "$INSTANCE_ARNS" ]; then
  echo "发现活动容器实例，正在注销..."
  for ARN in $INSTANCE_ARNS; do
    echo "注销: $ARN"
    aws ecs deregister-container-instance --cluster $CLUSTER_NAME --container-instance "$ARN" --region $REGION --force > /dev/null
    if [ $? -ne 0 ]; then
      echo "错误：注销实例 $ARN 失败。"
      # 即使失败也继续，以尝试清理所有实例
    fi
  done

  # 2. 等待所有容器实例都从集群中消失
  echo "等待所有容器实例完成注销..."
  ATTEMPTS=0
  MAX_ATTEMPTS=20
  while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    REMAINING_INSTANCES=$(aws ecs list-container-instances --cluster $CLUSTER_NAME --region $REGION --query 'containerInstanceArns' --output text)
    if [ -z "$REMAINING_INSTANCES" ]; then
      echo "所有容器实例已成功注销。"
      break
    fi
    echo "仍在等待实例注销... 剩余: $(echo $REMAINING_INSTANCES | wc -w)"
    sleep 15
    ATTEMPTS=$((ATTEMPTS+1))
  done

  if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo "错误：等待实例注销超时。请手动检查 ECS 集群。"
    exit 1
  fi
else
  echo "集群中无活动容器实例，无需注销。"
fi

# 3. 安全地删除CloudFormation堆栈
echo "正在删除CloudFormation堆栈 '$STACK_NAME'..."
aws cloudformation delete-stack \
  --stack-name $STACK_NAME \
  --region $REGION

if [ $? -eq 0 ]; then
  echo "堆栈删除命令已发送，等待删除完成..."
  aws cloudformation wait stack-delete-complete \
    --stack-name $STACK_NAME \
    --region $REGION
  
  if [ $? -eq 0 ]; then
    echo "堆栈 '$STACK_NAME' 删除成功！"
  else
    echo "错误：堆栈删除失败或超时。请登录 AWS 控制台检查 CloudFormation 事件。"
    exit 1
  fi
else
  echo "错误：发送堆栈删除命令失败。"
  exit 1
fi