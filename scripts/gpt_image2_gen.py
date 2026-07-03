#!/usr/bin/env python3
"""
GPT Image 2 (openai/gpt-5.4-image-2) 图片生成示例，支持文生图与图生图。

对应 docs/openrouter_api_guide.md §3。通过标准 Chat Completions 接口调用，
图片在 message.images[] 中以 base64 data URI 返回。

实测结论（2026-07-03）：
  - 固定输出 1024x1024 PNG，image_tokens 恒为 7024
  - size / quality / n 参数被静默接受但不生效（网关透传但上游不处理）
  - 文生图：messages content 为字符串
  - 图生图：messages content 为数组，含 text + image_url

用法：
    export OPENROUTER_API_KEY=gws_xxx   # 或提前缓存到 ~/.openrouter_cache
    # 文生图
    python scripts/gpt_image2_gen.py --mode text2img --prompt "a cute anime cat girl" --out output/cat.png
    # 图生图（编辑）
    python scripts/gpt_image2_gen.py --mode img2img --prompt "change background to blue" --input input.png --out output/edited.png
"""
import os, sys, json, argparse, base64, subprocess, tempfile
import urllib.request

GATEWAY = os.environ.get("OPENROUTER_BASE_URL", "https://gateway.runloop.ai")
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
MODEL = "openai/gpt-5.4-image-2"


def img_to_data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def call(prompt, input_image=None):
    if input_image:
        url = input_image if input_image.startswith("http") else img_to_data_uri(input_image)
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
    else:
        content = prompt
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}]})
    # 用 curl 子进程处理大 chunked 响应，写入临时文件再解析（urllib 对大响应不稳）
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = tf.name
    try:
        subprocess.run(
            ["curl", "-sS", "-X", "POST", f"{GATEWAY}/api/v1/chat/completions",
             "-H", f"Authorization: Bearer {API_KEY}",
             "-H", "Content-Type: application/json",
             "-d", "@-", "-o", tmp],
            input=body.encode(), check=True, timeout=300,
        )
        with open(tmp, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_images(resp, out_prefix):
    if "choices" not in resp:
        print("错误:", json.dumps(resp.get("error", resp), ensure_ascii=False)[:400])
        sys.exit(1)
    imgs = resp["choices"][0]["message"].get("images", [])
    if not imgs:
        print("未返回图片，content:", str(resp["choices"][0]["message"].get("content"))[:200])
        sys.exit(1)
    paths = []
    for i, im in enumerate(imgs):
        url = im["image_url"]["url"]
        b64 = url.split(",", 1)[1]
        raw = base64.b64decode(b64)
        p = out_prefix if len(imgs) == 1 else f"{os.path.splitext(out_prefix)[0]}_{i}{os.path.splitext(out_prefix)[1]}"
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "wb") as f:
            f.write(raw)
        paths.append(p)
    u = resp.get("usage", {})
    print(f"生成 {len(imgs)} 张图:")
    for p in paths:
        print(f"  - {p} ({os.path.getsize(p)/1024:.0f} KB)")
    print(f"用量: tokens={u.get('total_tokens')} cost=${u.get('cost')} "
          f"image_tokens={u.get('completion_tokens_details', {}).get('image_tokens')}")
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["text2img", "img2img"], default="text2img")
    ap.add_argument("--prompt", required=True, help="生成/编辑指令")
    ap.add_argument("--input", help="图生图模式下的输入图片路径或 URL")
    ap.add_argument("--out", default="output/image.png", help="输出路径")
    args = ap.parse_args()

    if args.mode == "img2img" and not args.input:
        print("img2img 模式需要 --input")
        sys.exit(1)

    print(f"[调用] {MODEL} | {args.mode}")
    resp = call(args.prompt, args.input if args.mode == "img2img" else None)
    save_images(resp, args.out)


if __name__ == "__main__":
    main()
