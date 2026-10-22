#!/usr/bin/env python3
"""Call ghc-api's native AnySearch endpoint, never handling the provider key.

Example:
    python scripts/anysearch_search_demo.py 'Python asyncio TaskGroup docs'
    python scripts/anysearch_search_demo.py 'Go context docs' --tag code.doc --format markdown

Enable AnySearch in the server config first. If ghc-api user authentication is
on, set GHC_API_TOKEN to your ghc-api user token (not the AnySearch API key).
"""

import argparse
import json
import os

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--base-url", default="http://127.0.0.1:8313")
    parser.add_argument("--max-results", type=int, choices=range(1, 11), default=5)
    parser.add_argument("--tag")
    parser.add_argument("--zone", choices=("cn", "intl"))
    parser.add_argument("--language")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    payload = {"query": args.query, "max_results": args.max_results, "format": args.format}
    for name in ("tag", "zone", "language"):
        if getattr(args, name):
            payload[name] = getattr(args, name)
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("GHC_API_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with requests.post(args.base_url.rstrip("/") + "/v1/search", json=payload,
                           headers=headers, timeout=30, allow_redirects=False) as response:
            if not 200 <= response.status_code < 300:
                # Never dump error bodies: a misconfigured endpoint might
                # return credentials in a 402 response rather than proxy errors.
                print(f"Search failed: HTTP {response.status_code}")
                return 1
            body = response.json()
            if not isinstance(body, dict) or body.get("code") != 0:
                print("Search returned an unsuccessful response")
                return 1
            print(json.dumps(body, ensure_ascii=False, indent=2))
    except (requests.RequestException, ValueError):
        print("Search failed: network error or invalid JSON")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
