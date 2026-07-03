# Runloop/OpenRouter 视频 & 图片生成完整指南

> **给新对话的提示词**：请读取以下文档，然后我可以直接让你生成视频或图片。你不需要我有额外的上下文，按照文档中的步骤操作即可。

---

## 〇、Key 管理（自动创建 + 复用）

### 环境变量

环境中已预配置：

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `OPENROUTER_API_KEY` | 网关 API Key（`gws_` 前缀，通过 Runloop 网关认证） | `gws_2VYXpzn2...` |
| `OPENROUTER_BASE_URL` | 网关地址 | `https://gateway.runloop.ai` |

### 自动化 Key 检查与创建流程

每次新对话开始时，按以下步骤处理 Key：

**Step 1: 检查环境变量是否有可用 Key**

```bash
# 检查环境变量中是否已有可用的 key
if [ -n "$OPENROUTER_API_KEY" ]; then
  echo "已找到 OPENROUTER_API_KEY（前缀: ${OPENROUTER_API_KEY:0:10}...）"
else
  echo "OPENROUTER_API_KEY 未设置，需要创建"
fi
```

**Step 2: 验证 Key 是否有效（调一个轻量接口测试）**

```bash
# 用 /health 或 /api/v1/models 验证 key 是否可用
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
  "https://gateway.runloop.ai/health" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY")

if [ "$RESPONSE" = "200" ]; then
  echo "Key 验证成功 ✅"
else
  echo "Key 验证失败 ❌ (HTTP $RESPONSE)，需要重新获取"
fi
```

**Step 3: 如果 Key 不存在或无效，自动创建**

```bash
# 方式 A：如果环境中已有 Runloop 的 session token（如 gws_ 开头的自动注入）
# 直接用环境变量中的 token 作为 key 使用，无需额外创建

# 方式 B：通过 Runloop MCP 创建新 devbox/workspace key
export RUNLOOP_API_KEY="$OPENROUTER_API_KEY"
npx @runloop/rl-cli gateway-config list 2>/dev/null

# 方式 C：手动指引 — 如果以上都失败，告诉用户：
echo "请访问以下地址创建 API Key："
echo "  https://openrouter.ai/settings/keys"
echo "创建后将 key 设置为环境变量："
echo "  export OPENROUTER_API_KEY=sk-or-xxxxx"
echo ""
echo "或使用 Runloop 网关 Key（如有 workspace session）："
echo "  export OPENROUTER_API_KEY=gws_xxxxx"
```

**Step 4: 缓存到本地文件（复用）**

```bash
# 将有效的 key 缓存到本地文件，避免每次手动设置
KEY_CACHE_FILE="$HOME/.openrouter_cache"

save_key() {
  echo "$OPENROUTER_API_KEY" > "$KEY_CACHE_FILE"
  chmod 600 "$KEY_CACHE_FILE"
  echo "Key 已缓存到 $KEY_CACHE_FILE"
}

load_cached_key() {
  if [ -f "$KEY_CACHE_FILE" ]; then
    export OPENROUTER_API_KEY=$(cat "$KEY_CACHE_FILE")
    echo "已从缓存加载 Key ✅"
    return 0
  fi
  return 1
}

# 完整流程：环境变量 → 缓存文件 → 用户创建
setup_key() {
  # 1. 先尝试环境变量
  if [ -n "$OPENROUTER_API_KEY" ]; then
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
      "https://gateway.runloop.ai/health" \
      -H "Authorization: Bearer $OPENROUTER_API_KEY")
    if [ "$RESPONSE" = "200" ]; then
      echo "使用环境变量中的 Key ✅"
      return 0
    fi
  fi
  
  # 2. 尝试缓存
  if load_cached_key; then
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
      "https://gateway.runloop.ai/health" \
      -H "Authorization: Bearer $OPENROUTER_API_KEY")
    if [ "$RESPONSE" = "200" ]; then
      echo "使用缓存的 Key ✅"
      return 0
    fi
  fi
  
  # 3. 都没有 → 打印指引
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "未找到可用 Key，请按以下步骤创建："
  echo ""
  echo "1. 访问 https://openrouter.ai/settings/keys"
  echo "2. 点击 'Create Key'"
  echo "3. 复制生成的 key"
  echo "4. 在终端执行：export OPENROUTER_API_KEY=你的key"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  return 1
}
```

### Key 类型说明

