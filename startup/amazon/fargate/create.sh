#!/bin/bash
echo "创建 CloudFormation 堆栈..."
aws cloudformation create-stack \
--stack-name fargate-test \
--template-body file://Fargate-startup.yaml \
--parameters ParameterKey=ExecutionRoleArn,ParameterValue="arn:aws:iam::970089764833:role/ECSTasksRole" \
--region us-east-2

echo "等待 CloudFormation 堆栈创建完成..."
aws cloudformation wait stack-create-complete \
--stack-name fargate-test \
--region us-east-2