import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request


LOGIN_URL = "https://id.copyleaks.com/v3/account/login/api"
DETECT_URL_TEMPLATE = "https://api.copyleaks.com/v2/writer-detector/{scan_id}/check"
MIN_TEXT_LENGTH = 255


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Copyleaks AI detection against a code file or inline text."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a code file. If omitted, use --text or the built-in demo snippet.",
    )
    parser.add_argument(
        "--text",
        help="Inline code/text to scan instead of reading a file.",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional language code, e.g. en, zh-CN. Copyleaks can auto-detect if omitted.",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Use Copyleaks sandbox mode for integration testing.",
    )
    parser.add_argument(
        "--sensitivity",
        type=int,
        default=2,
        choices=(1, 2, 3),
        help="1=direct AI text, 2=minor edits, 3=heavily modified AI text.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Ask Copyleaks for extra explainability fields when available.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat the input content N times. Useful when testing the API minimum length.",
    )
    parser.add_argument(
        "--save-json",
        default=None,
        help="Optional path to save the raw detection response as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    email = os.getenv("COPYLEAKS_EMAIL")
    api_key = os.getenv("COPYLEAKS_API_KEY")

    if not email or not api_key:
        print(
            "Missing credentials. Set COPYLEAKS_EMAIL and COPYLEAKS_API_KEY first.",
            file=sys.stderr,
        )
        return 1

    content = load_input(args)
    if args.repeat > 1:
        content = "\n".join(content for _ in range(args.repeat))

    if not content.strip():
        print("No content to scan.", file=sys.stderr)
        return 1
    if len(content) < MIN_TEXT_LENGTH:
        print(
            f"Input is too short for Copyleaks: {len(content)} chars. Minimum length is {MIN_TEXT_LENGTH}. "
            "Use a larger file, pass longer --text, or add --repeat.",
            file=sys.stderr,
        )
        return 1

    try:
        token = login(email=email, api_key=api_key)
        result = detect_ai(
            token=token,
            text=content,
            language=args.language,
            sandbox=args.sandbox,
            sensitivity=args.sensitivity,
            explain=args.explain,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_summary(result)
    if args.save_json:
        save_json(Path(args.save_json), result)
    print("\nRaw response:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def load_input(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text

    if args.input:
        return Path(args.input).read_text(encoding="utf-8")

    return """\
def sum_even_numbers(values):
    total = 0
    for value in values:
        if value % 2 == 0:
            total += value
    return total
"""


def login(*, email: str, api_key: str) -> str:
    payload = json.dumps({"email": email, "key": api_key}).encode("utf-8")
    req = request.Request(
        LOGIN_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = http_json(req)
    token = response.get("access_token")
    if not token:
        raise RuntimeError(f"Login succeeded but no access token was returned: {response}")
    return token


def detect_ai(
    *,
    token: str,
    text: str,
    language: str | None,
    sandbox: bool,
    sensitivity: int,
    explain: bool,
) -> dict[str, Any]:
    scan_id = f"scan-{uuid.uuid4().hex[:24]}"
    payload: dict[str, Any] = {
        "text": text,
        "sandbox": sandbox,
        "sensitivity": sensitivity,
        "explain": explain,
    }
    if language:
        payload["language"] = language

    req = request.Request(
        DETECT_URL_TEMPLATE.format(scan_id=scan_id),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    return http_json(req)


def http_json(req: request.Request) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {req.full_url}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {req.full_url}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {req.full_url}: {body}") from exc


def print_summary(result: dict[str, Any]) -> None:
    print("Detection summary:")

    if "model" in result:
        print(f"- model: {result['model']}")

    if "summary" in result and isinstance(result["summary"], dict):
        for key, value in result["summary"].items():
            print(f"- summary.{key}: {value}")

    if "results" in result and isinstance(result["results"], list):
        print(f"- sections: {len(result['results'])}")
        for index, item in enumerate(result["results"][:5], start=1):
            score = item.get("score")
            classification = item.get("classification")
            print(f"  {index}. classification={classification}, score={score}")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved JSON: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