| 前缀 | 类型 | 用途 |
|------|------|------|
| `gws_` | Runloop Gateway Workspace | 自动注入，通过网关代理所有 API |
| `sk-or-` | OpenRouter 标准 Key | 直接调用 openrouter.ai |
| Management Key | 管理 API Key | 仅用于 `/api/v1/keys` 管理接口，不能调生成 API |

**注意**：
- 通过网关（`gateway.runloop.ai`）调用时用 `gws_` 格式的 key
- 直接调 `openrouter.ai` 时用 `sk-or-` 格式
- Management Key 是单独的，不能混用

---

## 一、API 基础信息

```bash
GATEWAY="https://gateway.runloop.ai"
AUTH="Authorization: Bearer $OPENROUTER_API_KEY"
```

**关键规则**：
- 所有 API 必须带 `/api/v1` 前缀（不是 `/v1`！直接调 `/v1/...` 会返回 HTML 错误页）
- 认证头：`Authorization: Bearer $OPENROUTER_API_KEY`

---

## 二、视频生成（16 个模型）

### 2.1 查询可用模型

```bash
curl -s "$GATEWAY/api/v1/videos/models" -H "$AUTH" | python3 -m json.tool
```

### 2.2 模型清单

| # | Model ID | 厂商 | 分辨率 | 比例 | 时长(秒) | 首/尾帧 | 音频 | Seed | 参考价($/s或/token) |
|---|----------|------|--------|------|----------|---------|------|------|---------------------|
| 1 | `google/veo-3.1` | Google | 720p-4K | 16:9/9:16 | 4/6/8 | ✅/✅ | ✅ | ✅ | $0.20-0.60/s |
| 2 | `google/veo-3.1-fast` | Google | 720p-4K | 16:9/9:16 | 4/6/8 | ✅/✅ | ✅ | ✅ | $0.08-0.30/s |
| 3 | `google/veo-3.1-lite` | Google | 720p/1080p | 16:9/9:16 | 4/6/8 | ✅/✅ | ✅ | ✅ | $0.03-0.08/s |
| 4 | `openai/sora-2-pro` | OpenAI | 720p/1080p | 16:9/9:16 | 4-20 | ❌/❌ | ✅ | ❌ | $0.30-0.50/s |
| 5 | `bytedance/seedance-2.0` | ByteDance | 480p-4K | 7种 | 4-15 | ✅/✅ | ✅ | ✅ | $0.007/token |
| 6 | `bytedance/seedance-2.0-fast` | ByteDance | 480p/720p | 7种 | 4-15 | ✅/✅ | ✅ | ✅ | $0.0056/token |
| 7 | `bytedance/seedance-1-5-pro` | ByteDance | 480p-1080p | 7种 | 4-12 | ✅/✅ | ✅ | ✅ | $0.0024/token |
| 8 | `kwaivgi/kling-v3.0-pro` | 快手 Kling | 720p | 16:9/9:16/1:1 | 3-15 | ✅/✅ | ✅ | ❌ | $0.112-0.168/s |
| 9 | `kwaivgi/kling-v3.0-std` | 快手 Kling | 720p | 16:9/9:16/1:1 | 3-15 | ✅/✅ | ✅ | ❌ | $0.084-0.126/s |
| 10 | `kwaivgi/kling-video-o1` | 快手 Kling | 720p | 16:9/9:16/1:1 | 5/10 | ✅/✅ | ✅ | ❌ | $0.112/s |
| 11 | `alibaba/happyhorse-1.1` | 阿里 | 720p/1080p | 7种 | 3-15 | ✅/❌ | ❌ | ✅ | $0.099-0.128/s |
| 12 | `alibaba/happyhorse-1.0` | 阿里 | 720p/1080p | 7种 | 3-15 | ✅/❌ | ❌ | ✅ | $0.099-0.169/s |
| 13 | `alibaba/wan-2.7` | 阿里万相 | 720p/1080p | 5种 | 2-10 | ✅/✅ | ✅ | ✅ | $0.10/s |
| 14 | `alibaba/wan-2.6` | 阿里万相 | 720p/1080p | 16:9/9:16 | 5/10 | ✅/❌ | ✅ | ✅ | $0.04-0.15/s |
| 15 | `minimax/hailuo-2.3` | 海螺 | 1080p | 16:9 | 6/10 | ✅/❌ | ❌ | ❌ | $0.082/s |
| 16 | `x-ai/grok-imagine-video` | xAI Grok | 480p/720p | 7种 | 1-15 | ✅/❌ | ❌ | ❌ | $0.05-0.07/s |

