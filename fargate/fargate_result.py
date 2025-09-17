import subprocess
import re
import json
import matplotlib.pyplot as plt

# 初始化存储数据的列表
cold_times = []
hot_times = []
savings = []

# 正则表达式模式用于匹配输出行
cold_pattern = r'冷启动时间: (\d+)ms'
hot_pattern = r'热启动时间: (\d+)ms'
saving_pattern = r'时间节省: (-?\d+)ms'

# 帮助函数：从输出中提取某一段时间戳 JSON（基于中文标签“冷启动时间戳：”/“热启动时间戳：”）
def extract_timestamps(full_output: str, label: str):
    idx = full_output.find(label)
    if idx == -1:
        return None
    # 截取从标签开始的一段文本
    sub = full_output[idx:]
    # 找第一个 '{' 和对应的第一个 '}'（AWS CLI 这里是单层对象）
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
        # 解析失败时尝试用正则兜底
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

# 执行100次循环
for i in range(20):
    print(f"\nRunning iteration {i+1}/20 ...")

    try:
        # 执行三个脚本
        subprocess.run(['./create.sh'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(['./script.sh'], check=True, capture_output=True, text=True)
        subprocess.run(['./delete.sh'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 从输出中提取数据
        output = result.stdout
        
        cold_match = re.search(cold_pattern, output)
        hot_match = re.search(hot_pattern, output)
        saving_match = re.search(saving_pattern, output)
        
        if cold_match and hot_match and saving_match:
            cold_time = int(cold_match.group(1))
            hot_time = int(hot_match.group(1))
            saving = int(saving_match.group(1))
            
            cold_times.append(cold_time)
            hot_times.append(hot_time)
            savings.append(saving)
            
            print(f"Iteration {i+1} result: \nCold Start={cold_time}ms, Hot Start={hot_time}ms, Saving={saving}ms")

            # 额外解析并输出时间戳详情
            cold_ts = extract_timestamps(output, "冷启动时间戳：")
            hot_ts = extract_timestamps(output, "热启动时间戳：")

            def fmt(ts_dict):
                if not ts_dict:
                    return "(timestamps not found)"
                return (
                    f"createdAt={ts_dict.get('createdAt','N/A')}\n"
                    f"pullStartedAt={ts_dict.get('pullStartedAt','N/A')}\n"
                    f"pullStoppedAt={ts_dict.get('pullStoppedAt','N/A')}\n"
                    f"startedAt={ts_dict.get('startedAt','N/A')}"
                )

            print(f"  Cold timestamps: {fmt(cold_ts)}")
            print(f"  Hot  timestamps: {fmt(hot_ts)}")
        else:
            print(f"Iteration {i+1}: Failed to extract complete data from output")
            
    except Exception as e:
        print(f"Iteration {i+1} error: {e}")

# 绘制分布图
plt.figure(figsize=(15, 5))


# Cold Start Time Distribution
plt.subplot(1, 3, 1)
plt.hist(cold_times, bins=10, alpha=0.7, color='blue', edgecolor='black')
plt.title('Cold Start Time Distribution')
plt.xlabel('Time (ms)')
plt.ylabel('Frequency')

# Hot Start Time Distribution
plt.subplot(1, 3, 2)
plt.hist(hot_times, bins=10, alpha=0.7, color='green', edgecolor='black')
plt.title('Hot Start Time Distribution')
plt.xlabel('Time (ms)')
plt.ylabel('Frequency')

# Time Saving Distribution
plt.subplot(1, 3, 3)
plt.hist(savings, bins=15, alpha=0.7, color='orange', edgecolor='black')
plt.title('Time Saving Distribution')
plt.xlabel('Saving Time (ms)')
plt.ylabel('Frequency')
plt.axvline(0, color='red', linestyle='--', linewidth=1, label='Zero Line')
plt.legend()

plt.tight_layout()
plt.savefig('startup_time_distribution.png')