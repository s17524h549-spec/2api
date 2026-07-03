#!/usr/bin/env python3
"""
Seedance 2.0 首尾帧模式示例（模式1：frame_images）。

对应 docs/openrouter_api_guide.md §2.4.3 模式1、§2.7 frame_only。
用图片锚定视频的第一帧和最后一帧，控制画面走向；prompt 描述中间的运动过程。

注意：
  - --first / --last 支持公网 URL 或本地路径（本地图片自动转 base64 data URI）
  - 至少提供 --first / --last 之一；只给首帧则尾帧由模型自由发挥
  - 图片含真人会被 ByteDance 审核拒绝（InputImageSensitiveContentDetected），
    AI 生成人物/卡通/动漫可正常使用；被拒时改用纯提示词模式（seedance_text2video.py）

用法：
    export OPENROUTER_API_KEY=gws_xxx   # 或提前缓存到 ~/.openrouter_cache
    python scripts/seedance_frames2video.py \
        --prompt "首帧角色向前冲刺，激烈交锋后定格为尾帧姿态，动作连贯不间断" \
        --first ./first.jpg --last ./last.jpg \
        --out output/seedance_frames.mp4
"""
import os, sys, time, json, base64, argparse
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

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def resolve_media(source):
    """有公网 URL 直接用，本地文件转 base64 data URI（doc §2.4 方案C）"""
    if source.startswith("http://") or source.startswith("https://"):
        return source
    if not os.path.exists(source):
        raise ValueError(f"既不是公网 URL 也不是有效本地路径: {source}")
    mime = MIME.get(os.path.splitext(source)[1].lower(), "image/jpeg")
    with open(source, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{GATEWAY}{path}", data=data, headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def submit_and_wait(payload):
    """提交任务并轮询到终态（固定 45 次 × 20s = 最多 15 分钟）"""
    code, job = req("POST", "/api/v1/videos", payload)
    print(f"  HTTP {code}")
    if code == 400:
        msg = json.dumps(job.get("error", job), ensure_ascii=False)
        if "SensitiveContent" in msg or "PrivacyInformation" in msg:
            print("[拒绝] 图片含真人被 ByteDance 审核拒绝")
            print("[解决] 改用纯提示词模式（scripts/seedance_text2video.py），人物特征用文字写清楚")
            sys.exit(1)
        print(msg[:600])
        sys.exit(1)
    if code not in (200, 202):
        print(json.dumps(job, ensure_ascii=False)[:600])
        sys.exit(1)

    job_id = job.get("id")
    print(f"  job_id={job_id} status={job.get('status')}")
    if not job_id:
        print("未拿到 job_id，原始返回:", json.dumps(job, ensure_ascii=False)[:600])
        sys.exit(1)

    for i in range(45):
        time.sleep(20)
        code, r = req("GET", f"/api/v1/videos/{job_id}")
        status = r.get("status", "unknown") if isinstance(r, dict) else "unknown"
        print(f"  [{i+1:2d}/45] {status}")
        if status in ("completed", "failed", "cancelled", "expired"):
            return r

    print("[超时] 15 分钟内未完成")
    sys.exit(1)


def download_video(result, out):
    urls = result.get("unsigned_urls", [])
    if not urls:
        print("无视频 URL")
        sys.exit(1)
    url = urls[0].replace("https://openrouter.ai", GATEWAY)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
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


def main():
    ap = argparse.ArgumentParser(description="Seedance 2.0 首尾帧模式（frame_images）")
    ap.add_argument("--prompt", required=True, help="描述首尾帧之间的运动过程")
    ap.add_argument("--first", help="首帧图片：本地路径或公网 URL")
    ap.add_argument("--last", help="尾帧图片：本地路径或公网 URL")
    ap.add_argument("--resolution", default="720p", help="480p/720p/1080p/2K/4K，默认 720p")
    ap.add_argument("--aspect-ratio", default="16:9", help="默认 16:9")
    ap.add_argument("--duration", type=int, default=15, help="4-15 秒，默认 15")
    ap.add_argument("--no-audio", action="store_true", help="不生成音频")
    ap.add_argument("--out", default="output/seedance_frames.mp4", help="输出路径")
    args = ap.parse_args()

    if not args.first and not args.last:
        print("首尾帧模式至少需要 --first / --last 之一")
        sys.exit(1)

    frame_images = []
    if args.first:
        frame_images.append({"type": "image_url",
                             "image_url": {"url": resolve_media(args.first)},
                             "frame_type": "first_frame"})
    if args.last:
        frame_images.append({"type": "image_url",
                             "image_url": {"url": resolve_media(args.last)},
                             "frame_type": "last_frame"})

    payload = {
        "model": "bytedance/seedance-2.0",
        "prompt": args.prompt,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "duration": args.duration,
        "generate_audio": not args.no_audio,
        "frame_images": frame_images,
    }

    print(f"[提交] bytedance/seedance-2.0 | {args.resolution} {args.aspect_ratio} "
          f"{args.duration}s 首尾帧模式（{len(frame_images)} 张锚定帧）")
    result = submit_and_wait(payload)

    print("\n[完成] 最终结果:")
    print(json.dumps(result, ensure_ascii=False)[:800])
    if result.get("status") != "completed":
        print("任务未成功:", result.get("error", result.get("status")))
        sys.exit(1)

    download_video(result, args.out)


if __name__ == "__main__":
    main()
