import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://celeb-viral.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def celebs(s):
    r = s.get(f"{API}/celebrities", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) >= 5
    return data


# ===== Celebrities =====
class TestCelebrities:
    def test_list_celebrities_seeded(self, celebs):
        names = {c["name"] for c in celebs}
        expected = {"Franco Escamilla", "Don Cheto", "El Potro", "Said el Interrogatorio", "Rica Famosa Latina"}
        assert expected.issubset(names)
        # YouTube data populated
        for c in celebs:
            if c["name"] in expected:
                assert c["youtube_channel_id"], f"missing channel for {c['name']}"
                assert c["subscriber_count"] > 0, f"no subs for {c['name']}"

    def test_get_celebrity(self, s, celebs):
        cid = celebs[0]["id"]
        r = s.get(f"{API}/celebrities/{cid}")
        assert r.status_code == 200
        assert r.json()["id"] == cid

    def test_get_celebrity_404(self, s):
        r = s.get(f"{API}/celebrities/nonexistent-id")
        assert r.status_code == 404


# ===== Videos =====
class TestVideos:
    def test_videos_for_franco(self, s, celebs):
        franco = next(c for c in celebs if c["name"] == "Franco Escamilla")
        # Wait briefly for background fetch to complete (seed startup task)
        videos = []
        for _ in range(6):
            r = s.get(f"{API}/celebrities/{franco['id']}/videos", timeout=30)
            assert r.status_code == 200
            videos = r.json().get("videos", [])
            if videos:
                break
            time.sleep(3)
        assert len(videos) > 0, "No videos for Franco"
        v = videos[0]
        assert v["title"] and v["thumbnail_url"] and v["video_id"]
        assert isinstance(v["view_count"], int)

    def test_viral_videos_sorted_desc(self, s, celebs):
        franco = next(c for c in celebs if c["name"] == "Franco Escamilla")
        r = s.get(f"{API}/celebrities/{franco['id']}/viral-videos")
        assert r.status_code == 200
        vids = r.json()["videos"]
        if len(vids) >= 2:
            assert vids[0]["view_count"] >= vids[1]["view_count"]


# ===== YouTube Search =====
class TestYouTubeSearch:
    def test_search_luis_fonsi(self, s):
        r = s.get(f"{API}/youtube/search", params={"q": "Luis Fonsi"}, timeout=30)
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) > 0
        assert "channel_id" in results[0]
        assert "title" in results[0]


# ===== Celebrity CRUD =====
class TestCelebrityCRUD:
    created_id = None
    channel_id = "UCYzPXprvl5Y-Sf0g4vX-m6g"  # Jacksepticeye-ish - any popular channel

    def test_add_celebrity(self, s):
        # First search a real channel
        r = s.get(f"{API}/youtube/search", params={"q": "Luisito Comunica"})
        results = r.json()["results"]
        assert len(results) > 0
        cid = results[0]["channel_id"]
        payload = {
            "name": "TEST_Luisito",
            "color": "#ABCDEF",
            "youtube_channel_id": cid,
        }
        r = s.post(f"{API}/celebrities", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Luisito"
        assert data["youtube_channel_id"] == cid
        assert data["subscriber_count"] >= 0
        TestCelebrityCRUD.created_id = data["id"]

    def test_delete_celebrity_cascade(self, s):
        cid = TestCelebrityCRUD.created_id
        assert cid
        r = s.delete(f"{API}/celebrities/{cid}")
        assert r.status_code == 200
        # verify gone
        r = s.get(f"{API}/celebrities/{cid}")
        assert r.status_code == 404


# ===== Virals =====
class TestVirals:
    viral_id = None

    def test_add_viral_creates_notification(self, s, celebs):
        franco_id = next(c["id"] for c in celebs if c["name"] == "Franco Escamilla")
        # count notifs before
        before = s.get(f"{API}/notifications").json()["notifications"]
        payload = {"title": "TEST_ViralX", "description": "test desc", "tag": "viral", "source_url": "https://x.com"}
        r = s.post(f"{API}/celebrities/{franco_id}/virals", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["title"] == "TEST_ViralX"
        TestVirals.viral_id = data["id"]
        # list virals
        r = s.get(f"{API}/celebrities/{franco_id}/virals")
        assert r.status_code == 200
        titles = [v["title"] for v in r.json()["virals"]]
        assert "TEST_ViralX" in titles
        # notification created
        after = s.get(f"{API}/notifications").json()["notifications"]
        assert len(after) > len(before)

    def test_delete_viral(self, s):
        vid = TestVirals.viral_id
        assert vid
        r = s.delete(f"{API}/virals/{vid}")
        assert r.status_code == 200


# ===== Notifications =====
class TestNotifications:
    def test_list_and_mark_read(self, s, celebs):
        # ensure there is at least one notif (create viral)
        franco_id = next(c["id"] for c in celebs if c["name"] == "Franco Escamilla")
        s.post(f"{API}/celebrities/{franco_id}/virals", json={"title": "TEST_NotifViral", "description": "x", "tag": "viral"})
        r = s.get(f"{API}/notifications")
        assert r.status_code == 200
        body = r.json()
        assert "notifications" in body and "unread" in body
        if body["notifications"]:
            nid = body["notifications"][0]["id"]
            r = s.post(f"{API}/notifications/{nid}/read")
            assert r.status_code == 200

    def test_mark_all_read(self, s):
        r = s.post(f"{API}/notifications/read-all")
        assert r.status_code == 200
        r = s.get(f"{API}/notifications")
        assert r.json()["unread"] == 0


# ===== Contacts =====
class TestContacts:
    def test_add_contact(self, s, celebs):
        cid = celebs[0]["id"]
        payload = {"celebrity_id": cid, "phone": "+15551112222", "name": "TEST_User"}
        r = s.post(f"{API}/contacts", json=payload)
        assert r.status_code == 200
        assert r.json()["phone"] == "+15551112222"


# ===== Refresh all =====
class TestRefreshAll:
    def test_refresh_all(self, s):
        r = s.post(f"{API}/refresh-all", timeout=120)
        assert r.status_code == 200
        assert r.json()["ok"] is True
