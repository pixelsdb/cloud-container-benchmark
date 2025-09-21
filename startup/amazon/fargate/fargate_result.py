
import subprocess
import re
import json
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt

# 数据存储
cold_total_times = []
hot_total_times = []
cold_pull_times = []
hot_pull_times = []
cold_prepare_times = []
hot_prepare_times = []
savings = []

# 正则表达式
cold_pattern = r'冷启动时间: (\d+)ms'
hot_pattern = r'热启动时间: (\d+)ms'
saving_pattern = r'时间节省: (-?\d+)ms'

# 时间戳正则
def extract_timestamps(full_output: str, label: str):
    idx = full_output.find(label)
    if idx == -1:
        return None
    sub = full_output[idx:]
    start = sub.find('{')
    if start == -1:
        return None
    end = sub.find('}', start)
    if end == -1:
        return None
    json_str = sub[start:end+1]
    try:
        data = json.loads(json_str)
        return data
    except Exception:
        pattern = r'"createdAt":\s*"(?P<created>[^"]+)".*?"startedAt":\s*"(?P<started>[^"]+)".*?"pullStartedAt":\s*(?:"(?P<pullStarted>[^"]+)"|null).*?"pullStoppedAt":\s*(?:"(?P<pullStopped>[^"]+)"|null)'
        m = re.search(pattern, json_str, re.S)
        if m:
            return {
                "createdAt": m.group('created'),
                "startedAt": m.group('started'),
                "pullStartedAt": m.group('pullStarted'),
                "pullStoppedAt": m.group('pullStopped')
            }
        return None

def calc_time(ts):
    # 返回总时间、拉取时间、准备时间（单位ms）
    from datetime import datetime
    def to_ms(s):
        if not s or s == 'null':
            return None
        # AWS 时间戳格式: 2025-09-18T01:41:57.128000+08:00
        try:
            dt = datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f")
            # 处理时区
            if '+' in s:
                offset = int(s[-6:-3])
                dt = dt
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    created = to_ms(ts.get('createdAt'))
    started = to_ms(ts.get('startedAt'))
    pull_started = to_ms(ts.get('pullStartedAt'))
    pull_stopped = to_ms(ts.get('pullStoppedAt'))
    total = started - created if created and started else None
    pull = pull_stopped - pull_started if pull_started and pull_stopped else None
    prepare = None
    if total is not None and pull is not None:
        prepare = total - pull
    return total, pull, prepare

