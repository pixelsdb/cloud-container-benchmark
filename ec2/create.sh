#!/bin/bash
STACK_NAME="ec2-test"
REGION="us-east-2"
# INSTANCE_ROLE_ARN="arn:aws:iam::970089764833:role/EC2Role"
INSTANCE_ROLE_ARN="arn:aws:iam::970089764833:instance-profile/EC2Role"
AMI_TYPE="ECSOptimized"  # 'AmazonLinux2' 

echo "创建CloudFormation堆栈..."

# 构建参数数组
PARAMETERS="ParameterKey=InstanceRoleArn,ParameterValue=$INSTANCE_ROLE_ARN"

aws cloudformation create-stack \
  --stack-name $STACK_NAME \
  --template-body file://ec2_v1.yaml \
  --parameters $PARAMETERS \
  --capabilities CAPABILITY_IAM \
  --region $REGION

# 检查上一条命令的执行状态
if [ $? -eq 0 ]; then
  echo "堆栈创建命令已发送，等待创建完成..."
  aws cloudformation wait stack-create-complete \
    --stack-name $STACK_NAME \
    --region $REGION
  
  # 检查等待命令的返回状态
  if [ $? -eq 0 ]; then
    echo "堆栈创建成功完成！"
    echo "集群名称: $(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`ClusterName`].OutputValue' --output text)"
  else
    echo "堆栈创建失败或超时。请使用以下命令检查状态："
    echo "aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text"
    echo "查看详细事件："
    echo "aws cloudformation describe-stack-events --stack-name $STACK_NAME --region $REGION --query 'StackEvents[?contains(ResourceStatus, \`FAILED\`)].[ResourceType, ResourceStatusReason]' --output table"
    exit 1
  fi
else
  echo "堆栈创建命令执行失败。"
  exit 1
fi