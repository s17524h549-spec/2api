#!/usr/bin/env python3
"""
Seedance 2.0 全能模式示例（模式2：frame_images + input_references）。

对应 docs/openrouter_api_guide.md §2.4.3 模式2、§2.7 full_mode。
首尾帧锚定画面走向，同时用参考图/音频/视频引导风格、内容、节奏与动作。

注意：
  - input_references 支持三种类型：image_url（引导风格/内容）、audio_url（引导节奏）、
    video_url（引导动作）；audio/video 仅 Seedance 2.0（byteplus 后端）支持
  - prompt 中可用 [image_1]、[image_2]…… 占位符引用 --ref 传入的第 n 张参考图
    （doc §2.4.2；audio/video 参考不能用占位符引用）
  - 所有素材支持公网 URL 或本地路径（本地文件自动转 base64 data URI）
  - 素材含真人会被 ByteDance 审核拒绝（InputImageSensitiveContentDetected），
    AI 生成人物/卡通/动漫可正常使用；被拒时改用纯提示词模式（seedance_text2video.py）

用法：
    export OPENROUTER_API_KEY=gws_xxx   # 或提前缓存到 ~/.openrouter_cache
    python scripts/seedance_full2video.py \
        --prompt "[image_1] 主动进攻，[image_2] 侧身躲闪并反击，两人持续激烈打斗" \
        --first ./first.jpg --last ./last.jpg \
        --ref ./girl1.jpg --ref ./girl2.jpg \
        --audio https://example.com/music.mp3 \
        --out output/seedance_full.mp4
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

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
}


def resolve_media(source):
    """有公网 URL 直接用，本地文件转 base64 data URI（doc §2.4 方案C）"""
    if source.startswith("http://") or source.startswith("https://"):
        return source
    if not os.path.exists(source):
        raise ValueError(f"既不是公网 URL 也不是有效本地路径: {source}")
    mime = MIME.get(os.path.splitext(source)[1].lower(), "application/octet-stream")
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
            print("[拒绝] 素材含真人被 ByteDance 审核拒绝")
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
    ap = argparse.ArgumentParser(description="Seedance 2.0 全能模式（frame_images + input_references）")
    ap.add_argument("--prompt", required=True,
                    help="视频描述，可用 [image_n] 占位符引用第 n 张 --ref 参考图")
    ap.add_argument("--first", help="首帧图片：本地路径或公网 URL")
    ap.add_argument("--last", help="尾帧图片：本地路径或公网 URL")
    ap.add_argument("--ref", action="append", default=[],
                    help="参考图（引导风格/内容），可多次传入，顺序对应 [image_1]、[image_2]……")
    ap.add_argument("--audio", help="参考音频（引导节奏）：本地路径或公网 URL")
    ap.add_argument("--video", help="参考视频（引导动作）：本地路径或公网 URL")
    ap.add_argument("--resolution", default="720p", help="480p/720p/1080p/2K/4K，默认 720p")
    ap.add_argument("--aspect-ratio", default="16:9", help="默认 16:9")
    ap.add_argument("--duration", type=int, default=15, help="4-15 秒，默认 15")
    ap.add_argument("--no-audio", action="store_true", help="不生成音频")
    ap.add_argument("--out", default="output/seedance_full.mp4", help="输出路径")
    args = ap.parse_args()

    if not args.ref and not args.audio and not args.video:
        print("全能模式至少需要一个参考素材（--ref / --audio / --video），"
              "只需首尾帧请用 seedance_frames2video.py")
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

    input_references = [{"type": "image_url", "image_url": {"url": resolve_media(r)}}
                        for r in args.ref]
    if args.audio:
        input_references.append({"type": "audio_url",
                                 "audio_url": {"url": resolve_media(args.audio)}})
    if args.video:
        input_references.append({"type": "video_url",
                                 "video_url": {"url": resolve_media(args.video)}})

    payload = {
        "model": "bytedance/seedance-2.0",
        "prompt": args.prompt,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "duration": args.duration,
        "generate_audio": not args.no_audio,
        "input_references": input_references,
    }
    if frame_images:
        payload["frame_images"] = frame_images

    print(f"[提交] bytedance/seedance-2.0 | {args.resolution} {args.aspect_ratio} "
          f"{args.duration}s 全能模式（锚定帧 {len(frame_images)} 张，参考素材 {len(input_references)} 个）")
    result = submit_and_wait(payload)

    print("\n[完成] 最终结果:")
    print(json.dumps(result, ensure_ascii=False)[:800])
    if result.get("status") != "completed":
        print("任务未成功:", result.get("error", result.get("status")))
        sys.exit(1)

    download_video(result, args.out)


if __name__ == "__main__":
    main()
