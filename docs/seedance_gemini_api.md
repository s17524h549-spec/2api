# Seedance 2.0 视频 & Gemini 生图 API 接入文档

> 精简接入指南，只覆盖两个已验证成熟的模型链路：
> - **视频生成**：`bytedance/seedance-2.0`（异步任务：提交 → 轮询 → 下载）
> - **图片生成**：`google/gemini-*-image` 系列（同步 Chat Completions，一次请求直接返回图片）
>
> 完整模型清单与更多细节见 [openrouter_api_guide.md](./openrouter_api_guide.md)。

---

## 一、接入基础

### 1.1 请求地址

```
Base URL:  https://gateway.runloop.ai
```

所有接口必须带 **`/api/v1` 前缀**（不是 `/v1`！用 `/v1/...` 会返回 HTML 错误页 / `missing_envelope`）：

| 用途 | 方法 | 路径 |
|------|------|------|
| 提交视频生成任务 | POST | `/api/v1/videos` |
| 查询视频任务状态 | GET | `/api/v1/videos/{job_id}` |
| 下载视频 | GET | `/api/v1/videos/{job_id}/content?index=0` |
| 图片生成（Chat） | POST | `/api/v1/chat/completions` |
| 健康检查（验 key） | GET | `/health` |

也可通过环境变量覆盖：`OPENROUTER_BASE_URL`（默认即上述网关地址）。

### 1.2 API Key

**认证头**（所有请求都要带）：

```
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json
```

**Key 类型**：

| 前缀 | 类型 | 用途 |
|------|------|------|
| `gws_` | Runloop Gateway Workspace Key | 走网关 `gateway.runloop.ai`（本文档默认） |
| `sk-or-` | OpenRouter 标准 Key | 直连 `openrouter.ai` 时使用 |

**获取与加载顺序**（脚本约定）：

1. 环境变量 `OPENROUTER_API_KEY`（Runloop 环境已预注入 `gws_` key）
2. 本地缓存文件 `~/.openrouter_cache`（纯文本一行 key，`chmod 600`）
3. 都没有 → 到 https://openrouter.ai/settings/keys 创建后 `export OPENROUTER_API_KEY=xxx`

**验证 key 是否可用**：

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "https://gateway.runloop.ai/health" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
# 200 = 可用
```

---

## 二、Seedance 2.0 视频生成

### 2.1 模型与能力

| Model ID | 分辨率 | 比例 | 时长 | 首/尾帧 | 音频 | 计价 |
|----------|--------|------|------|---------|------|------|
| `bytedance/seedance-2.0` | 480p / 720p / 1080p / 2K / 4K | 9 种（16:9、9:16、1:1、4:3、3:4、3:2、2:3、21:9、9:21） | 4-15 秒 | ✅ | ✅ | $0.007/token（15s 720p 约 $1-3，4K 更贵） |

### 2.2 请求参数

`POST /api/v1/videos`，请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | `bytedance/seedance-2.0` |
| `prompt` | string | ✅ | 视频描述；全能模式下支持 `[image_n]` 占位符 |
| `resolution` | string | 否 | `480p`/`720p`/`1080p`/`2K`/`4K` |
| `aspect_ratio` | string | 否 | 如 `16:9` |
| `duration` | int | 否 | 4-15（秒） |
| `generate_audio` | bool | 否 | 是否生成音频 |
| `seed` | int | 否 | 随机种子 |
| `frame_images` | array | 否 | 首尾帧锚定（见模式 1/2） |
| `input_references` | array | 否 | 多模态参考（见模式 2） |

### 2.3 三种模式

#### 模式 1：首尾帧模式（`frame_images`）

用图片锚定视频第一帧和最后一帧，prompt 描述中间的运动过程：

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "首帧角色向前冲刺，激烈交锋后定格为尾帧姿态",
  "resolution": "720p",
  "duration": 15,
  "frame_images": [
    {"type": "image_url", "image_url": {"url": "<URL 或 data URI>"}, "frame_type": "first_frame"},
    {"type": "image_url", "image_url": {"url": "<URL 或 data URI>"}, "frame_type": "last_frame"}
  ]
}
```

