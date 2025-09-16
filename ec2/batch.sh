#!/bin/bash

# --- 配置 ---
# 测试总次数
TOTAL_RUNS=50
# AWS 区域
REGION="us-east-2"
# CloudFormation 堆栈名称
STACK_NAME="ec2-test"
# ECS 集群名称 (必须与 ec2_v1.yaml 中定义的一致)
CLUSTER_NAME="ec2-startup-test-cluster"
# ECS 任务定义 (必须与 ec2_v1.yaml 中定义的一致)
TASK_DEFINITION="ec2-startup-test-task"
# 新建 EC2 实例的类型
INSTANCE_TYPE="t2.micro"
# 结果输出文件
OUTPUT_FILE="startup_times.csv"

# --- 脚本开始 ---

# 1. 初始化环境：创建堆栈
echo ">>> 第1步：创建 CloudFormation 堆栈..."
./create.sh
if [ $? -ne 0 ]; then
  echo "错误：CloudFormation 堆栈创建失败，测试终止。"
  exit 1
fi

# 2. 获取堆栈输出的关键信息
echo ">>> 第2步：获取网络、角色和启动模板配置..."
SUBNET_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='SubnetId'].OutputValue" --output text --region $REGION)
LAUNCH_TEMPLATE_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='LaunchTemplateId'].OutputValue" --output text --region $REGION)

echo "子网 ID: $SUBNET_ID"
echo "启动模板 ID: $LAUNCH_TEMPLATE_ID"

if [ -z "$SUBNET_ID" ] || [ -z "$LAUNCH_TEMPLATE_ID" ]; then
  echo "错误：未能从 CloudFormation 堆栈获取必要的输出 (SubnetId, LaunchTemplateId)。请检查堆栈状态。"
  ./delete.sh # 尝试清理
  exit 1
fi

# 3. 等待初始的常驻实例注册
echo ">>> 第3步：等待初始的常驻容器实例注册到集群..."
HOT_INSTANCE_ARN=""
while [ -z "$HOT_INSTANCE_ARN" ]; do
  HOT_INSTANCE_ARN=$(aws ecs list-container-instances --cluster $CLUSTER_NAME --region $REGION --query 'containerInstanceArns[0]' --output text)
  if [ "$HOT_INSTANCE_ARN" == "None" ] || [ -z "$HOT_INSTANCE_ARN" ]; then
    echo "等待常驻实例注册... (30秒后重试)"
    sleep 30
    HOT_INSTANCE_ARN=""
  else
    echo "常驻容器实例已注册: $HOT_INSTANCE_ARN"
  fi
done


# --- 第一次热启动暖机 ---
HOT_TASK_ARN=$(aws ecs start-task \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEFINITION \
  --container-instances $HOT_INSTANCE_ARN \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text 2>/dev/null)

if [ -z "$HOT_TASK_ARN" ] || [ "$HOT_TASK_ARN" == "None" ]; then
    echo "错误：第一次热启动任务创建失败。"
    continue
fi

aws ecs wait tasks-running --cluster $CLUSTER_NAME --tasks $HOT_TASK_ARN --region $REGION
aws ecs stop-task --cluster $CLUSTER_NAME --task $HOT_TASK_ARN --region $REGION >/dev/null

# 4. 循环执行测试
echo ">>> 第4步：开始 ${TOTAL_RUNS} 次冷热启动测试循环..."
echo "run,cold_start_ms,hot_start_ms,time_saved_ms" > $OUTPUT_FILE

