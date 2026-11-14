# SPDX-License-Identifier: MIT
"""Exercise libSDRForge REST control without external HTTP dependencies."""
from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base: str, path: str, payload: dict[str, object] | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=3) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise TypeError("REST response must be a JSON object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5570")
    parser.add_argument("--frequency", type=int, help="Tune in Hz (changes receiver state)")
    parser.add_argument("--mode", choices=("FM", "NFM", "WFM", "AM"))
    parser.add_argument("--bandwidth", type=int, default=200_000)
    parser.add_argument("--start", action="store_true", help="Start receiver")
    parser.add_argument("--stop", action="store_true", help="Stop receiver")
    args = parser.parse_args()
    try:
        print("health:", json.dumps(request(args.url, "/v1/health"), indent=2))
        if args.frequency is not None:
            print("tune:", request(args.url, "/v1/receiver/frequency", {
                "frequency_hz": args.frequency,
            }))
        if args.mode is not None:
            print("mode:", request(args.url, "/v1/receiver/mode", {
                "mode": args.mode, "bandwidth_hz": args.bandwidth,
            }))
        if args.start:
            print("start:", request(args.url, "/v1/receiver/start", {}))
        if args.stop:
            print("stop:", request(args.url, "/v1/receiver/stop", {}))
        print("receiver:", json.dumps(request(args.url, "/v1/receiver"), indent=2))
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as exc:
        print(f"REST test failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