for i in range(100):
    print(f"\n第{i+1}次测试 ...")
    try:
        subprocess.run(['./create.sh'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(['./script.sh'], check=True, capture_output=True, text=True)
        subprocess.run(['./delete.sh'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output = result.stdout

        cold_match = re.search(cold_pattern, output)
        hot_match = re.search(hot_pattern, output)
        saving_match = re.search(saving_pattern, output)

        cold_ts = extract_timestamps(output, "冷启动时间戳：")
        hot_ts = extract_timestamps(output, "热启动时间戳：")

        cold_total, cold_pull, cold_prepare = (None, None, None)
        hot_total, hot_pull, hot_prepare = (None, None, None)
        if cold_ts:
            cold_total, cold_pull, cold_prepare = calc_time(cold_ts)
        if hot_ts:
            hot_total, hot_pull, hot_prepare = calc_time(hot_ts)

        if cold_match and hot_match and saving_match and cold_total and hot_total:
            cold_time = int(cold_match.group(1))
            hot_time = int(hot_match.group(1))
            saving = int(saving_match.group(1))
            cold_total_times.append(cold_total)
            hot_total_times.append(hot_total)
            cold_pull_times.append(cold_pull)
            hot_pull_times.append(hot_pull)
            cold_prepare_times.append(cold_prepare)
            hot_prepare_times.append(hot_prepare)
            savings.append(saving)

            print(f"第{i+1}次结果：\n冷启动总时间={cold_total}ms，镜像拉取时间={cold_pull}ms，准备时间={cold_prepare}ms")
            print(f"热启动总时间={hot_total}ms，镜像拉取时间={hot_pull}ms，准备时间={hot_prepare}ms")
            print(f"时间节省={saving}ms")
        else:
            print(f"第{i+1}次：未能完整提取数据")
    except Exception as e:
        print(f"第{i+1}次出错: {e}")

# 绘制分布图
plt.figure(figsize=(18, 12))

# 1. Cold Start Total Time
plt.subplot(2, 3, 1)
plt.hist(cold_total_times, bins=10, alpha=0.7, color='blue', edgecolor='black')
plt.title('Cold Start Total Time Distribution')
plt.xlabel('Total Time (ms)')
plt.ylabel('Frequency')

# 2. Hot Start Total Time
plt.subplot(2, 3, 2)
plt.hist(hot_total_times, bins=10, alpha=0.7, color='green', edgecolor='black')
plt.title('Hot Start Total Time Distribution')
plt.xlabel('Total Time (ms)')
plt.ylabel('Frequency')

# 3. Cold Start Pull Time
plt.subplot(2, 3, 3)
plt.hist(cold_pull_times, bins=10, alpha=0.7, color='purple', edgecolor='black')
plt.title('Cold Start Image Pull Time Distribution')
plt.xlabel('Pull Time (ms)')
plt.ylabel('Frequency')

# 4. Hot Start Pull Time
plt.subplot(2, 3, 4)
plt.hist(hot_pull_times, bins=10, alpha=0.7, color='orange', edgecolor='black')
plt.title('Hot Start Image Pull Time Distribution')
plt.xlabel('Pull Time (ms)')
plt.ylabel('Frequency')

# 5. Cold Start Prepare Time
plt.subplot(2, 3, 5)
plt.hist(cold_prepare_times, bins=10, alpha=0.7, color='cyan', edgecolor='black')
plt.title('Cold Start Preparation Time Distribution')
plt.xlabel('Preparation Time (ms)')
plt.ylabel('Frequency')

# 6. Hot Start Prepare Time
plt.subplot(2, 3, 6)
plt.hist(hot_prepare_times, bins=10, alpha=0.7, color='red', edgecolor='black')
plt.title('Hot Start Preparation Time Distribution')
plt.xlabel('Preparation Time (ms)')
plt.ylabel('Frequency')

plt.tight_layout()
plt.savefig('startup_time_summary.png')

# 单独保存每张图
fig, ax = plt.subplots()
ax.hist(cold_total_times, bins=10, alpha=0.7, color='blue', edgecolor='black')
ax.set_title('Cold Start Total Time Distribution')
ax.set_xlabel('Total Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('cold_start_total_time_PrivateImage.png')
plt.close(fig)

fig, ax = plt.subplots()
ax.hist(hot_total_times, bins=10, alpha=0.7, color='green', edgecolor='black')
ax.set_title('Hot Start Total Time Distribution')
ax.set_xlabel('Total Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('hot_start_total_time_PrivateImage.png')
plt.close(fig)

fig, ax = plt.subplots()
ax.hist(cold_pull_times, bins=10, alpha=0.7, color='purple', edgecolor='black')
ax.set_title('Cold Start Image Pull Time Distribution')
ax.set_xlabel('Pull Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('cold_start_pull_time_PrivateImage.png')
plt.close(fig)

fig, ax = plt.subplots()
ax.hist(hot_pull_times, bins=10, alpha=0.7, color='orange', edgecolor='black')
ax.set_title('Hot Start Image Pull Time Distribution')
ax.set_xlabel('Pull Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('hot_start_pull_time_PrivateImage.png')
plt.close(fig)

fig, ax = plt.subplots()
ax.hist(cold_prepare_times, bins=10, alpha=0.7, color='cyan', edgecolor='black')
ax.set_title('Cold Start Preparation Time Distribution')
ax.set_xlabel('Preparation Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('cold_start_prepare_time_PrivateImage.png')
plt.close(fig)

fig, ax = plt.subplots()
ax.hist(hot_prepare_times, bins=10, alpha=0.7, color='red', edgecolor='black')
ax.set_title('Hot Start Preparation Time Distribution')
ax.set_xlabel('Preparation Time (ms)')
ax.set_ylabel('Frequency')
fig.savefig('hot_start_prepare_time_PrivateImage.png')
plt.close(fig)