for i in $(seq 1 $TOTAL_RUNS); do
  echo "================================================="
  echo "=============== 开始第 $i / $TOTAL_RUNS 轮测试 ==============="
  echo "================================================="

  # --- 冷启动测试 ---
  echo "--- [冷启动] ---"
  # a. 启动一台新的 EC2 实例
  echo "使用启动模板 ($LAUNCH_TEMPLATE_ID) 启动新的 EC2 实例用于冷启动测试..."

  # # 为临时实例准备一个简单的 UserData，仅用于加入集群
  # USER_DATA_FILE=$(mktemp)
  # echo "#!/bin/bash
  # echo ECS_CLUSTER=${CLUSTER_NAME} > /etc/ecs/ecs.config" > $USER_DATA_FILE

  INSTANCE_ID=$(aws ec2 run-instances \
    --launch-template LaunchTemplateId=$LAUNCH_TEMPLATE_ID \
    --subnet-id $SUBNET_ID \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=cold-start-test-instance}]' \
    --query 'Instances[0].InstanceId' \
    --output text \
    --region $REGION)

  # rm $USER_DATA_FILE # 清理临时文件
  
  if [ -z "$INSTANCE_ID" ]; then
      echo "错误：无法启动新的 EC2 实例，跳过此轮测试。"
      continue
  fi
  echo "新实例 ID: $INSTANCE_ID，等待其注册到 ECS 集群..."

  # b. 等待新实例注册到 ECS
  COLD_INSTANCE_ARN=""
  ATTEMPTS=0
  MAX_ATTEMPTS=20
  echo "新实例 ID: $INSTANCE_ID，等待其注册到 ECS 集群..."

  while [ -z "$COLD_INSTANCE_ARN" ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    ATTEMPTS=$((ATTEMPTS+1))
    echo "等待新实例注册... (尝试 ${ATTEMPTS}/${MAX_ATTEMPTS})"
    
    # 查找与新EC2实例ID匹配的容器实例ARN
    # 这是一个更健壮的方法，避免了复杂的嵌套查询
    ALL_CONTAINER_INSTANCES_ARNS=$(aws ecs list-container-instances --cluster $CLUSTER_NAME --region $REGION --query 'containerInstanceArns' --output text)
    if [ -n "$ALL_CONTAINER_INSTANCES_ARNS" ]; then
        COLD_INSTANCE_ARN=$(aws ecs describe-container-instances \
            --cluster $CLUSTER_NAME \
            --region $REGION \
            --container-instances $ALL_CONTAINER_INSTANCES_ARNS \
            --query "containerInstances[?ec2InstanceId=='$INSTANCE_ID'].containerInstanceArn" \
            --output text)
    fi

    if [ -z "$COLD_INSTANCE_ARN" ]; then
      sleep 20
    else
      echo "新容器实例已注册: $COLD_INSTANCE_ARN"
    fi
  done

  if [ -z "$COLD_INSTANCE_ARN" ]; then
    echo "错误：新实例注册超时，终止此实例并跳过此轮测试。"
    aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
    continue
  fi

  # c. 在新实例上运行任务并计时
  START_TIME_COLD=$(date +%s%3N)
  COLD_TASK_ARN=$(aws ecs start-task \
    --cluster $CLUSTER_NAME \
    --task-definition $TASK_DEFINITION \
    --container-instances $COLD_INSTANCE_ARN \
    --region $REGION \
    --query 'tasks[0].taskArn' \
    --output text 2>/dev/null)

  if [ -z "$COLD_TASK_ARN" ] || [ "$COLD_TASK_ARN" == "None" ]; then
      echo "错误：冷启动任务创建失败。"
      aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
      continue
  fi

  aws ecs wait tasks-running --cluster $CLUSTER_NAME --tasks $COLD_TASK_ARN --region $REGION
  END_TIME_COLD=$(date +%s%3N)
  COLD_START_TIME=$((END_TIME_COLD - START_TIME_COLD))
  echo "冷启动完成，耗时: ${COLD_START_TIME}ms"

  # d. 清理冷启动资源
  echo "停止冷启动任务并终止临时实例..."
  aws ecs stop-task --cluster $CLUSTER_NAME --task $COLD_TASK_ARN --region $REGION >/dev/null
  aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION >/dev/null
  echo "等待实例终止..."
  aws ec2 wait instance-terminated --instance-ids $INSTANCE_ID --region $REGION

  # --- 热启动测试 ---
  echo "--- [热启动] ---"
  START_TIME_HOT=$(date +%s%3N)
  HOT_TASK_ARN=$(aws ecs start-task \
    --cluster $CLUSTER_NAME \
    --task-definition $TASK_DEFINITION \
    --container-instances $HOT_INSTANCE_ARN \
    --region $REGION \
    --query 'tasks[0].taskArn' \
    --output text 2>/dev/null)

  if [ -z "$HOT_TASK_ARN" ] || [ "$HOT_TASK_ARN" == "None" ]; then
      echo "错误：热启动任务创建失败。"
      continue
  fi

  aws ecs wait tasks-running --cluster $CLUSTER_NAME --tasks $HOT_TASK_ARN --region $REGION
  END_TIME_HOT=$(date +%s%3N)
  HOT_START_TIME=$((END_TIME_HOT - START_TIME_HOT))
  echo "热启动完成，耗时: ${HOT_START_TIME}ms"

  # 清理热启动任务
  aws ecs stop-task --cluster $CLUSTER_NAME --task $HOT_TASK_ARN --region $REGION >/dev/null

  # --- 记录结果 ---
  TIME_SAVED=$((COLD_START_TIME - HOT_START_TIME))
  echo "本轮节省时间: ${TIME_SAVED}ms"
  echo "$i,${COLD_START_TIME},${HOT_START_TIME},${TIME_SAVED}" >> $OUTPUT_FILE
  
  # 等待一段时间，避免 AWS API 调用过于频繁
  echo "等待30秒进入下一轮..."
  sleep 30
done

# 5. 最终清理
echo ">>> 第5步：所有测试完成，清理 CloudFormation 堆栈..."
./delete.sh
if [ $? -ne 0 ]; then
  echo "警告：堆栈清理脚本执行失败。请手动检查 AWS 控制台。"
fi

echo "========================================="
echo "测试全部完成！结果已保存到 $OUTPUT_FILE"
echo "========================================="
