#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

SUBMIT_URL = "https://aireiter.com/api/openapi/submit"
QUERY_URL = "https://aireiter.com/api/openapi/query"
DEFAULT_MODEL = "gpt_image_2"
DEFAULT_ASPECT_RATIO = "3:4"
DEFAULT_RESOLUTION = "2K"
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_TIMEOUT = 300.0
CONFIG_PATH = pathlib.Path(__file__).resolve().parents[1] / "references" / "config.json"
MODEL_ALIASES = {
    "gpt-image-2": "gpt_image_2",
    "gpt image 2": "gpt_image_2",
    "gptimage2": "gpt_image_2",
    "gpt_image_2": "gpt_image_2",
    "nano-banana-v2": "nano_banana_v2",
    "nano banana v2": "nano_banana_v2",
    "nanobanana v2": "nano_banana_v2",
    "nanobananav2": "nano_banana_v2",
    "nano_banana_v2": "nano_banana_v2",
    "nano-banana-v2-base": "nano_banana_v2_base",
    "nano banana v2 base": "nano_banana_v2_base",
    "nanobanana v2 base": "nano_banana_v2_base",
    "nano_banana_v2_base": "nano_banana_v2_base",
    "nano-banana-v2-plus": "nano_banana_v2_plus",
    "nano banana v2 plus": "nano_banana_v2_plus",
    "nanobanana v2 plus": "nano_banana_v2_plus",
    "nano_banana_v2_plus": "nano_banana_v2_plus",
    "nano-banana-v2-max": "nano_banana_v2_max",
    "nano banana v2 max": "nano_banana_v2_max",
    "nanobanana v2 max": "nano_banana_v2_max",
    "nano_banana_v2_max": "nano_banana_v2_max",
}


def fatal(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # AIReiter's CDN currently rejects urllib's default Python user agent.
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
    }