**比例完整列表**：`16:9` / `9:16` / `1:1` / `4:3` / `3:4` / `3:2` / `2:3` / `21:9` / `9:21`

### 2.3 提交视频生成（异步任务）

```bash
curl -s -X POST "$GATEWAY/api/v1/videos" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bytedance/seedance-2.0",
    "prompt": "Two anime warriors fighting with swords on a mountain cliff at sunset, dramatic action",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 15,
    "generate_audio": true
  }'
```

**返回**：
```json
{
  "id": "9mYwB7O4mw0kmIibglTO",
  "polling_url": "https://openrouter.ai/api/v1/videos/9mYwB7O4mw0kmIibglTO",
  "status": "pending"
}
```

### 2.4 完整请求体

```
Seedance 2.0 支持三种图片引导模式：
  - 首尾帧模式（frame_images）：用图片锚定视频第一帧和最后一帧，控制画面走向
  - 全能模式（input_references + frame_images 同时使用）：首尾帧锚定画面 + 参考图/音频/视频引导风格和内容
  - 纯提示词模式（不加任何图片）：完全依赖 prompt 描述，人物用文字写清楚

️ 占位符说明：
  OpenRouter API 层没有 @占位符 机制（不支持 prompt 中写 @image_1 / @placeholder 引用图片）
  所有参考内容统一通过 input_references / frame_images 结构化 JSON 字段传输
  allowed_passthrough_parameters 仅 watermark 和 req_key，无 placeholder 相关参数

Seedance 2.0 特殊能力：
  - input_references 支持三种类型：image_url（引导风格/内容）、audio_url（引导节奏）、video_url（引导动作）
  - audio_url / video_url 仅 Seedance 2.0（byteplus 后端）支持，其他模型只接受 image_url

### 图片上传（无上传 API 的解决方案）

OpenRouter/Runloop 网关没有图片上传接口（POST /api/v1/images 是生成图片，POST /api/v1/videos 是生成视频，都不支持上传）。

**方案 A：有公网 URL 直接用**

```json
{
  "type": "image_url",
  "image_url": {"url": "https://example.com/photo.jpg"}
}
```

**方案 B：没有 URL 就用 base64 data URI**

直接把本地图片转成 base64 data URI 放在 url 字段里，API 会解析这种格式：

```python
import base64, os

def img_to_data_uri(path):
    """本地图片 -> base64 data URI"""
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

img1 = img_to_data_uri("./photo1.jpg")  # "data:image/jpeg;base64,/9j/4AAQ..."

# 在请求体中使用
frame_images = [
    {"type": "image_url", "image_url": {"url": img1}, "frame_type": "first_frame"}
]
```

**方案 C：封装自动判断函数（推荐）**

```python
def resolve_image(source):
    """有 URL 就用 URL，没有就读本地转 base64，两种都失败报错"""
    if not source:
        return None
    if source.startswith("http://") or source.startswith("https://"):
        return source
    try:
        return img_to_data_uri(source)
    except Exception:
        raise ValueError(f"图片既不是公网 URL 也不是有效本地路径: {source}")
```

### 2.4.2 [image_n] 占位符引用

Seedance 2.0 全能模式支持在 **prompt 中用 `[image_n]` 占位符引用 `input_references` 里的图片**，帮助模型理解哪张图片对应哪些描述：

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "[image_1] (粉色水手服女生) 主动发起攻击，[image_2] (黑卫衣格裙女生) 侧身躲闪并反击。两人在竹林石阶上持续激烈打斗...",
  "input_references": [
    {"type": "image_url", "image_url": {"url": "图1的 URL 或 data URI"}},
    {"type": "image_url", "image_url": {"url": "图2的 URL 或 data URI"}}
  ]
}
```

**占位符规则**：
- 格式：`[image_1]`、`[image_2]`、`[image_3]`……（方括号 + image_ 序号，序号从 1 开始）
- `[image_n]` 对应 `input_references` 数组中第 n 张图片（下标 n-1）
- prompt 中可以多次引用同一个占位符，模型会在不同镜头里重复应用

**对比：有/无占位符的 prompt 效果**

