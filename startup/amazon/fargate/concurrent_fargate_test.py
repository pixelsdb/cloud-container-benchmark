import subprocess
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
import csv
import sys
import atexit
import os
import argparse
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，避免 Wayland/Qt 问题
import matplotlib.pyplot as plt

# =============== 配置 ===============
REGION = "us-east-2"
STACK_NAME = "fargate-test"
CLUSTER_NAME = "fargate-startup-test-cluster"
TASK_DEFINITION = "startup-test-task"
NUM_TASKS = 100
POLL_BATCH = 20  # 分批等待/查询，避免参数过长或限流
OUTPUT_CSV = "concurrent_fargate_tasks.csv"

# =============== 参数：镜像类型及输出目录 ===============
parser = argparse.ArgumentParser(description='Concurrent Fargate tasks startup benchmark')
parser.add_argument('--image-type', choices=['privateimage', 'publicimage', 'private', 'public'], required=True, help='选择使用 privateimage 或 publicimage（必选）')
args = parser.parse_args()
image_type = args.image_type
if image_type == 'private':
    image_type = 'privateimage'
elif image_type == 'public':
    image_type = 'publicimage'

out_dir = os.path.join('images', image_type)
os.makedirs(out_dir, exist_ok=True)

# =============== 日志 Tee（同时输出到控制台与文件） ===============
LOG_FILE = f"concurrent_fargate_test_{image_type}.log"

class _Tee:
    def __init__(self, *files):
        self._files = files
    def write(self, data):
        for f in self._files:
            try:
                f.write(data)
            except Exception:
                pass
    def flush(self):
        for f in self._files:
            try:
                f.flush()
            except Exception:
                pass

_orig_stdout = sys.stdout
_orig_stderr = sys.stderr
_log_fp = open(LOG_FILE, "w", encoding="utf-8")
sys.stdout = _Tee(_orig_stdout, _log_fp)
sys.stderr = _Tee(_orig_stderr, _log_fp)

@atexit.register
def _restore_std_streams():
    try:
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
    finally:
        try:
            _log_fp.close()
        except Exception:
            pass

# =============== 工具函数 ===============

def run(cmd: List[str], quiet: bool = True) -> Optional[str]:
    """运行命令并返回 stdout 字符串，失败返回 None。"""
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not quiet:
            print(f"命令失败: {' '.join(cmd)}\n{e.stderr}")
        return None


def get_stack_output(output_key: str) -> Optional[str]:
    return run([
        "aws", "cloudformation", "describe-stacks",
        "--stack-name", STACK_NAME,
        "--query", f"Stacks[0].Outputs[?OutputKey=='{output_key}'].OutputValue",
        "--output", "text",
        "--region", REGION
    ])


def get_network_config(subnet_id: str, sg_id: str) -> str:
    # 传给 aws cli 的 JSON 字符串
    return json.dumps({
        "awsvpcConfiguration": {
            "subnets": [subnet_id],
            "securityGroups": [sg_id],
            "assignPublicIp": "ENABLED"
        }
    })


def run_task(network_conf: str) -> Optional[str]:
    return run([
        "aws", "ecs", "run-task",
        "--cluster", CLUSTER_NAME,
        "--task-definition", TASK_DEFINITION,
        "--launch-type", "FARGATE",
        "--platform-version", "LATEST",
        "--network-configuration", network_conf,
        "--region", REGION,
        "--query", "tasks[0].taskArn",
        "--output", "text"
    ], quiet=True)


def wait_tasks_stopped(task_arns: List[str]):
    # 分批调用 wait，避免过长参数或限流
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
        run([
            "aws", "ecs", "wait", "tasks-stopped",
            "--cluster", CLUSTER_NAME,
            "--tasks", *batch,
            "--region", REGION
        ], quiet=False)


def wait_tasks_running(task_arns: List[str]):
    # 分批等待任务进入 RUNNING 状态
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
        run([
            "aws", "ecs", "wait", "tasks-running",
            "--cluster", CLUSTER_NAME,
            "--tasks", *batch,
            "--region", REGION
        ], quiet=False)


