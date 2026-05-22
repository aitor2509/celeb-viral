"""Iteration 2 tests: Videos/Shorts split, AI recs, News, Secondary channels."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def franco_id(s):
    r = s.get(f"{API}/celebrities", timeout=30)
    assert r.status_code == 200
    for c in r.json():
        if c["name"] == "Franco Escamilla":
            return c["id"]
    pytest.skip("Franco Escamilla not seeded")


def _wait_videos(s, cid, kind, attempts=8):
    """Trigger refresh if empty, then wait."""
    for i in range(attempts):
        r = s.get(f"{API}/celebrities/{cid}/videos", params={"kind": kind}, timeout=30)
        assert r.status_code == 200
        vids = r.json().get("videos", [])
        if vids:
            return vids
        if i == 0:
            # trigger refresh
            s.get(f"{API}/celebrities/{cid}/videos", params={"kind": kind, "refresh": "true"}, timeout=60)
        time.sleep(3)
    return []


# ===== Videos vs Shorts split =====
class TestVideosShortsSplit:
    def test_videos_kind_long(self, s, franco_id):
        vids = _wait_videos(s, franco_id, "video")
        assert len(vids) > 0, "No long videos returned"
        for v in vids:
            assert v.get("is_short") is False, f"Long endpoint returned short: {v.get('video_id')}"
            # duration may be 0 if unparseable, but if present, > 60
            if v.get("duration_seconds"):
                assert v["duration_seconds"] > 60, f"Long video w/ dur<=60: {v['video_id']}"

    def test_shorts_kind_short(self, s, franco_id):
        vids = _wait_videos(s, franco_id, "short")
        assert len(vids) > 0, "No shorts returned"
        for v in vids:
            assert v.get("is_short") is True
            assert 0 < v.get("duration_seconds", 0) <= 60

    def test_videos_recent_sorted(self, s, franco_id):
        r = s.get(f"{API}/celebrities/{franco_id}/videos", params={"kind": "video", "sort": "recent"})
        assert r.status_code == 200
        vids = r.json()["videos"]
        if len(vids) >= 2:
            assert vids[0]["published_at"] >= vids[1]["published_at"]

    def test_viral_shorts(self, s, franco_id):
        r = s.get(f"{API}/celebrities/{franco_id}/viral-videos", params={"kind": "short"})
        assert r.status_code == 200
        vids = r.json()["videos"]
        assert all(v.get("is_short") for v in vids)
        if len(vids) >= 2:
            assert vids[0]["view_count"] >= vids[1]["view_count"]

    def test_viral_videos_long(self, s, franco_id):
        r = s.get(f"{API}/celebrities/{franco_id}/viral-videos", params={"kind": "video"})
        assert r.status_code == 200
        vids = r.json()["videos"]
        assert all(v.get("is_short") is False for v in vids)


# ===== Trending context =====
class TestTrendingContext:
    def test_put_trending_context(self, s, franco_id):
        payload = {"trending_context": "TEST_CTX: temas virales tiktok mexico enero 2026"}
        r = s.put(f"{API}/celebrities/{franco_id}/trending-context", json=payload)
        assert r.status_code == 200, r.text
        # Verify persisted
        r2 = s.get(f"{API}/celebrities/{franco_id}")
        assert r2.status_code == 200
        assert "TEST_CTX" in r2.json().get("trending_context", "")


# ===== AI recommendations (Claude via Emergent) =====
class TestAIRecommendations:
    def test_recommendations_video(self, s, franco_id):
        r = s.post(f"{API}/celebrities/{franco_id}/recommendations",
                   params={"kind": "video"}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "recommendations" in data
        recs = data["recommendations"]
        assert isinstance(recs, list)
        if recs:
            first = recs[0]
            # enriched fields
            assert "video_id" in first
            assert "score" in first
            assert isinstance(first["score"], (int, float))
            assert "reason" in first
            assert isinstance(first["reason"], str) and len(first["reason"]) > 0
        # strategy field present
        assert "strategy" in data


# ===== News =====
class TestNews:
    def test_news_returns_items(self, s, franco_id):
        r = s.get(f"{API}/celebrities/{franco_id}/news", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "news" in data or "items" in data
        items = data.get("news") or data.get("items") or []
        assert isinstance(items, list)
        if items:
            n = items[0]
            assert n.get("title")
            assert n.get("link") or n.get("url")


# ===== Secondary channels =====
class TestSecondaryChannels:
    added_channel_id = None

    def test_add_secondary_channel(self, s, franco_id):
        # search a real channel
        r = s.get(f"{API}/youtube/search", params={"q": "Lo mejor de Franco Escamilla"}, timeout=30)
        assert r.status_code == 200
        results = r.json()["results"]
        assert results
        ch = results[0]
        chan_id = ch["channel_id"]
        TestSecondaryChannels.added_channel_id = chan_id
        r = s.post(f"{API}/celebrities/{franco_id}/secondary-channels",
                   json={"youtube_channel_id": chan_id, "title": ch.get("title", "TEST_CH")}, timeout=60)
        assert r.status_code == 200, r.text
        # verify celeb shows it
        r2 = s.get(f"{API}/celebrities/{franco_id}")
        assert r2.status_code == 200
        sec = r2.json().get("secondary_channels", [])
        ids = [c.get("channel_id") for c in sec]
        assert chan_id in ids

    def test_delete_secondary_channel(self, s, franco_id):
        chan_id = TestSecondaryChannels.added_channel_id
        assert chan_id
        r = s.delete(f"{API}/celebrities/{franco_id}/secondary-channels/{chan_id}")
        assert r.status_code == 200, r.text
        r2 = s.get(f"{API}/celebrities/{franco_id}")
        sec = r2.json().get("secondary_channels", [])
        ids = [c.get("channel_id") for c in sec]
        assert chan_id not in ids
