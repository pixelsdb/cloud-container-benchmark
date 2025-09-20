import subprocess
import re
import json
import matplotlib.pyplot as plt
import time
from datetime import datetime
import sys

# 重定向输出到文件
output_log = open('ec2_batch_output.txt', 'w', encoding='utf-8')
sys.stdout = output_log

# --- 堆栈创建 ---
print(">>> 第1步：创建 CloudFormation 堆栈 ...")
create_ret = subprocess.run(["./create.sh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if create_ret.returncode != 0:
    print("错误：CloudFormation 堆栈创建失败，测试终止。")
    exit(1)

# --- 配置 ---
TOTAL_RUNS = 100
REGION = "us-east-2"
STACK_NAME = "ec2-test"
CLUSTER_NAME = "ec2-startup-test-cluster"
TASK_DEFINITION = "ec2-startup-test-task"
INSTANCE_TYPE = "t2.micro"
OUTPUT_FILE = "startup_times_ec2.csv"

# --- 数据存储 ---
cold_total_times = []
hot_total_times = []
cold_pull_times = []
hot_pull_times = []
cold_prepare_times = []
hot_prepare_times = []
savings = []

# --- 工具函数 ---
def run_aws_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def extract_instance_arn(instance_id):
    # 获取所有容器实例，找到与EC2实例ID匹配的ARN
    cmd = f"aws ecs list-container-instances --cluster {CLUSTER_NAME} --region {REGION} --query 'containerInstanceArns' --output text"
    arns = run_aws_cmd(cmd)
    if not arns:
        return None
    cmd = f"aws ecs describe-container-instances --cluster {CLUSTER_NAME} --region {REGION} --container-instances {arns} --query \"containerInstances[?ec2InstanceId=='{instance_id}'].containerInstanceArn\" --output text"
    return run_aws_cmd(cmd)

def extract_timestamps(task_arn, label):
    cmd = f"aws ecs describe-tasks --cluster {CLUSTER_NAME} --tasks {task_arn} --region {REGION} --query 'tasks[0].{{createdAt: createdAt, startedAt: startedAt, pullStartedAt: pullStartedAt, pullStoppedAt: pullStoppedAt}}'"
    out = run_aws_cmd(cmd)
    try:
        ts = json.loads(out) if out else None
    except Exception:
        ts = None
    return ts

def calc_time(ts):
    def to_ms(s):
        if not s or s == 'null':
            return None
        try:
            dt = datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f")
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    created = to_ms(ts.get('createdAt'))
    started = to_ms(ts.get('startedAt'))
    pull_started = to_ms(ts.get('pullStartedAt'))
    pull_stopped = to_ms(ts.get('pullStoppedAt'))
    total = started - created if created and started else None
    pull = pull_stopped - pull_started if pull_started and pull_stopped else None
    prepare = total - pull if total is not None and pull is not None else None
    return total, pull, prepare

# --- 获取堆栈输出 ---
print(">>> 获取 CloudFormation 堆栈输出 ...")
subnet_id = run_aws_cmd(f"aws cloudformation describe-stacks --stack-name {STACK_NAME} --query \"Stacks[0].Outputs[?OutputKey=='SubnetId'].OutputValue\" --output text --region {REGION}")
launch_template_id = run_aws_cmd(f"aws cloudformation describe-stacks --stack-name {STACK_NAME} --query \"Stacks[0].Outputs[?OutputKey=='LaunchTemplateId'].OutputValue\" --output text --region {REGION}")
print(f"子网 ID: {subnet_id}")
print(f"启动模板 ID: {launch_template_id}")

# --- 获取常驻实例 ---
hot_instance_arn = None
while not hot_instance_arn:
    hot_instance_arn = run_aws_cmd(f"aws ecs list-container-instances --cluster {CLUSTER_NAME} --region {REGION} --query 'containerInstanceArns[0]' --output text")
    if not hot_instance_arn or hot_instance_arn == "None":
        print("等待常驻实例注册... (30秒后重试)")
        time.sleep(30)
        hot_instance_arn = None
    else:
        print(f"常驻容器实例已注册: {hot_instance_arn}")

# --- 第一次热启动暖机 ---
hot_task_arn = run_aws_cmd(f"aws ecs start-task --cluster {CLUSTER_NAME} --task-definition {TASK_DEFINITION} --container-instances {hot_instance_arn} --region {REGION} --query 'tasks[0].taskArn' --output text 2>/dev/null")
if not hot_task_arn or hot_task_arn == "None":
    print("错误：第一次热启动任务创建失败。")
else:
    run_aws_cmd(f"aws ecs wait tasks-running --cluster {CLUSTER_NAME} --tasks {hot_task_arn} --region {REGION}")
    run_aws_cmd(f"aws ecs stop-task --cluster {CLUSTER_NAME} --task {hot_task_arn} --region {REGION}")

# --- 测试循环 ---
print(f">>> 开始 {TOTAL_RUNS} 次冷热启动测试循环 ...")
with open(OUTPUT_FILE, "w") as f:
    f.write("run,cold_start_ms,hot_start_ms,time_saved_ms\n")

for i in range(1, TOTAL_RUNS+1):
    print("=================================================")
    print(f"=============== 开始第 {i} / {TOTAL_RUNS} 轮测试 ===============")
    print("=================================================")
    # --- 冷启动 ---
    print("--- [冷启动] ---")
    instance_id = run_aws_cmd(f"aws ec2 run-instances --launch-template LaunchTemplateId={launch_template_id} --subnet-id {subnet_id} --tag-specifications 'ResourceType=instance,Tags=[{{Key=Name,Value=cold-start-test-instance}}]' --query 'Instances[0].InstanceId' --output text --region {REGION}")
    if not instance_id:
        print("错误：无法启动新的 EC2 实例，跳过此轮测试。")
        continue
    print(f"新实例 ID: {instance_id}，等待其注册到 ECS 集群...")
    cold_instance_arn = None
    attempts = 0
    max_attempts = 20
    while not cold_instance_arn and attempts < max_attempts:
        attempts += 1
        print(f"等待新实例注册... (尝试 {attempts}/{max_attempts})")
        cold_instance_arn = extract_instance_arn(instance_id)
        if not cold_instance_arn:
            time.sleep(20)
    if not cold_instance_arn:
        print("错误：新实例注册超时，终止此实例并跳过此轮测试。")
        run_aws_cmd(f"aws ec2 terminate-instances --instance-ids {instance_id} --region {REGION}")
        continue
    print(f"新容器实例已注册: {cold_instance_arn}")
    # 冷启动任务
    start_time_cold = int(time.time() * 1000)
    cold_task_arn = run_aws_cmd(f"aws ecs start-task --cluster {CLUSTER_NAME} --task-definition {TASK_DEFINITION} --container-instances {cold_instance_arn} --region {REGION} --query 'tasks[0].taskArn' --output text 2>/dev/null")
    if not cold_task_arn or cold_task_arn == "None":
        print("错误：冷启动任务创建失败。")
        run_aws_cmd(f"aws ec2 terminate-instances --instance-ids {instance_id} --region {REGION}")
        continue
    run_aws_cmd(f"aws ecs wait tasks-running --cluster {CLUSTER_NAME} --tasks {cold_task_arn} --region {REGION}")
    end_time_cold = int(time.time() * 1000)
    cold_start_time = end_time_cold - start_time_cold
    print(f"冷启动完成，耗时: {cold_start_time}ms")
    # 冷启动时间戳
    cold_ts = extract_timestamps(cold_task_arn, "")
    cold_total, cold_pull, cold_prepare = (None, None, None)
    if cold_ts:
        cold_total, cold_pull, cold_prepare = calc_time(cold_ts)
    # 清理冷启动资源
    run_aws_cmd(f"aws ecs stop-task --cluster {CLUSTER_NAME} --task {cold_task_arn} --region {REGION}")
    run_aws_cmd(f"aws ec2 terminate-instances --instance-ids {instance_id} --region {REGION}")
    run_aws_cmd(f"aws ec2 wait instance-terminated --instance-ids {instance_id} --region {REGION}")
    # --- 热启动 ---
    print("--- [热启动] ---")
    start_time_hot = int(time.time() * 1000)
    hot_task_arn = run_aws_cmd(f"aws ecs start-task --cluster {CLUSTER_NAME} --task-definition {TASK_DEFINITION} --container-instances {hot_instance_arn} --region {REGION} --query 'tasks[0].taskArn' --output text 2>/dev/null")
    if not hot_task_arn or hot_task_arn == "None":
        print("错误：热启动任务创建失败。")
        continue
    run_aws_cmd(f"aws ecs wait tasks-running --cluster {CLUSTER_NAME} --tasks {hot_task_arn} --region {REGION}")
    end_time_hot = int(time.time() * 1000)
    hot_start_time = end_time_hot - start_time_hot
    print(f"热启动完成，耗时: {hot_start_time}ms")
    # 热启动时间戳
    hot_ts = extract_timestamps(hot_task_arn, "")
    hot_total, hot_pull, hot_prepare = (None, None, None)
    if hot_ts:
        hot_total, hot_pull, hot_prepare = calc_time(hot_ts)
    # 清理热启动任务
    run_aws_cmd(f"aws ecs stop-task --cluster {CLUSTER_NAME} --task {hot_task_arn} --region {REGION}")
    # --- 记录结果 ---
    time_saved = cold_start_time - hot_start_time
    print(f"本轮节省时间: {time_saved}ms")
    with open(OUTPUT_FILE, "a") as f:
        f.write(f"{i},{cold_start_time},{hot_start_time},{time_saved}\n")
    # 汇总数据
    if cold_total and hot_total:
        cold_total_times.append(cold_total)
        hot_total_times.append(hot_total)
        cold_pull_times.append(cold_pull)
        hot_pull_times.append(hot_pull)
        cold_prepare_times.append(cold_prepare)
        hot_prepare_times.append(hot_prepare)
        savings.append(time_saved)
    print(f"第{i}次结果：\n冷启动总时间={cold_total}ms，镜像拉取时间={cold_pull}ms，准备时间={cold_prepare}ms")
    print(f"热启动总时间={hot_total}ms，镜像拉取时间={hot_pull}ms，准备时间={hot_prepare}ms")
    print(f"时间节省={time_saved}ms")
    print("等待30秒进入下一轮...")
    time.sleep(30)

# --- 绘制分布图 ---
plt.figure(figsize=(18, 12))
plt.subplot(2, 3, 1)
plt.hist(cold_total_times, bins=10, alpha=0.7, color='blue', edgecolor='black')
plt.title('Cold Start Total Time Distribution')
plt.xlabel('Total Time (ms)')
plt.ylabel('Frequency')
plt.subplot(2, 3, 2)
plt.hist(hot_total_times, bins=10, alpha=0.7, color='green', edgecolor='black')
plt.title('Hot Start Total Time Distribution')
plt.xlabel('Total Time (ms)')
plt.ylabel('Frequency')
plt.subplot(2, 3, 3)
plt.hist(cold_pull_times, bins=10, alpha=0.7, color='purple', edgecolor='black')
plt.title('Cold Start Image Pull Time Distribution')
plt.xlabel('Pull Time (ms)')
plt.ylabel('Frequency')
plt.subplot(2, 3, 4)
plt.hist(hot_pull_times, bins=10, alpha=0.7, color='orange', edgecolor='black')
plt.title('Hot Start Image Pull Time Distribution')
plt.xlabel('Pull Time (ms)')
plt.ylabel('Frequency')
plt.subplot(2, 3, 5)
plt.hist(cold_prepare_times, bins=10, alpha=0.7, color='cyan', edgecolor='black')
plt.title('Cold Start Preparation Time Distribution')
plt.xlabel('Preparation Time (ms)')
plt.ylabel('Frequency')
plt.subplot(2, 3, 6)
plt.hist(hot_prepare_times, bins=10, alpha=0.7, color='red', edgecolor='black')
plt.title('Hot Start Preparation Time Distribution')
plt.xlabel('Preparation Time (ms)')
plt.ylabel('Frequency')
plt.tight_layout()
plt.savefig('startup_time_summary_ec2_privateimage.png')
# 单独保存每张图
fig, ax = plt.subplots()
ax.hist(cold_total_times, bins=10, alpha=0.7, color='blue', edgecolor='black')
ax.set_title('Cold Start Total Time Distribution')
ax.set_xlabel('Total Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/cold_start_total_time_PrivateImage.png')
plt.close(fig)
fig, ax = plt.subplots()
ax.hist(hot_total_times, bins=10, alpha=0.7, color='green', edgecolor='black')
ax.set_title('Hot Start Total Time Distribution')
ax.set_xlabel('Total Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/hot_start_total_time_PrivateImage.png')
plt.close(fig)
fig, ax = plt.subplots()
ax.hist(cold_pull_times, bins=10, alpha=0.7, color='purple', edgecolor='black')
ax.set_title('Cold Start Image Pull Time Distribution')
ax.set_xlabel('Pull Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/cold_start_pull_time_PrivateImage.png')
plt.close(fig)
fig, ax = plt.subplots()
ax.hist(hot_pull_times, bins=10, alpha=0.7, color='orange', edgecolor='black')
ax.set_title('Hot Start Image Pull Time Distribution')
ax.set_xlabel('Pull Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/hot_start_pull_time_PrivateImage.png')
plt.close(fig)
fig, ax = plt.subplots()
ax.hist(cold_prepare_times, bins=10, alpha=0.7, color='cyan', edgecolor='black')
ax.set_title('Cold Start Preparation Time Distribution')
ax.set_xlabel('Preparation Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/cold_start_prepare_time_PrivateImage.png')
plt.close(fig)
fig, ax = plt.subplots()
ax.hist(hot_prepare_times, bins=10, alpha=0.7, color='red', edgecolor='black')
ax.set_title('Hot Start Preparation Time Distribution')
ax.set_xlabel('Preparation Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('images/hot_start_prepare_time_PrivateImage.png')
plt.close(fig)

# --- 堆栈清理 ---
print(">>> 第5步：所有测试完成，清理 CloudFormation 堆栈 ...")
delete_ret = subprocess.run(["./delete.sh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if delete_ret.returncode != 0:
    print("警告：堆栈清理脚本执行失败。请手动检查 AWS 控制台。")

# 恢复标准输出并关闭文件
sys.stdout = sys.__stdout__
output_log.close()

print("=========================================")
print(f"测试全部完成！结果已保存到 {OUTPUT_FILE}")
print("输出日志已保存到 ec2_batch_output.txt")
print("=========================================")