def describe_tasks(task_arns: List[str]) -> List[Dict]:
    tasks: List[Dict] = []
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
        out = run([
            "aws", "ecs", "describe-tasks",
            "--cluster", CLUSTER_NAME,
            "--tasks", *batch,
            "--region", REGION,
            "--output", "json"
        ], quiet=False)
        if out:
            try:
                data = json.loads(out)
                tasks.extend(data.get("tasks", []))
            except Exception:
                pass
    return tasks


def to_ms(ts: Optional[str]) -> Optional[int]:
    if not ts or ts == "null":
        return None
    try:
        # 示例: 2025-09-18T01:41:57.128000+08:00 -> 取到微秒位置
        dt = datetime.strptime(ts[:26], "%Y-%m-%dT%H:%M:%S.%f")
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def compute_times(task: Dict) -> Dict:
    created = to_ms(task.get("createdAt"))
    started = to_ms(task.get("startedAt"))
    pull_started = to_ms(task.get("pullStartedAt"))
    pull_stopped = to_ms(task.get("pullStoppedAt"))
    total = (started - created) if (created is not None and started is not None) else None
    pull = (pull_stopped - pull_started) if (pull_started is not None and pull_stopped is not None) else None
    prepare = (total - pull) if (total is not None and pull is not None) else None
    return {
        "createdAt": task.get("createdAt"),
        "startedAt": task.get("startedAt"),
        "pullStartedAt": task.get("pullStartedAt"),
        "pullStoppedAt": task.get("pullStoppedAt"),
        "total_ms": total,
        "pull_ms": pull,
        "prepare_ms": prepare,
        "taskArn": task.get("taskArn")
    }

# =============== 主流程 ===============

print(">>> 获取 CloudFormation 堆栈输出...")
subnet_id = get_stack_output("SubnetId")
sg_id = get_stack_output("SecurityGroupId")
print(f"子网ID: {subnet_id}")
print(f"安全组ID: {sg_id}")
if not subnet_id or not sg_id:
    print("错误：无法获取 SubnetId 或 SecurityGroupId，请先创建/检查堆栈。")
    raise SystemExit(1)

network_conf = get_network_config(subnet_id, sg_id)

# 1) 先暖机：运行1个任务，并等待其结束
print(">>> 开始暖机任务...")
warm_task_arn = run_task(network_conf)
if not warm_task_arn or warm_task_arn == "None":
    print("错误：暖机任务创建失败。")
    raise SystemExit(1)
print(f"暖机任务ARN: {warm_task_arn}")
print("等待暖机任务进入 RUNNING...")
wait_tasks_running([warm_task_arn])
print("暖机任务已运行，进行回收...")
# 暖机完成后立即停止该任务并等待停止
run([
    "aws", "ecs", "stop-task",
    "--cluster", CLUSTER_NAME,
    "--task", warm_task_arn,
    "--reason", "warm-up cleanup",
    "--region", REGION
], quiet=False)
wait_tasks_stopped([warm_task_arn])
print("暖机完成并已清理。")

# 2) 并发启动 NUM_TASKS 个任务
print(f">>> 并发启动 {NUM_TASKS} 个任务...")
all_task_arns: List[str] = []
for i in range(NUM_TASKS):
    arn = run_task(network_conf)
    if arn and arn != "None":
        all_task_arns.append(arn)
    else:
        print(f"第{i+1}个任务创建失败")
    # 小的间隔，降低 API 限流风险
    time.sleep(0.05)

print(f"已创建任务数: {len(all_task_arns)}/{NUM_TASKS}")
if not all_task_arns:
    print("错误：没有成功创建任何任务。")
    raise SystemExit(1)

# 3) 等待全部任务停止
print("等待所有任务进入 RUNNING (这可能需要几分钟)...")
wait_tasks_running(all_task_arns)
print("所有任务已运行。开始收集时间戳...")

