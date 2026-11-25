import json
import sqlite3

import pytest

from service import create_app


@pytest.mark.parametrize("mode, status", [("ready", 201), ("closed", 503)])
def test_dispatch_uses_a_saved_number(tmp_path, monkeypatch, capsys, mode, status):
    path = tmp_path / "fresh.sqlite"
    monkeypatch.setenv("SUBMIT_DB", str(path))
    monkeypatch.setenv("DISPATCH_MODE", mode)
    api = create_app().test_client()
    submission = {"group_code": "SE-31", "submission_key": "dispatch-1"}

    answer = api.post("/submissions", json=submission)
    assert answer.status_code == status
    assert answer.json["id"] == 1
    if mode == "ready":
        assert answer.json["delivery"] == {"state": "queued", "reference": "SE-D00001"}
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    expected = "confirmation_failed" if status == 503 else "confirmation_sent"
    assert [row["event"] for row in events] == ["submission_saved", expected, "submission_response"]
    assert {row["request_id"] for row in events} == {answer.headers["X-Request-Id"]}
    assert api.get("/health").json == {"status": "ok", "version": "v2"}
    assert api.get("/submissions/1").json == {"id": 1, **submission}
    replay = api.post("/submissions", json=submission)
    assert (replay.status_code, replay.json) == (200, {"id": 1})
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id FROM submissions").fetchall() == [(1,)]