`frame_type` 取值 `first_frame` / `last_frame`，可只给其中一个。

#### 模式 2：全能模式（`frame_images` + `input_references`）

首尾帧锚定画面，同时用参考图/音频/视频引导风格、内容、节奏与动作：

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "[image_1] 主动进攻，[image_2] 侧身躲闪并反击，两人持续激烈打斗",
  "resolution": "720p",
  "duration": 15,
  "frame_images": [
    {"type": "image_url", "image_url": {"url": "..."}, "frame_type": "first_frame"}
  ],
  "input_references": [
    {"type": "image_url", "image_url": {"url": "图1"}},
    {"type": "image_url", "image_url": {"url": "图2"}},
    {"type": "audio_url", "audio_url": {"url": "https://example.com/music.mp3"}}
  ]
}
```

- `input_references` 三种类型：`image_url`（风格/内容）、`audio_url`（节奏）、`video_url`（动作）；audio/video 仅 Seedance 2.0 支持
- **`[image_n]` 占位符**：prompt 中 `[image_1]`、`[image_2]`…… 对应 `input_references` 里第 n 张图（序号从 1 开始，可重复引用）；格式就是方括号，**不是** `@image_n`；audio/video 参考不能用占位符引用

#### 模式 3：纯提示词模式（无图片字段）

完全靠文字描述，人物特征写清楚。图片被真人审核拒绝时的兜底方案：

```json
{
  "model": "bytedance/seedance-2.0",
  "prompt": "Two anime warriors duel on stone stairs... First: long black hair, crimson armor... Second: silver hair, dark blue outfit...",
  "resolution": "720p",
  "duration": 15,
  "generate_audio": true
}
```

### 2.4 图片/素材传入方式

没有上传接口，素材统一放在 `url` 字段里，两种形式：

1. **公网 URL**：`https://example.com/photo.jpg`
2. **base64 data URI**（本地文件）：`data:image/jpeg;base64,/9j/4AAQ...`

```python
import base64

def resolve_media(source, mime="image/jpeg"):
    if source.startswith(("http://", "https://")):
        return source
    with open(source, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
```

### 2.5 完整调用流程（提交 → 轮询 → 下载）

**① 提交**：

```bash
curl -s -X POST "https://gateway.runloop.ai/api/v1/videos" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "bytedance/seedance-2.0", "prompt": "...", "resolution": "720p", "duration": 15}'
```

返回：

```json
{"id": "9mYwB7O4mw0kmIibglTO", "status": "pending"}
```

**② 轮询**（每 15-20 秒一次，建议最多等 15 分钟）：

```bash
curl -s "https://gateway.runloop.ai/api/v1/videos/$JOB_ID" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
```

状态流转：`pending` → `in_progress` → `completed` | `failed` | `cancelled` | `expired`

完成时返回：

```json
{
  "id": "...",
  "status": "completed",
  "unsigned_urls": ["https://openrouter.ai/api/v1/videos/JOB_ID/content?index=0"],
  "usage": {"cost": 2.268}
}
```

**③ 下载**（把 `unsigned_urls` 里的 `openrouter.ai` 域名替换为网关域名，带认证头）：

```bash
curl -s -L "https://gateway.runloop.ai/api/v1/videos/$JOB_ID/content?index=0" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -o output.mp4
```

### 2.6 现成脚本

| 模式 | 脚本 |
|------|------|
| 模式 1 首尾帧 | `scripts/seedance_frames2video.py` |
| 模式 2 全能 | `scripts/seedance_full2video.py` |
| 模式 3 纯提示词 | `scripts/seedance_text2video.py` |