```python
# 无占位符：模型需要猜哪句描述对应哪张图
prompt_a = "两个女生打斗，第一个穿粉色水手服，第二个穿黑卫衣格裙，持续战斗"

# 有占位符：模型清楚每句话指哪个人物
prompt_b = "[image_1] 持剑跃起，[image_2] 举盾格挡。两人在竹林石阶上持续激烈打斗"
```

️ **注意**：
- OpenRouter API 层的占位符就是 `[image_n]`，不是 `@image_n` / `@placeholder` 等
- 图片含真人仍会被 ByteDance 审核拒绝（`SensitiveContentDetected`），这是图片内容问题，与占位符格式无关
- `input_references` 中的 audio_url / video_url 不能用 `[image_n]` 引用，它们只能作为整体风格/节奏参考

### 2.4.3 真人被拒时的替代方案

**模式 1：首尾帧模式**

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "两女持剑激烈打斗...",
  "resolution": "4K",
  "duration": 15,
  "frame_images": [
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}, "frame_type": "first_frame"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}, "frame_type": "last_frame"}
  ]
}
```

**模式 2：全能模式**

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "两女打斗，参考图中女生的特征...",
  "resolution": "4K",
  "duration": 15,
  "frame_images": [
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}, "frame_type": "first_frame"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}, "frame_type": "last_frame"}
  ],
  "input_references": [
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
    {"type": "audio_url", "audio_url": {"url": "https://example.com/music.mp3"}}
  ]
}
```

**模式 3：纯提示词模式（真人被拒时使用）**

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "Two women fighting with swords on stone stairs... "
          "First woman: long black hair, pink sailor school uniform, navy pleated skirt, white knee socks, black loafers... "
          "Second woman: long black hair with bangs, oversized black fur hoodie, blue plaid miniskirt, black tights, Mary Jane shoes...",
  "resolution": "4K",
  "duration": 15,
  "generate_audio": true
}
```

**注意**：
- `frame_images` / `input_references` 需要公网 URL 或 base64 data URI
- Seedance 2.0 有真人检测：图片/视频如果包含真人照片会被 ByteDance 审核拒绝，返回 `InputImageSensitiveContentDetected.PrivacyInformation`，AI 生成的人物、卡通、动漫可以正常使用。遇到真人报错时，改用纯提示词模式，用文字详细描述人物特征
- prompt 不能包含知名 IP 名称（会触发版权审核失败）

### 2.5 轮询任务状态

```bash
# 每 15-20 秒查询一次，最长等 10 分钟
JOB_ID="9mYwB7O4mw0kmIibglTO"

curl -s "$GATEWAY/api/v1/videos/$JOB_ID" -H "$AUTH"
```

**状态流转**：`pending` → `in_progress` → `completed` | `failed` | `cancelled` | `expired`

**完成返回**：
```json
{
  "id": "...",
  "generation_id": "gen-vid-...",
  "status": "completed",
  "unsigned_urls": ["https://openrouter.ai/api/v1/videos/JOB_ID/content?index=0"],
  "usage": {"cost": 2.268, "is_byok": false}
}
```

### 2.6 下载视频

```bash
# 通过网关下载（替换域名为 gateway.runloop.ai）
curl -s -L "$GATEWAY/api/v1/videos/$JOB_ID/content?index=0" \
  -H "$AUTH" -o output.mp4
```

### 2.7 完整 Python 调用模板（三种模式）

```python
import requests, time, base64, os

GATEWAY = os.environ.get("OPENROUTER_BASE_URL", "https://gateway.runloop.ai")
AUTH = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"}

# ─── 图片处理：有 URL 就用 URL，没有就读本地转 base64 ───

def img_to_data_uri(path):
    """本地图片 -> base64 data URI"""
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

def resolve_image(source):
    """有 URL 就用 URL，没有就读本地转 base64，两种都失败报错"""
    if not source:
        return None
    if source.startswith("http://") or source.startswith("https://"):
        return source
    try:
        return img_to_data_uri(source)
    except Exception:
        raise ValueError(f"既不是公网 URL 也不是有效本地路径: {source}")


# ─── 核心函数 ───

