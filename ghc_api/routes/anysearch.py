"""Native POST /v1/search with key custody, safe audit, and request statistics."""

import time
import uuid

from flask import Blueprint, Response, g, request

from ..anysearch import SEARCH_PATH, TOOL_NAME, decode_body, is_success, search
from ..anysearch_log import record_search_to_file
from ..auth import ANONYMOUS_USER_ID, redact_auth_headers
from ..cache import cache
from ..counters import counters
from ..state import state
from ..utils import get_client_ip

anysearch_bp = Blueprint("anysearch", __name__)


@anysearch_bp.route(SEARCH_PATH, methods=["POST"])
def anysearch_search():
    started = time.time()
    clock = time.monotonic()
    request_id = str(uuid.uuid4())
    raw_request = request.get_data()
    # The transport is the security boundary. Raw 402 bodies must never reach
    # Flask, its logs, the shared cache, exports, or the browser/model history.
    response = search(raw_request, state, local_request_id=request_id,
                      content_type=request.headers.get("Content-Type"))
    body = decode_body(response.content)
    success = is_success(response.status_code, body)
    counters.incr("anysearch.search" if success else "anysearch.search_error")
    duration = time.monotonic() - clock
    request_body = decode_body(raw_request)
    count = len(body["data"]["results"]) if success else None
    client_ip = get_client_ip(request)
    user_id = getattr(g, "user_id", ANONYMOUS_USER_ID) or ANONYMOUS_USER_ID
    entry = {
        "id": request_id,
        "timestamp": int(started),
        "type": TOOL_NAME,
        "endpoint": SEARCH_PATH,
        "client_ip": client_ip,
        "user_id": user_id,
        "query": request_body.get("query") if isinstance(request_body, dict) else None,
        "request_body": request_body,
        "response_body": body,
        "status_code": response.status_code,
        "upstream": {"status_code": response.upstream_status,
                     "request_id": response.upstream_request_id},
        "business_code": body.get("code") if isinstance(body, dict) else None,
        "result_count": count,
        "duration_ms": int(duration * 1000),
        "state": "completed" if success else "error",
    }
    try:
        record_search_to_file(entry)
    except Exception:
        print("[AnySearch] Failed to record search")
    try:
        cache.add_request(request_id, {
            "client_ip": client_ip,
            "user_id": user_id,
            "request_headers": redact_auth_headers(dict(request.headers)),
            "request_body": request_body,
            "response_body": body,
            "model": TOOL_NAME,
            "endpoint": SEARCH_PATH,
            "status_code": response.status_code,
            "state": entry["state"],
            "upstream_status": response.upstream_status,
            "upstream_request_id": response.upstream_request_id,
            "business_code": entry["business_code"],
            "result_count": count,
            "request_size": len(raw_request),
            "response_size": len(response.content),
            "duration": round(duration, 3),
            "input_tokens": 0,
            "output_tokens": 0,
        })
    except Exception:
        print("[AnySearch] Failed to add request to cache")
    print(f"[AnySearch] request_id={request_id} status={response.status_code} "
          f"success={success} results={count} duration_ms={int(duration * 1000)}")
    return Response(response.content, status=response.status_code, headers=response.headers)
