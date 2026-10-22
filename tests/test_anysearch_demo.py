"""The CLI uses the local proxy token and never dumps sensitive error bodies."""

from pathlib import Path
import runpy
from unittest.mock import MagicMock, Mock

import pytest
import requests


@pytest.mark.parametrize("status", [200, 402, 429])
def test_demo_response_handling(monkeypatch, capsys, status):
    demo = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "anysearch_search_demo.py"))
    monkeypatch.setattr("sys.argv", ["anysearch_search_demo.py", "query", "--tag", "code.doc"])
    monkeypatch.setenv("GHC_API_TOKEN", "LOCAL-USER-TOKEN")
    response = Mock(status_code=status)
    response.json.return_value = {"code": 0, "data": {"results": []}}
    if status != 200:
        response.json.side_effect = AssertionError("must not inspect sensitive error body")
    context = MagicMock()
    context.__enter__.return_value = response
    post = Mock(return_value=context)
    monkeypatch.setattr(requests, "post", post)
    assert demo["main"]() == (0 if status == 200 else 1)
    assert post.call_args.args == ("http://127.0.0.1:8313/v1/search",)
    kwargs = post.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer LOCAL-USER-TOKEN"
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"]["tag"] == "code.doc"
    assert "LOCAL-USER-TOKEN" not in capsys.readouterr().out
    if status != 200:
        response.json.assert_not_called()
