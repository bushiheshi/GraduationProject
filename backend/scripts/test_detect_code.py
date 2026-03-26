"""本地调试 DroidDetect 代码检测模型的小脚本。

用途：
1. 在不启动 FastAPI 的情况下，直接验证模型是否能加载成功。
2. 按阶段打印耗时，便于判断是下载慢、模型装载慢，还是推理慢。
3. 支持直接传入代码文件，也支持使用内置示例代码做最小测试。

运行方式（在 backend 目录下）：
    python scripts/test_detect_code.py
    python scripts/test_detect_code.py --code-file path/to/homework.py --language python
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 允许从 "backend/scripts" 直接运行时导入同级目录下的 app 包。
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.code_detection_service import (  # noqa: E402
    _load_detection_bundle,
    detect_code_authorship,
)
from app.config import get_settings  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Test DroidDetect code detection model locally')
    parser.add_argument('--code-file', type=str, default=None, help='Path to a local code file to be detected')
    parser.add_argument('--language', type=str, default=None, help='Optional language label for display only')
    parser.add_argument('--filename', type=str, default=None, help='Optional filename shown in result')
    parser.add_argument('--show-chunks', action='store_true', help='Print per-chunk scores in the final result')
    return parser.parse_args()


def load_code(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.code_file:
        file_path = Path(args.code_file).expanduser().resolve()
        return file_path.read_text(encoding='utf-8'), args.filename or file_path.name

    # 这里给一个极小样例，便于先确认模型能否走完整个加载与推理流程。
    sample_code = """def fibonacci(n: int) -> list[int]:
    if n <= 0:
        return []
    if n == 1:
        return [0]

    result = [0, 1]
    while len(result) < n:
        result.append(result[-1] + result[-2])
    return result


if __name__ == '__main__':
    print(fibonacci(8))
"""
    return sample_code, args.filename or 'sample_code.py'


def main() -> int:
    args = parse_args()
    settings = get_settings()
    code, filename = load_code(args)

    print('=== DroidDetect Local Test ===')
    print(f'model_id: {settings.code_detect_model_id}')
    print(f'base_model_id: {settings.code_detect_base_model_id}')
    print(f'code_length: {len(code)}')
    print(f'filename: {filename}')
    if args.language:
        print(f'language: {args.language}')
    print()

    # 分阶段打印加载进度，主要用于判断“卡住”的具体位置。
    bundle_start = time.perf_counter()
    print('[1/2] loading tokenizer + base model + DroidDetect weights ...')
    bundle = _load_detection_bundle()
    bundle_elapsed = time.perf_counter() - bundle_start
    print(f'loaded in {bundle_elapsed:.2f}s')
    print(f"missing_keys: {len(bundle['load_result']['missing_keys'])}")
    print(f"unexpected_keys: {len(bundle['load_result']['unexpected_keys'])}")
    print()

    detect_start = time.perf_counter()
    print('[2/2] running detection ...')
    result = detect_code_authorship(
        code=code,
        filename=filename,
        language=args.language,
    )
    detect_elapsed = time.perf_counter() - detect_start
    print(f'detected in {detect_elapsed:.2f}s')
    print()

    output = dict(result)
    if not args.show_chunks:
        output.pop('chunk_scores', None)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
