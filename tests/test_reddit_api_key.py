"""With a Reddit client ID and secret set, posts come from Reddit's authenticated API; without them, the public feed."""
import json
from unittest.mock import patch
from urllib.error import HTTPError

from tradingagents.dataflows.vendors import reddit

_LISTING = json.dumps({"data": {"children": [
    {"data": {"title": "DOCN after earnings", "created_utc": 1794300000.0, "selftext": "Raised guide &amp; ATM",
              "subreddit": "stocks"}},
    {"data": {"title": "DOCN dip", "created_utc": 1794200000.0, "selftext": "", "subreddit": "wallstreetbets"}},
]}}).encode()


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, size=-1):
        return self.body if size is None or size < 0 else self.body[:size]


def _keys(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "the-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "the-secret")


def test_with_keys_the_api_is_used_and_posts_are_parsed(monkeypatch):
    _keys(monkeypatch)
    calls = []

    def opened(req, timeout=None):
        calls.append(req)
        if "access_token" in req.full_url:
            return _Resp(json.dumps({"access_token": "tok-123", "token_type": "bearer"}).encode())
        return _Resp(_LISTING)

    with patch.object(reddit, "urlopen", side_effect=opened):
        posts = reddit._fetch_subreddit_api("DOCN", "wallstreetbets+stocks", 100, 5.0)
    token, search = calls
    assert token.get_method() == "POST" and token.data == b"grant_type=client_credentials"
    assert token.get_header("Authorization").startswith("Basic ")
    assert search.full_url.startswith("https://oauth.reddit.com/r/wallstreetbets+stocks/search.json?")
    assert search.get_header("Authorization") == "Bearer tok-123"
    assert [(p["title"], p["subreddit"]) for p in posts] == [("DOCN after earnings", "stocks"),
                                                            ("DOCN dip", "wallstreetbets")]
    assert posts[0]["selftext"] == "Raised guide & ATM" and posts[0]["created_utc"] == 1794300000.0


def test_the_block_uses_the_api_when_keys_are_set_and_the_feed_when_not(monkeypatch):
    with patch.object(reddit, "_fetch_subreddit_api", return_value=[]) as api, \
            patch.object(reddit, "_fetch_subreddit_rss", return_value=[]) as rss:
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
        reddit.fetch_reddit_posts("DOCN")
        assert rss.call_count == 1 and api.call_count == 0
        _keys(monkeypatch)
        reddit.fetch_reddit_posts("DOCN")
        assert api.call_count == 1 and rss.call_count == 1
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", " ")
        reddit.fetch_reddit_posts("DOCN")
        assert rss.call_count == 2


def test_a_failed_api_call_is_unavailable_and_never_shows_the_secret(monkeypatch, caplog):
    _keys(monkeypatch)
    for failure in (HTTPError("https://www.reddit.com/api/v1/access_token", 401, "Unauthorized", {}, None),
                    OSError("network down")):
        with patch.object(reddit, "urlopen", side_effect=failure):
            assert reddit._fetch_subreddit_api("DOCN", "stocks", 100, 5.0) is None
    for body in (b"not json", json.dumps({"error": "invalid_grant"}).encode()):
        with patch.object(reddit, "urlopen", return_value=_Resp(body)):
            assert reddit._fetch_subreddit_api("DOCN", "stocks", 100, 5.0) is None
    with patch.object(reddit, "urlopen", side_effect=OSError("down")):
        assert "Reddit unavailable" in reddit.fetch_reddit_posts("DOCN")
    assert "the-secret" not in caplog.text and "tok-123" not in caplog.text


def test_only_the_search_result_is_recorded_for_replay(monkeypatch):
    _keys(monkeypatch)
    seen = {}

    def record(name, arguments, live):
        seen.update(name=name, arguments=arguments, value=live())
        return seen["value"]

    def opened(req, timeout=None):
        return _Resp(json.dumps({"access_token": "tok-123"}).encode() if "access_token" in req.full_url else _LISTING)

    with patch.object(reddit, "external_input", side_effect=record), patch.object(reddit, "urlopen", side_effect=opened):
        reddit._fetch_subreddit_api("DOCN", "stocks", 100, 5.0)
    assert seen["value"] == _LISTING
    assert "tok-123" not in json.dumps(seen["arguments"]) and "the-secret" not in json.dumps(seen["arguments"])