def generate_video(model, prompt, resolution="4K", aspect_ratio="16:9",
                   duration=15, generate_audio=True,
                   frame_images=None, input_references=None, **kwargs):
    """提交视频生成任务并等待完成，支持三种模式"""

    payload = {
        "model": model, "prompt": prompt,
        "resolution": resolution, "aspect_ratio": aspect_ratio,
        "duration": duration, "generate_audio": generate_audio, **kwargs
    }
    if frame_images:
        payload["frame_images"] = frame_images
    if input_references:
        payload["input_references"] = input_references

    resp = requests.post(f"{GATEWAY}/api/v1/videos", headers=AUTH, json=payload)
    if resp.status_code == 400:
        data = resp.json().get("error", {})
        msg = data.get("message", "")
        if "SensitiveContent" in msg or "PrivacyInformation" in msg:
            print("[拒绝] 图片含真人被 ByteDance 审核拒绝")
            print("[解决] 删掉 frame_images / input_references，改用纯提示词模式")
            print("       人物特征用文字写清楚即可")
            return None
        raise RuntimeError(f"400: {resp.json()}")
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"提交失败 HTTP {resp.status_code}: {resp.text[:300]}")

    job = resp.json()
    job_id = job["id"]
    print(f"[提交] job_id={job_id}")

    # 轮询（最多 15 分钟）
    for i in range(45):
        time.sleep(20)
        r = requests.get(f"{GATEWAY}/api/v1/videos/{job_id}", headers=AUTH).json()
        status = r.get("status", "unknown")
        print(f"  [{i+1:2d}/{45}] {status}")
        if status in ("completed", "failed", "cancelled", "expired"):
            return r

    return {"status": "timeout", "id": job_id}