### 2.7 内容审核限制

- **真人检测**：素材含真人照片会被 ByteDance 拒绝，返回 `400 InputImageSensitiveContentDetected.PrivacyInformation`；AI 生成人物/卡通/动漫可正常使用。被拒时改用模式 3，人物特征用文字描述
- **版权审核**：prompt 不能含知名 IP 名称（如 Naruto、Marvel），用通用描述（"anime style warriors"）代替

---

## 三、Gemini 生图

### 3.1 模型清单

| Model ID | 名称 | 输入 | 上下文 | 定位 |
|----------|------|------|--------|------|
| `google/gemini-2.5-flash-image` | Nano Banana | text, image | 32K | 最快最便宜，日常首选 |
| `google/gemini-3.1-flash-image` | Nano Banana 2 | text, image | 131K | 新一代 Flash |
| `google/gemini-3.1-flash-image-preview` | Flash Preview | text, image | 131K | 预览版 |
| `google/gemini-3-pro-image` | Nano Banana Pro | text, image | 65K | 高质量 |
| `google/gemini-3-pro-image-preview` | Pro Preview | text, image | 65K | 预览版 |

### 3.2 调用方式（同步，Chat Completions）

图片模型走标准 Chat 接口，**一次请求直接返回图片**，无需轮询。

**文生图**（`content` 为字符串）：

```bash
curl -s -X POST "https://gateway.runloop.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash-image",
    "messages": [{"role": "user", "content": "Generate an image of a cute anime cat girl"}]
  }'
```

**图生图 / 图片编辑**（`content` 为数组，text + image_url）：

```json
{
  "model": "google/gemini-2.5-flash-image",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "把背景换成蓝色星空"},
      {"type": "image_url", "image_url": {"url": "<公网 URL 或 data:image/png;base64,...>"}}
    ]
  }]
}
```

### 3.3 解析返回的图片

图片在 `choices[0].message.images[]` 中，以 base64 data URI 返回：

```python
import json, base64

resp = ...  # chat/completions 的 JSON 响应
imgs = resp["choices"][0]["message"].get("images", [])
for i, im in enumerate(imgs):
    b64 = im["image_url"]["url"].split(",", 1)[1]   # 去掉 "data:image/png;base64," 前缀
    with open(f"output_{i}.png", "wb") as f:
        f.write(base64.b64decode(b64))
print("cost:", resp.get("usage", {}).get("cost"))
```

**注意**：

- 若 `message.images` 为空，检查 `message.content` 中的文字（通常是拒绝原因或说明）
- 图片响应体较大（base64 后数 MB），用 `urllib` 处理大 chunked 响应不稳定，建议 curl 子进程落盘再解析（参考 `scripts/gpt_image2_gen.py` 的做法）
- 按 token 计费，单张图通常远低于 $0.1

---

## 四、错误速查

| 错误 | 原因 | 解决 |
|------|------|------|
| `missing_envelope` / HTML 错误页 | 路径用了 `/v1/...` | 改为 `/api/v1/...` |
| `401 Missing Authentication` | key 无效或过期 | 重新验证/获取 key（§1.2） |
| `404 Not Found` | 端点拼写错误 | 核对 §1.1 路径表 |
| `403 Error 1010` | Cloudflare 拦截 | 检查 User-Agent / 请求格式 |
| `400 InputImageSensitiveContentDetected` / `PrivacyInformation` | 素材含真人 | 改用纯提示词模式 |
| 视频 `failed` + copyright | prompt 含版权 IP | 换通用描述重写 prompt |
| 视频超 15 分钟未完成 | 上游拥堵 | 记下 job_id 稍后再查，或重新提交 |

## 五、费用提示

- **视频**：15 秒 720p 约 $1-3，4K 显著更贵；调试期建议 720p + 短时长
- **图片**：按 token 计费，极便宜
- 每次调用后检查响应里的 `usage.cost`