# 4) 批量查询并计算时间
raw_tasks = describe_tasks(all_task_arns)

# 从 describe-tasks 返回中提取我们关心的字段
records: List[Dict] = []
for t in raw_tasks:
    rec = compute_times({
        "taskArn": t.get("taskArn"),
        "createdAt": t.get("createdAt"),
        "startedAt": t.get("startedAt"),
        "pullStartedAt": t.get("pullStartedAt"),
        "pullStoppedAt": t.get("pullStoppedAt"),
    })
    records.append(rec)

# 5) 打印简要中文摘要，并导出 CSV
print(">>> 任务时间统计 (仅显示前10条预览)...")
for i, r in enumerate(records[:10], start=1):
    print(f"任务{i}: 总时间={r['total_ms']}ms，镜像拉取={r['pull_ms']}ms，准备={r['prepare_ms']}ms")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=[
        "index", "taskArn", "createdAt", "startedAt", "pullStartedAt", "pullStoppedAt", "total_ms", "pull_ms", "prepare_ms"
    ])
    w.writeheader()
    for idx, r in enumerate(records, start=1):
        row = {"index": idx}
        row.update(r)
        w.writerow(row)
print(f"明细已保存: {OUTPUT_CSV}")

# 6) 作图（英文标签），过滤 None
all_total = [r["total_ms"] for r in records if r["total_ms"] is not None]
all_pull = [r["pull_ms"] for r in records if r["pull_ms"] is not None]
all_prepare = [r["prepare_ms"] for r in records if r["prepare_ms"] is not None]

plt.figure(figsize=(18, 5))

plt.subplot(1, 3, 1)
if all_total:
    plt.hist(all_total, bins=15, alpha=0.7, color='steelblue', edgecolor='black')
plt.title('Concurrent Tasks Total Time Distribution')
plt.xlabel('Total Time (ms)')
plt.ylabel('Frequency')

plt.subplot(1, 3, 2)
if all_pull:
    plt.hist(all_pull, bins=15, alpha=0.7, color='orange', edgecolor='black')
plt.title('Concurrent Tasks Image Pull Time Distribution')
plt.xlabel('Pull Time (ms)')
plt.ylabel('Frequency')

plt.subplot(1, 3, 3)
if all_prepare:
    plt.hist(all_prepare, bins=15, alpha=0.7, color='seagreen', edgecolor='black')
plt.title('Concurrent Tasks Preparation Time Distribution')
plt.xlabel('Preparation Time (ms)')
plt.ylabel('Frequency')

plt.tight_layout()
plt.savefig(os.path.join(out_dir, 'concurrent_startup_time_summary.png'), dpi=300, bbox_inches='tight')

# 分别保存单图
for data, title, fname, color, xlabel in [
    (all_total, 'Concurrent Tasks Total Time Distribution', 'concurrent_total_time.png', 'steelblue', 'Total Time (ms)'),
    (all_pull, 'Concurrent Tasks Image Pull Time Distribution', 'concurrent_pull_time.png', 'orange', 'Pull Time (ms)'),
    (all_prepare, 'Concurrent Tasks Preparation Time Distribution', 'concurrent_prepare_time.png', 'seagreen', 'Preparation Time (ms)'),
]:
    fig, ax = plt.subplots()
    if data:
        ax.hist(data, bins=15, alpha=0.7, color=color, edgecolor='black')
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Frequency')
    fig.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
    plt.close(fig)

# 7) 主动停止全部运行中的任务，并等待停止以回收
print(">>> 停止所有并发任务以回收资源...")
for arn in all_task_arns:
    run([
        "aws", "ecs", "stop-task",
        "--cluster", CLUSTER_NAME,
        "--task", arn,
        "--reason", "benchmark finished",
        "--region", REGION
    ], quiet=True)
print("等待所有任务停止...")
wait_tasks_stopped(all_task_arns)
print("所有任务已停止并回收。")

print(f"所有图表已保存到: {out_dir}")
print(f"日志已保存到: {LOG_FILE}")
