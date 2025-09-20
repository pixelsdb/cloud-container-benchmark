#!/bin/bash
echo "删除CloudFormation 堆栈..."
aws cloudformation delete-stack \
--stack-name fargate-test \
--region us-east-2

echo "等待 CloudFormation 堆栈删除完成..."
aws cloudformation wait stack-delete-complete \
--stack-name fargate-test \
--region us-east-2