def post_json(url: str, payload: dict, api_key: str) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=build_headers(api_key), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fatal(f"HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        fatal(f"Request failed: {exc}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        fatal(f"Invalid JSON response: {exc}\n{raw}")


def is_submit_accepted(response: dict) -> bool:
    """Return True only when AIReiter actually accepted the submitted task."""
    if response.get("ok") is False:
        return False

    status_code = response.get("statusCode")
    if isinstance(status_code, int) and status_code >= 400:
        return False
    if isinstance(status_code, str) and status_code.isdigit() and int(status_code) >= 400:
        return False

    message = str(response.get("message") or response.get("error") or "").lower()
    failure_markers = (
        "not enough credits",
        "insufficient credit",
        "forbidden",
        "unauthorized",
        "failed",
        "error",
    )
    if any(marker in message for marker in failure_markers):
        return False

    data = response.get("data")
    if not isinstance(data, dict):
        return False

    status = str(data.get("status") or "").lower()
    if status in {"pending", "processing", "completed"}:
        return True

    return bool(str(data.get("out_task_id") or "").strip())


def file_to_data_url(path_text: str) -> str:
    path = pathlib.Path(path_text).expanduser().resolve()
    if not path.is_file():
        fatal(f"Image file not found: {path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "application/octet-stream"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def normalize_image_input(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://") or value.startswith("data:"):
        return value
    return file_to_data_url(value)


def normalize_model_name(value: str) -> str:
    """Accept common spoken model aliases while preserving unknown API names."""
    raw = (value or DEFAULT_MODEL).strip()
    key = " ".join(raw.lower().replace("_", " ").replace("-", " ").split())
    compact = key.replace(" ", "")
    return MODEL_ALIASES.get(raw, MODEL_ALIASES.get(key, MODEL_ALIASES.get(compact, raw)))


def make_task_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


def submit_task(args: argparse.Namespace) -> int:
    api_key = (args.api_key or "").strip() or env_api_key()
    if not api_key:
        fatal("Missing AIReiter API key. Pass --api-key or set AIREITER_API_KEY.")

    task_id = args.task_id or make_task_id(args.task_prefix)
    params = {"prompt": args.prompt}
    if args.aspect_ratio:
        params["aspect_ratio"] = args.aspect_ratio
    if args.resolution:
        params["resolution"] = args.resolution
    if args.image:
        params["image_url"] = [normalize_image_input(item) for item in args.image]

    payload = {
        "model": normalize_model_name(args.model),
        "params": params,
        "out_task_id": task_id,
    }
    result = post_json(SUBMIT_URL, payload, api_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not is_submit_accepted(result):
        fatal("AIReiter submit was not accepted; trigger imagegen fallback in the orchestrating agent.")
    return 0


def query_task(args: argparse.Namespace) -> int:
    result = post_json(QUERY_URL, {"out_task_id": args.task_id}, args.api_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def extract_status(response: dict) -> str:
    data = response.get("data") or {}
    return str(data.get("status") or "")


def wait_task(args: argparse.Namespace) -> int:
    deadline = time.time() + args.timeout
    while True:
        result = post_json(QUERY_URL, {"out_task_id": args.task_id}, args.api_key)
        status = extract_status(result)
        if status in {"completed", "failed"}:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if status == "completed" else 1
        if time.time() >= deadline:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            fatal(f"Timed out waiting for task {args.task_id}")
        time.sleep(args.interval)


def encode_file(args: argparse.Namespace) -> int:
    print(file_to_data_url(args.path))
    return 0


def config_api_key() -> str:
    if not CONFIG_PATH.is_file():
        return ""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("api_key") or "").strip()


def env_api_key() -> str:
    return (os.environ.get("AIREITER_API_KEY") or "").strip() or config_api_key()


def env_model() -> str:
    return normalize_model_name(os.environ.get("AIREITER_MODEL") or DEFAULT_MODEL)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIReiter image generation helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="convert local image to data URL")
    encode_parser.add_argument("path", help="absolute or relative image path")
    encode_parser.set_defaults(func=encode_file)

    submit_parser = subparsers.add_parser("submit", help="submit image generation task")
    submit_parser.add_argument(
        "--api-key",
        default=env_api_key(),
        help="AIReiter API key; defaults to AIREITER_API_KEY when set",
    )
    submit_parser.add_argument("--prompt", required=True, help="generation prompt")
    submit_parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT_RATIO, help="e.g. 1:1, 3:4, 16:9, 9:16")
    submit_parser.add_argument("--resolution", default=DEFAULT_RESOLUTION, help="e.g. 2K; default: 2K")
    submit_parser.add_argument("--image", action="append", default=[], help="reference image URL, data URL, or local path; repeatable")
    submit_parser.add_argument("--task-id", default="", help="explicit out_task_id")
    submit_parser.add_argument("--task-prefix", default="aireiter", help="task id prefix when --task-id is omitted")
    submit_parser.add_argument(
        "--model",
        default=env_model(),
        help="model name or alias, e.g. gpt_image_2, nano_banana_v2, nanobanana V2; default: gpt_image_2",
    )
    submit_parser.set_defaults(func=submit_task)

    query_parser = subparsers.add_parser("query", help="query task status")
    query_parser.add_argument("--api-key", default=env_api_key(), help="AIReiter API key; defaults to AIREITER_API_KEY or references/config.json")
    query_parser.add_argument("--task-id", required=True, help="out_task_id to query")
    query_parser.set_defaults(func=query_task)

    wait_parser = subparsers.add_parser("wait", help="poll until task completes or fails")
    wait_parser.add_argument("--api-key", default=env_api_key(), help="AIReiter API key; defaults to AIREITER_API_KEY or references/config.json")
    wait_parser.add_argument("--task-id", required=True, help="out_task_id to poll")
    wait_parser.add_argument("--interval", type=float, default=DEFAULT_POLL_INTERVAL, help="poll interval seconds")
    wait_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="max wait time seconds")
    wait_parser.set_defaults(func=wait_task)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
