#!/usr/bin/env python3
"""
Seedance 2.0 文生视频示例（模式3：纯提示词 / 文生视频）。

对应 docs/openrouter_api_guide.md §2.7 模式3。人物用文字描述，规避真人检测与版权审核。

用法：
    export OPENROUTER_API_KEY=gws_xxx  # 或提前运行一次把 key 缓存到 ~/.openrouter_cache
    python scripts/seedance_text2video.py
"""
import os, sys, time, json
import urllib.request, urllib.error

GATEWAY = os.environ.get("OPENROUTER_BASE_URL", "https://gateway.runloop.ai")

# 优先用环境变量，否则从缓存加载
API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    cache = os.path.expanduser("~/.openrouter_cache")
    if os.path.exists(cache):
        with open(cache) as f:
            API_KEY = f.read().strip()
if not API_KEY:
    print("未找到 OPENROUTER_API_KEY，请先设置环境变量或缓存。")
    sys.exit(1)

AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# 纯提示词模式：避免真人/版权，纯动漫描述
PROMPT = (
    "Anime-style two warriors duel non-stop on a stone staircase winding through a dense bamboo grove at sunset. "
    "Warrior A: long flowing black hair, crimson samurai armor with gold trim, wields a glowing katana. "
    "Warrior B: silver hair in a topknot, dark blue ninja outfit, wields twin curved daggers. "
    "Continuous intense combat with dazzling, ever-changing techniques: blazing sword slashes trailing fire, "
    "rapid dagger flurries with afterimages, shockwave clashes, mid-air acrobatic dodges, energy bursts, "
    "sparks and debris flying, dynamic camera swirls and speed lines. No pauses, escalating spectacular moves, "
    "vibrant orange-and-violet sunset backlighting, dramatic lens flares."
)

payload = {
    "model": "bytedance/seedance-2.0",
    "prompt": PROMPT,
    "resolution": "4K",
    "aspect_ratio": "16:9",
    "duration": 15,
    "generate_audio": True,
}


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{GATEWAY}{path}", data=data, headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


# 1. 提交任务
print("[提交] bytedance/seedance-2.0 | 4K 16:9 15s 纯提示词")
code, job = req("POST", "/api/v1/videos", payload)
print(f"  HTTP {code}")
if code not in (200, 202):
    print(json.dumps(job, ensure_ascii=False)[:600])
    sys.exit(1)

job_id = job.get("id")
print(f"  job_id={job_id} status={job.get('status')}")
if not job_id:
    print("未拿到 job_id，原始返回:", json.dumps(job, ensure_ascii=False)[:600])
    sys.exit(1)

# 2. 轮询（固定 45 次 × 20s = 最多 15 分钟）
result = None
for i in range(45):
    time.sleep(20)
    code, r = req("GET", f"/api/v1/videos/{job_id}")
    status = r.get("status", "unknown") if isinstance(r, dict) else "unknown"
    print(f"  [{i+1:2d}/45] {status}")
    if status in ("completed", "failed", "cancelled", "expired"):
        result = r
        break

if not result:
    print("[超时] 15 分钟内未完成")
    sys.exit(1)

print("\n[完成] 最终结果:")
print(json.dumps(result, ensure_ascii=False)[:800])

if result.get("status") != "completed":
    print("任务未成功:", result.get("error", result.get("status")))
    sys.exit(1)

# 3. 下载视频
urls = result.get("unsigned_urls", [])
if not urls:
    print("无视频 URL")
    sys.exit(1)
url = urls[0].replace("https://openrouter.ai", GATEWAY)
out = os.path.join(os.path.dirname(__file__), "..", "output", "seedance_fight.mp4")
os.makedirs(os.path.dirname(out), exist_ok=True)
out = os.path.abspath(out)

dl = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
with urllib.request.urlopen(dl, timeout=300) as resp, open(out, "wb") as f:
    while True:
        chunk = resp.read(8192)
        if not chunk:
            break
        f.write(chunk)

size = os.path.getsize(out) / (1024 * 1024)
print(f"\n[下载] {out} ({size:.1f} MB)")
print(f"费用: ${result.get('usage', {}).get('cost')}")
