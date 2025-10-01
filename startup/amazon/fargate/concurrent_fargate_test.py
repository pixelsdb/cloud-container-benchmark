import boto3
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
import csv
import sys
import atexit
import os
import argparse
import threading
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# =============== 配置 ===============
REGION = "us-east-2"
STACK_NAME = "fargate-test"
CLUSTER_NAME = "fargate-startup-test-cluster"
TASK_DEFINITION = "startup-test-task"
NUM_TASKS = 100
BATCH_SIZE = 10  # 每次请求启动的任务数量，最大10个
POLL_BATCH = 100

# =============== 参数解析 ===============
parser = argparse.ArgumentParser(description='Concurrent Fargate tasks startup benchmark')
parser.add_argument('--image-type', choices=['privateimage', 'publicimage', 'private', 'public'], required=True, help='选择使用 privateimage 或 publicimage（必选）')
args = parser.parse_args()
image_type = args.image_type
if image_type == 'private':
    image_type = 'privateimage'
elif image_type == 'public':
    image_type = 'publicimage'

# =============== AWS 客户端初始化 ===============
ecs_client = boto3.client('ecs', region_name=REGION)
cloudformation_client = boto3.client('cloudformation', region_name=REGION)

# =============== 工具函数 ===============

def setup_stdout_tee(log_path: str):
    """将标准输出同步写入到指定日志文件"""
    class _StdoutTee:
        def __init__(self, original, file_obj):
            self._original = original
            self._file = file_obj
        def write(self, data):
            self._original.write(data)
            self._file.write(data)
            try:
                self._original.flush()
            except Exception:
                pass
            try:
                self._file.flush()
            except Exception:
                pass
        def flush(self):
            try:
                self._original.flush()
            except Exception:
                pass
            try:
                self._file.flush()
            except Exception:
                pass

    f = open(log_path, 'w', buffering=1, encoding='utf-8')
    atexit.register(f.close)
    sys.stdout = _StdoutTee(sys.stdout, f)

def get_stack_output(output_key: str) -> Optional[str]:
    """获取 CloudFormation 堆栈输出"""
    try:
        response = cloudformation_client.describe_stacks(StackName=STACK_NAME)
        stacks = response['Stacks']
        if stacks:
            outputs = stacks[0].get('Outputs', [])
            for output in outputs:
                if output['OutputKey'] == output_key:
                    return output['OutputValue']
        return None
    except Exception as e:
        print(f"获取堆栈输出失败: {e}")
        return None

def run_tasks_batch(network_config: Dict, count: int) -> List[str]:
    """使用 SDK 批量启动任务"""
    try:
        response = ecs_client.run_task(
            cluster=CLUSTER_NAME,
            taskDefinition=TASK_DEFINITION,
            launchType='FARGATE',
            platformVersion='LATEST',
            networkConfiguration=network_config,
            count=count  # 关键：一次启动多个任务
        )
        
        # 提取成功启动的任务 ARN
        task_arns = [task['taskArn'] for task in response.get('tasks', [])]
        
        # 处理失败的任务
        failures = response.get('failures', [])
        if failures:
            print(f"批量启动失败: {len(failures)} 个任务失败")
            for failure in failures:
                print(f"  - ARN: {failure.get('arn')}, 原因: {failure.get('reason')}")
        
        print(f"批量启动成功: {len(task_arns)}/{count} 个任务")
        return task_arns
        
    except Exception as e:
        print(f"批量启动任务失败: {e}")
        return []

def wait_tasks_stopped(task_arns: List[str]):
    """等待任务停止 - 使用 ECS waiter 分批处理（接口保持不变）"""
    waiter = ecs_client.get_waiter('tasks_stopped')
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
        print(f"等待 {len(batch)} 个任务停止（waiter）...")
        try:
            waiter.wait(
                cluster=CLUSTER_NAME,
                tasks=batch,
                WaiterConfig={
                    'Delay': 6,
                    'MaxAttempts': 100
                }
            )
            print("批次任务已全部停止")
        except Exception as e:
            print(f"等待任务停止失败: {e}")

