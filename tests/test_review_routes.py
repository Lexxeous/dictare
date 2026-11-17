"""Private review endpoints reject remote, rebinding, and cross-origin access."""

from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dictare.core.http_routes_review import register_review_routes
from dictare.core.prompt_review import ReviewSlot, UnavailableReviewAgent


def make_client(client=("127.0.0.1", 1234)):
    slot = ReviewSlot()
    engine = Mock()
    engine.review_snapshot.side_effect = slot.snapshot
    engine.discard_review.side_effect = slot.discard
    engine.send_review.return_value = "failed"
    app = FastAPI()
    register_review_routes(app, Mock(engine=engine))
    return TestClient(app, base_url="http://127.0.0.1:8770", client=client), slot, engine


def test_local_draft_can_be_read_and_discarded_without_caching():
    client, slot, _ = make_client()
    draft = slot.hold(UnavailableReviewAgent("keyboard"), [{"text": "private", "secret": "metadata"}])
    assert draft is not None
    response = client.get("/api/review")
    assert response.json() == {"draft": {"id": draft.id, "destination": "keyboard", "messages": ["private"], "sending": False, "can_send": False}}
    assert response.headers["cache-control"] == "no-store"
    result = client.post(f"/api/review/{draft.id}/discard", headers={"origin": "http://127.0.0.1:8770"})
    assert result.json() == {"status": "discarded"}
    assert client.get("/api/review").json() == {"draft": None}


def test_remote_rebinding_and_cross_origin_requests_are_rejected():
    client, slot, engine = make_client()
    draft = slot.hold(UnavailableReviewAgent("codex"), [{"text": "private"}])
    assert draft is not None
    assert client.get("/api/review", headers={"host": "attacker.example"}).status_code == 403
    assert client.get("/api/review", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/api/review", headers={"origin": "http://["}).status_code == 403
    assert client.post(f"/api/review/{draft.id}/send", headers={"origin": "https://attacker.example"}).status_code == 403
    engine.send_review.assert_not_called()
    remote, _, _ = make_client(client=("192.0.2.1", 1234))
    assert remote.get("/api/review").status_code == 403