def download_video_to_local(result, output_path):
    """从完成结果中下载视频文件"""
    urls = result.get("unsigned_urls", [])
    if not urls:
        print(f"无视频 URL, error: {result.get('error', 'N/A')}")
        return False
    url = urls[0].replace("https://openrouter.ai", GATEWAY)
    resp = requests.get(url, headers=AUTH, stream=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    size = os.path.getsize(output_path) / (1024*1024)
    print(f"[下载] {output_path} ({size:.1f} MB)")
    return True


# ─── 三种模式使用示例 ───

MODE = "pure_prompt"   # 改为 "frame_only" 或 "full_mode" 切换

if MODE == "frame_only":
    # 模式 1：首尾帧
    result = generate_video(
        model="bytedance/seedance-2.0",
        prompt="两女持剑激烈打斗于竹林石阶上...",
        resolution="4K", duration=15,
        frame_images=[
            {"type": "image_url", "image_url": {"url": resolve_image("./girl1.jpg")}, "frame_type": "first_frame"},
            {"type": "image_url", "image_url": {"url": resolve_image("./girl2.jpg")}, "frame_type": "last_frame"}
        ]
    )

elif MODE == "full_mode":
    # 模式 2：全能模式（首尾帧 + 参考图）
    img1 = resolve_image("./girl1.jpg")
    img2 = resolve_image("./girl2.jpg")
    result = generate_video(
        model="bytedance/seedance-2.0",
        prompt="两女打斗，保持参考图中的人物特征...",
        resolution="4K", duration=15,
        frame_images=[
            {"type": "image_url", "image_url": {"url": img1}, "frame_type": "first_frame"},
            {"type": "image_url", "image_url": {"url": img2}, "frame_type": "last_frame"}
        ],
        input_references=[
            {"type": "image_url", "image_url": {"url": img1}},
            {"type": "image_url", "image_url": {"url": img2}}
        ]
    )

else:
    # 模式 3：纯提示词（真人被拒时使用）
    result = generate_video(
        model="bytedance/seedance-2.0",
        prompt="Two women fighting with swords on stone stairs surrounded by bamboo... "
               "First woman: long black hair, pink sailor school uniform, navy pleated skirt, white knee socks, black loafers... "
               "Second woman: long black hair with bangs, oversized black fur hoodie, blue plaid miniskirt, black tights, Mary Jane shoes... "
               "Non-stop dynamic combat, speed lines, blade sparks, hair flowing, no breaks.",
        resolution="4K", duration=15, generate_audio=True
    )

if result and result.get("status") == "completed":
    download_video_to_local(result, "output.mp4")
    print(f"费用: ${result['usage']['cost']}")
elif result and result.get("status") in ("failed", "cancelled"):
    print(f"失败: {result.get('error', result.get('status', 'unknown'))}")
```

**三种模式对比**：

| 模式 | 字段 | 用途 | 适用场景 |
|------|------|------|---------|
| **首尾帧** | `frame_images` | 锚定首尾画面内容 | "第一帧是她 A，最后一帧是她 B" |
| **全能模式** | `frame_images` + `input_references` | 锚定画面 + 多模态参考引导 | 服装/风格/动作/节奏都要参考 |
| **纯提示词** | 不加图片字段 | 完全文字描述 | 人物照片被真人审核拒绝时 |

---

## 三、图片生成（8 个模型）

### 3.1 查询可用模型

```bash
curl -s "$GATEWAY/api/v1/models" -H "$AUTH" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('data', []):
    arch = m.get('architecture', {})
    if 'image' in arch.get('output_modalities', []):
        print(f\"{m['id']:<45} {m.get('name',''):<45} ctx={m.get('context_length','')}\")
"
```

### 3.2 模型清单

| # | Model ID | 名称 | 输入 | 上下文 | 特点 |
|---|----------|------|------|--------|------|
| 1 | `google/gemini-2.5-flash-image` | Nano Banana | text,image | 32K | 最快最便宜 |
| 2 | `google/gemini-3.1-flash-image` | Nano Banana 2 | text,image | 131K | 新一代 Flash |
| 3 | `google/gemini-3.1-flash-image-preview` | Flash Preview | text,image | 131K | 预览版 |
| 4 | `google/gemini-3-pro-image` | Nano Banana Pro | text,image | 65K | 高质量 |
| 5 | `google/gemini-3-pro-image-preview` | Pro Preview | text,image | 65K | 预览版 |
| 6 | `openai/gpt-5-image` | GPT-5 Image | text,image,file | 400K | 最强，支持文件 |
| 7 | `openai/gpt-5-image-mini` | GPT-5 Image Mini | text,image,file | 400K | 快速版 |
| 8 | `openai/gpt-5.4-image-2` | GPT-5.4 Image 2 | text,image,file | 272K | 最新 |

### 3.3 通过 Chat Completions 调用

图片模型通过标准 Chat 接口调用，图片以 base64 或 URL 返回：

```bash
curl -s -X POST "$GATEWAY/api/v1/chat/completions" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash-image",
    "messages": [
      {"role": "user", "content": "Generate an image of a cute anime cat girl"}
    ]
  }'
```

**说明**：
- 结果在 `choices[0].message.content` 中，包含 base64 图片数据或 URL
- `gemini-*-image`：快速、成本低，适合日常生成
- `gpt-5-image`：质量最高，支持文件作为输入参考

---

## 四、音频生成（2 个模型，通过 Chat Completions）

| Model ID | 说明 | 价格 |
|----------|------|------|
| `google/lyria-3-pro-preview` | 完整歌曲 | $0.08/首 |
| `google/lyria-3-clip-preview` | 30秒片段 | $0.04/段 |

---

## 五、通用注意事项

### 必须遵守
1. **API 路径**：所有调用必须用 `$GATEWAY/api/v1/...`（不能省略 `/api`）
2. **认证**：`Authorization: Bearer $OPENROUTER_API_KEY`
3. **视频是异步**：POST 提交 → GET 轮询 → GET 下载，轮询间隔 15-20 秒

### 费用
- 视频：15 秒 720p 约 $1-3，4K 更贵
- 图片：按 token 计费，通常极便宜
- 音频：按首/段计费

### 安全
- **版权问题**：prompt 不能含知名 IP 名称（如 Dragon Ball Z、Naruto、Marvel 等），否则触发审核失败
- **通用描述**：用 "anime style warriors" 代替 "like Naruto"
- **费用控制**：每次调用后检查 `usage.cost`

### 快速排错

| 错误 | 原因 | 解决 |
|------|------|------|
| `missing_envelope` | 用了 `/v1/...` 而非 `/api/v1/...` | 加 `/api` 前缀 |
| `401 Missing Authentication` | Key 无效或过期 | 检查 `setup_key` 流程 |
| `404 Not Found` | 端点错误 | 确认路径拼写 |
| `403 Error 1010` | Cloudflare 拦截 | 检查 User-Agent / 请求格式 |
| `400 InputImageSensitiveContentDetected` | 图像/视频中含真人（ByteDance 审核） | 改用纯提示词模式，文字描述人物特征 |
| `400 PrivacyInformation` | 同上（真人识别） | 同上 |
| 视频 `failed` + copyright | Prompt 含版权内容 | 用通用描述重新写 prompt |