def wait_tasks_running(task_arns: List[str]):
    """等待任务运行 - 使用 ECS waiter 分批处理（接口保持不变）"""
    waiter = ecs_client.get_waiter('tasks_running')
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
        print(f"等待 {len(batch)} 个任务运行（waiter）...")
        try:
            waiter.wait(
                cluster=CLUSTER_NAME,
                tasks=batch,
                WaiterConfig={
                    'Delay': 2,
                    'MaxAttempts': 100
                }
            )
            print("批次任务已全部运行")
        except Exception as e:
            print(f"等待任务运行失败: {e}")

def describe_tasks(task_arns: List[str]) -> List[Dict]:
    """描述任务状态 - 使用 SDK"""
    all_tasks = []
    for i in range(0, len(task_arns), POLL_BATCH):
        batch = task_arns[i:i+POLL_BATCH]
        if not batch:
            continue
            
        try:
            response = ecs_client.describe_tasks(
                cluster=CLUSTER_NAME,
                tasks=batch
            )
            all_tasks.extend(response.get('tasks', []))
        except Exception as e:
            print(f"描述任务失败: {e}")
    
    return all_tasks

def stop_tasks_batch(task_arns: List[str]):
    """批量停止任务"""
    for arn in task_arns:
        try:
            ecs_client.stop_task(
                cluster=CLUSTER_NAME,
                task=arn,
                reason='benchmark finished'
            )
        except Exception as e:
            print(f"停止任务 {arn} 失败: {e}")

def to_ms(ts: Optional[object]) -> Optional[int]:
    """时间戳转换：支持 datetime 对象、带空格和时区的字符串、ISO8601/Z 字符串"""
    if ts is None:
        return None
    # 直接是 datetime
    if isinstance(ts, datetime):
        try:
            return int(ts.timestamp() * 1000)
        except Exception:
            return None
    # 其他转成字符串再解析
    s = str(ts).strip()
    # 优先尝试使用 python-dateutil，能解析带时区偏移
    try:
        from dateutil import parser as dateparser  # type: ignore
        dt = dateparser.isoparse(s)
        return int(dt.timestamp() * 1000)
    except Exception:
        pass
    # 兼容形如 'YYYY-MM-DD HH:MM:SS.microsec+08:00'
    try:
        # 如果包含 'T' 则尝试 ISO，包含空格则尝试空格格式。
        if 'T' in s or 'Z' in s or '+' in s or '-' in s[10:]:
            # datetime.fromisoformat 支持 'YYYY-MM-DD HH:MM:SS.microsec+HH:MM'
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        # 没有时区且使用空格的简单格式（无偏移）
        dt = datetime.strptime(s[:26], "%Y-%m-%d %H:%M:%S.%f")
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

def compute_times(task: Dict) -> Dict:
    """计算时间指标"""
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

def main():
    # 启用标准输出同步到日志文件
    log_file = f"concurrent_fargate_test_{image_type}.log"
    setup_stdout_tee(log_file)

    print(">>> 获取 CloudFormation 堆栈输出...")
    subnet_id = get_stack_output("SubnetId")
    sg_id = get_stack_output("SecurityGroupId")
    print(f"子网ID: {subnet_id}")
    print(f"安全组ID: {sg_id}")
    
    if not subnet_id or not sg_id:
        print("错误：无法获取 SubnetId 或 SecurityGroupId，请先创建/检查堆栈。")
        return

    # 网络配置
    network_config = {
        'awsvpcConfiguration': {
            'subnets': [subnet_id],
            'securityGroups': [sg_id],
            'assignPublicIp': 'ENABLED'
        }
    }

    # 1) 暖机任务
    print(">>> 开始暖机任务...")
    warm_task_arns = run_tasks_batch(network_config, 1)
    if not warm_task_arns:
        print("错误：暖机任务创建失败。")
        return
        
    print(f"暖机任务ARN: {warm_task_arns[0]}")
    print("等待暖机任务运行...")
    wait_tasks_running(warm_task_arns)
    
    # 停止暖机任务
    print("停止暖机任务...")
    stop_tasks_batch(warm_task_arns)
    wait_tasks_stopped(warm_task_arns)
    print("暖机完成并已清理。")

    # 2) 批量启动并发任务（多线程并行发送，每个线程等待本批任务 RUNNING）
    print(f">>> 批量启动 {NUM_TASKS} 个任务（并行批次）...")
    # t_launch_start = time.time()
    # launch_to_running_ms: Optional[int] = None
    all_task_arns: List[str] = []
    lock = threading.Lock()

    # 预先计算每个批次的任务数，避免并发修改导致计算不一致
    num_batches = (NUM_TASKS + BATCH_SIZE - 1) // BATCH_SIZE
    batch_sizes = [min(BATCH_SIZE, NUM_TASKS - i * BATCH_SIZE) for i in range(num_batches)]
    batch_sizes = [s for s in batch_sizes if s > 0]

    def worker(batch_index: int, count: int):
        print(f"批次 {batch_index + 1}/{len(batch_sizes)}: 启动 {count} 个任务...")
        batch_arns = run_tasks_batch(network_config, count)
        if not batch_arns:
            print(f"批次 {batch_index + 1}: 未创建任何任务。")
            return
        with lock:
            all_task_arns.extend(batch_arns)
        # 等待该批次进入 RUNNING
        wait_tasks_running(batch_arns)
        print(f"批次 {batch_index + 1}: 已全部进入 RUNNING")

    threads: List[threading.Thread] = []
    for idx, size in enumerate(batch_sizes):
        t = threading.Thread(target=worker, args=(idx, size), daemon=True)
        threads.append(t)
        t.start()

    # 等待所有线程完成（即全部批次已进入 RUNNING）
    for t in threads:
        t.join()

    print(f"总共成功创建任务数: {len(all_task_arns)}/{NUM_TASKS}")
    if not all_task_arns:
        print("错误：没有成功创建任何任务。")
        return

    # # 记录从发起批量启动到全部进入 RUNNING 的耗时（父进程维度）
    # launch_to_running_ms = int((time.time() - t_launch_start) * 1000)
    print("所有任务已运行。开始收集时间戳...")

    # 4) 收集时间数据
    raw_tasks = describe_tasks(all_task_arns)
    records = [compute_times({
        "taskArn": t.get("taskArn"),
        "createdAt": t.get("createdAt"),
        "startedAt": t.get("startedAt"),
        "pullStartedAt": t.get("pullStartedAt"),
        "pullStoppedAt": t.get("pullStoppedAt"),
    }) for t in raw_tasks]

    # 5) 显示结果
    print(">>> 任务时间统计 (前10条)...")
    for i, r in enumerate(records[:10], start=1):
        print(f"任务{i}: 总时间={r['total_ms']}ms, 镜像拉取={r['pull_ms']}ms, 准备={r['prepare_ms']}ms")

    # 6) 生成图表
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
    images_dir = os.path.join('.', 'images', image_type)
    os.makedirs(images_dir, exist_ok=True)
    out_png = os.path.join(images_dir, f'concurrent_startup_time.png')
    plt.savefig(out_png, dpi=300, bbox_inches='tight')

    # 7) 清理资源
    print(">>> 停止所有任务以回收资源...")
    stop_tasks_batch(all_task_arns)
    wait_tasks_stopped(all_task_arns)
    print("所有任务已停止并回收。")

    # # 最终输出本次实验的关键耗时
    # if launch_to_running_ms is not None:
    #     print(f">>> 并行批次从发起到全部 RUNNING 的耗时: {launch_to_running_ms} ms")

    print("测试完成")

if __name__ == "__main__":
    main()