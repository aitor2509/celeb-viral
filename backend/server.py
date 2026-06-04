from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import logging
import asyncio
import re
import json
import urllib.parse
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import isodate
import feedparser
import requests
from groq import Groq


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

app = FastAPI(title="CelebTracker API")
api_router = APIRouter(prefix="/api")

MIN_RESULTS_PER_SECTION = 50
RECENT_UPLOAD_SCAN_LIMIT = 250
VIRAL_CHANNEL_SCAN_LIMIT = 200
VIDEO_RESPONSE_LIMIT = 200
VIDEO_BOMB_VIEWS_THRESHOLD = 50000  # ajustable según el canal


def is_video_bomb(video: dict) -> bool:
    """Detect 'video bomba': high view-count video published in the last 48h."""
    try:
        views = int(video.get("view_count", 0))
        pub = video.get("published_at", "")
        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        hours_old = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
        return views >= VIDEO_BOMB_VIEWS_THRESHOLD and hours_old <= 48
    except Exception:
        return False


# ===== Models =====
class Celebrity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    color: str  # hex like #007AFF
    image_url: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    youtube_channel_handle: Optional[str] = None
    secondary_channels: List[dict] = []  # [{channel_id, title, thumbnail}]
    subscriber_count: int = 0
    video_count: int = 0
    trending_context: str = ""  # user-provided trending topics for AI recommendations
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CelebrityCreate(BaseModel):
    name: str
    color: str
    youtube_channel_id: str
    image_url: Optional[str] = None


class SecondaryChannelAdd(BaseModel):
    youtube_channel_id: str


class TrendingContextUpdate(BaseModel):
    trending_context: str


class CelebrityVideo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_id: str
    channel_id: str = ""
    channel_title: str = ""
    video_id: str
    title: str
    description: str
    thumbnail_url: str
    published_at: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration: Optional[str] = None
    duration_seconds: int = 0
    is_short: bool = False
    viral_score: int = 0
    url: str
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ViralEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_id: str
    title: str
    description: str
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    tag: str = "viral"  # viral | funa | colab | noticia
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ViralCreate(BaseModel):
    title: str
    description: str
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    tag: str = "viral"


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_id: str
    celebrity_name: str
    celebrity_color: str
    type: str  # new_video | viral | funa
    title: str
    message: str
    link: Optional[str] = None
    image_url: Optional[str] = None
    read: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContactSubscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_id: str
    phone: str
    name: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContactCreate(BaseModel):
    celebrity_id: str
    phone: str
    name: Optional[str] = None


# ===== YouTube Service =====
def yt_service():
    if not YOUTUBE_API_KEY:
        raise HTTPException(status_code=500, detail="YouTube API key not configured")
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False)


async def fetch_channel_info(channel_id: str):
    try:
        yt = yt_service()
        resp = yt.channels().list(part="snippet,statistics", id=channel_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        return {
            "channel_id": item["id"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "thumbnail": item["snippet"]["thumbnails"].get("high", item["snippet"]["thumbnails"]["default"])["url"],
            "subscriber_count": int(item["statistics"].get("subscriberCount", 0)),
            "video_count": int(item["statistics"].get("videoCount", 0)),
            "view_count": int(item["statistics"].get("viewCount", 0)),
        }
    except HttpError as e:
        logging.error(f"YouTube fetch_channel_info error: {e}")
        return None


async def fetch_latest_videos(channel_id: str, max_results: int = RECENT_UPLOAD_SCAN_LIMIT):
    """Fetch latest videos from a channel using the uploads playlist (paginated up to max_results)."""
    try:
        yt = yt_service()
        ch_resp = yt.channels().list(part="contentDetails,snippet", id=channel_id).execute()
        items = ch_resp.get("items", [])
        if not items:
            return []
        channel_title = items[0]["snippet"]["title"]
        uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        video_ids = []
        page_token = None
        while len(video_ids) < max_results:
            pl_resp = yt.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist,
                maxResults=min(50, max_results - len(video_ids)),
                pageToken=page_token,
            ).execute()
            video_ids.extend([it["contentDetails"]["videoId"] for it in pl_resp.get("items", [])])
            page_token = pl_resp.get("nextPageToken")
            if not page_token:
                break
        if not video_ids:
            return []
        results = []
        # videos.list supports up to 50 ids at a time
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            vids_resp = yt.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(batch),
            ).execute()
            for v in vids_resp.get("items", []):
                duration_str = v["contentDetails"].get("duration", "PT0S")
                try:
                    duration_sec = int(isodate.parse_duration(duration_str).total_seconds())
                except Exception:
                    duration_sec = 0
                is_short = duration_sec > 0 and duration_sec <= 180
                results.append({
                    "channel_id": channel_id,
                    "channel_title": channel_title,
                    "video_id": v["id"],
                    "title": v["snippet"]["title"],
                    "description": v["snippet"].get("description", "")[:1000],
                    "thumbnail_url": v["snippet"]["thumbnails"].get("high", v["snippet"]["thumbnails"]["default"])["url"],
                    "published_at": v["snippet"]["publishedAt"],
                    "view_count": int(v["statistics"].get("viewCount", 0)),
                    "like_count": int(v["statistics"].get("likeCount", 0)),
                    "comment_count": int(v["statistics"].get("commentCount", 0)),
                    "duration": duration_str,
                    "duration_seconds": duration_sec,
                    "is_short": is_short,
                    "url": f"https://www.youtube.com/watch?v={v['id']}" if not is_short else f"https://www.youtube.com/shorts/{v['id']}",
                })
        return results
    except HttpError as e:
        logging.error(f"YouTube fetch_latest_videos error: {e}")
        return []


def fetch_top_viewed_from_channel(channel_id: str, max_results: int = VIRAL_CHANNEL_SCAN_LIMIT):
    """Use search.list with order=viewCount to get the all-time top-viewed videos from a channel."""
    try:
        yt = yt_service()
        ids = []
        page_token = None
        while len(ids) < max_results:
            resp = yt.search().list(
                part="id",
                channelId=channel_id,
                type="video",
                order="viewCount",
                maxResults=min(50, max_results - len(ids)),
                pageToken=page_token,
            ).execute()
            ids.extend([it["id"]["videoId"] for it in resp.get("items", []) if it.get("id", {}).get("videoId")])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        if not ids:
            return []
        results = []
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            vids_resp = yt.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(batch),
            ).execute()
            for v in vids_resp.get("items", []):
                duration_str = v["contentDetails"].get("duration", "PT0S")
                try:
                    duration_sec = int(isodate.parse_duration(duration_str).total_seconds())
                except Exception:
                    duration_sec = 0
                is_short = duration_sec > 0 and duration_sec <= 180
                results.append({
                    "channel_id": channel_id,
                    "video_id": v["id"],
                    "title": v["snippet"]["title"],
                    "description": v["snippet"].get("description", "")[:1000],
                    "thumbnail_url": v["snippet"]["thumbnails"].get("high", v["snippet"]["thumbnails"]["default"])["url"],
                    "published_at": v["snippet"]["publishedAt"],
                    "view_count": int(v["statistics"].get("viewCount", 0)),
                    "like_count": int(v["statistics"].get("likeCount", 0)),
                    "comment_count": int(v["statistics"].get("commentCount", 0)),
                    "duration": duration_str,
                    "duration_seconds": duration_sec,
                    "is_short": is_short,
                    "url": f"https://www.youtube.com/watch?v={v['id']}" if not is_short else f"https://www.youtube.com/shorts/{v['id']}",
                })
        return results
    except HttpError as e:
        logging.error(f"top viewed error: {e}")
        return []


def search_youtube_channels(query: str, max_results: int = 8):
    try:
        yt = yt_service()
        resp = yt.search().list(
            part="snippet", q=query, type="channel", maxResults=max_results,
        ).execute()
        return [{
            "channel_id": it["snippet"]["channelId"],
            "title": it["snippet"]["title"],
            "description": it["snippet"].get("description", ""),
            "thumbnail": it["snippet"]["thumbnails"].get("high", it["snippet"]["thumbnails"]["default"])["url"],
        } for it in resp.get("items", [])]
    except HttpError as e:
        logging.error(f"search error: {e}")
        raise HTTPException(status_code=400, detail=f"YouTube search failed: {str(e)}")


# ===== Viral Score (free, heuristic) =====
HOT_KEYWORDS = [
    "funa", "polémica", "polemica", "viral", "controversia", "escándalo", "escandalo",
    "exclusiva", "revelación", "revelacion", "exposed", "confiesa", "rompe el silencio",
    "trump", "presidente", "guerra", "ucrania", "muere", "muerte", "detenido",
    "cárcel", "carcel", "demanda", "denuncia", "feminicidio", "narco",
    "vs", "pelea", "responde", "callar", "lloró", "lloro", "se quiebra",
    "?", "¿", "!", "shock", "increíble", "increible",
]


def compute_viral_score(video: dict, channel_subs: int) -> int:
    """Heuristic 0-100 score. Free, no API."""
    try:
        views = max(int(video.get("view_count", 0)), 0)
        likes = max(int(video.get("like_count", 0)), 0)
        comments = max(int(video.get("comment_count", 0)), 0)
        subs = max(int(channel_subs or 0), 1)
        pub = video.get("published_at", "")
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            days_old = max((datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400, 0.5)
        except Exception:
            days_old = 30
        velocity = views / days_old  # views per day
        # log-scaled normalizations
        import math
        # velocity score: 0-40 (10K/day ~= 30, 100K/day ~= 40)
        velocity_score = min(40, math.log10(max(velocity, 1)) * 9)
        # reach: views/subs (rare viral hit). 0-25
        reach = views / subs
        reach_score = min(25, math.log10(max(reach * 100, 1)) * 8)
        # engagement: (likes + comments*3) / views. 0-20
        eng = (likes + comments * 3) / max(views, 1)
        engagement_score = min(20, eng * 400)
        # recency: 0-10 if <14 days
        recency_score = max(0, 10 - (days_old / 1.4)) if days_old < 14 else 0
        # title heat: 0-5
        title = (video.get("title", "") + " " + video.get("description", "")[:200]).lower()
        heat_hits = sum(1 for k in HOT_KEYWORDS if k in title)
        heat_score = min(5, heat_hits * 1.5)
        total = velocity_score + reach_score + engagement_score + recency_score + heat_score
        return int(round(min(100, max(0, total))))
    except Exception:
        return 0


# ===== Chapter Parser (free) =====
TIMESTAMP_RE = re.compile(r"(?:^|\s)(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—:]?\s*([^\n]{3,120})", re.MULTILINE)


def ts_to_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def parse_chapters(description: str, total_duration: int = 0):
    """Extracts timestamped chapters from a video description."""
    if not description:
        return []
    chapters = []
    for m in TIMESTAMP_RE.finditer(description):
        ts = m.group(1)
        topic = m.group(2).strip().strip("-–—:").strip()
        if len(topic) < 3:
            continue
        sec = ts_to_seconds(ts)
        chapters.append({"start": sec, "ts": ts, "topic": topic})
    # sort and compute durations
    chapters.sort(key=lambda c: c["start"])
    for i, c in enumerate(chapters):
        next_start = chapters[i + 1]["start"] if i + 1 < len(chapters) else (total_duration or c["start"] + 600)
        c["duration"] = max(next_start - c["start"], 0)
        c["end_ts"] = f"{next_start // 60}:{next_start % 60:02d}"
    return chapters


def score_chapter_for_clip(chapter: dict) -> int:
    """Score a chapter 0-100 based on duration suitability + keyword heat."""
    dur = chapter.get("duration", 0)
    # ideal clip length: 45s - 180s
    if dur < 20:
        dur_score = max(0, dur * 1.5)
    elif 20 <= dur <= 45:
        dur_score = 30 + (dur - 20) * 0.8
    elif 45 < dur <= 180:
        dur_score = 50
    elif 180 < dur <= 300:
        dur_score = 40 - (dur - 180) / 12
    else:
        dur_score = max(5, 25 - (dur - 300) / 60)
    topic = chapter.get("topic", "").lower()
    heat = sum(1 for k in HOT_KEYWORDS if k in topic)
    heat_score = min(50, heat * 12)
    return int(min(100, dur_score + heat_score))


# ===== Seeding =====
INITIAL_CELEBRITIES = [
    {"name": "Franco Escamilla", "color": "#007AFF", "query": "Franco Escamilla", "channel_id": "UC9gQc88X-EVzYJsr_yOSnvA"},
    {"name": "Don Cheto", "color": "#FF6B00", "query": "Don Cheto Al Aire", "channel_id": "UCdvHnZHBYhUBLDPlGdLwsfA"},
    {"name": "El Potro", "color": "#00FF66", "query": "El Potro Caballero", "channel_id": "UC3WnDvtSQ1cwwjsfTGjJ4OQ"},
    {"name": "Said el Interrogatorio", "color": "#FF3B30", "query": "Said El Interrogatorio", "channel_id": "UC2Zb6N7d_W7M2tBVf6vXp2g"},
    {"name": "Rica Famosa Latina", "color": "#FF007F", "query": "Rica Famosa Latina", "channel_id": "UCWvtmJBPJ4dpA_22IoYHJYg"},
]


async def seed_celebrities():
    count = await db.celebrities.count_documents({})
    if count > 0:
        return
    logging.info("Seeding initial celebrities...")
    for c in INITIAL_CELEBRITIES:
        # try with channel_id; fall back to search
        info = await fetch_channel_info(c["channel_id"])
        if not info:
            results = search_youtube_channels(c["query"], max_results=1)
            if results:
                info = await fetch_channel_info(results[0]["channel_id"])
        if not info:
            # store without youtube data
            celeb = Celebrity(name=c["name"], color=c["color"])
        else:
            celeb = Celebrity(
                name=c["name"],
                color=c["color"],
                image_url=info["thumbnail"],
                youtube_channel_id=info["channel_id"],
                subscriber_count=info["subscriber_count"],
                video_count=info["video_count"],
            )
        await db.celebrities.insert_one(celeb.model_dump())
    logging.info("Seeding done.")


# ===== Routes: Celebrities =====
@api_router.get("/celebrities", response_model=List[Celebrity])
async def list_celebrities():
    docs = await db.celebrities.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return docs


@api_router.get("/celebrities/{celeb_id}", response_model=Celebrity)
async def get_celebrity(celeb_id: str):
    doc = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    return doc


@api_router.post("/celebrities", response_model=Celebrity)
async def add_celebrity(payload: CelebrityCreate):
    info = await fetch_channel_info(payload.youtube_channel_id)
    celeb = Celebrity(
        name=payload.name,
        color=payload.color,
        image_url=payload.image_url or (info["thumbnail"] if info else None),
        youtube_channel_id=payload.youtube_channel_id,
        subscriber_count=info["subscriber_count"] if info else 0,
        video_count=info["video_count"] if info else 0,
    )
    await db.celebrities.insert_one(celeb.model_dump())
    # Fetch all videos for the new celebrity (full channel scan)
    asyncio.create_task(refresh_celebrity_videos(celeb.id, notify=False))
    return celeb


@api_router.delete("/celebrities/{celeb_id}")
async def delete_celebrity(celeb_id: str):
    res = await db.celebrities.delete_one({"id": celeb_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.videos.delete_many({"celebrity_id": celeb_id})
    await db.virals.delete_many({"celebrity_id": celeb_id})
    await db.notifications.delete_many({"celebrity_id": celeb_id})
    return {"ok": True}


# ===== Routes: YouTube Search =====
@api_router.get("/youtube/search")
async def youtube_search(q: str):
    return {"results": search_youtube_channels(q, max_results=8)}


# ===== Routes: Videos =====
async def refresh_celebrity_videos(celeb_id: str, channel_id: str = None, notify: bool = True):
    """Refresh videos from main + secondary channels."""
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        return []
    channels_to_fetch = []
    if channel_id:
        channels_to_fetch.append(channel_id)
    else:
        if celeb.get("youtube_channel_id"):
            channels_to_fetch.append(celeb["youtube_channel_id"])
        for sc in celeb.get("secondary_channels", []):
            channels_to_fetch.append(sc["channel_id"])
    existing_ids = set()
    async for v in db.videos.find({"celebrity_id": celeb_id}, {"_id": 0, "video_id": 1}):
        existing_ids.add(v["video_id"])
    had_previous = len(existing_ids) > 0
    all_new = []
    for ch_id in channels_to_fetch:
        videos = await fetch_latest_videos(ch_id, max_results=RECENT_UPLOAD_SCAN_LIMIT)
        # compute viral score per video using main channel subs
        channel_subs = celeb.get("subscriber_count", 1)
        for v in videos:
            v["viral_score"] = compute_viral_score(v, channel_subs)
        new_videos = [v for v in videos if v["video_id"] not in existing_ids]
        all_new.extend(new_videos)
        for v in videos:
            doc = CelebrityVideo(celebrity_id=celeb_id, **v).model_dump()
            await db.videos.update_one(
                {"celebrity_id": celeb_id, "video_id": v["video_id"]},
                {"$set": doc},
                upsert=True,
            )
    await db.video_refresh_state.update_one(
        {"_key": f"{celeb_id}:uploads"},
        {"$set": {
            "_key": f"{celeb_id}:uploads",
            "celebrity_id": celeb_id,
            "scan_limit": RECENT_UPLOAD_SCAN_LIMIT,
            "channels": channels_to_fetch,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    if notify and had_previous:
        for v in all_new:
            label = "short" if v["is_short"] else "video"
            is_bomb = is_video_bomb(v)
            if is_bomb:
                try:
                    views_k = int(v.get("view_count", 0) / 1000)
                except Exception:
                    views_k = 0
                notif_type = "video_bomb"
                notif_title = f"💣 {celeb['name']} BOMBA: {views_k}K views"
            else:
                notif_type = "new_video"
                notif_title = f"{celeb['name']} subió un nuevo {label}"
            notif = Notification(
                celebrity_id=celeb_id,
                celebrity_name=celeb["name"],
                celebrity_color=celeb["color"],
                type=notif_type,
                title=notif_title,
                message=v["title"],
                link=v["url"],
                image_url=v["thumbnail_url"],
                created_at=v["published_at"],
            )
            await db.notifications.insert_one(notif.model_dump())
    return all_new


@api_router.get("/celebrities/{celeb_id}/videos")
async def get_celebrity_videos(celeb_id: str, kind: str = "video", sort: str = "recent", refresh: bool = False):
    """
    kind: 'video' (long) or 'short'
    sort: 'recent' | 'viral' (by view count)
    """
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    has_channels = celeb.get("youtube_channel_id") or celeb.get("secondary_channels")
    is_short = kind == "short"
    if refresh and has_channels:
        asyncio.create_task(refresh_celebrity_videos(celeb_id))
        # Also reset viral cache so "Más virales" re-scans whole channel
        await db.viral_cache.delete_many({"celebrity_id": celeb_id})
    # If the current kind has too few videos from older limited scans, do one deep scan.
    count = await db.videos.count_documents({"celebrity_id": celeb_id, "is_short": is_short})
    scan_state = await db.video_refresh_state.find_one({"_key": f"{celeb_id}:uploads"}, {"_id": 0})
    should_deep_scan = (
        has_channels and
        count < MIN_RESULTS_PER_SECTION and
        (not scan_state or scan_state.get("scan_limit", 0) < RECENT_UPLOAD_SCAN_LIMIT)
    )
    if should_deep_scan and not refresh:
        await refresh_celebrity_videos(celeb_id, notify=False)
    query = {"celebrity_id": celeb_id, "is_short": is_short}
    sort_key = "view_count" if sort == "viral" else "published_at"
    raw = await db.videos.find(query, {"_id": 0}).sort(sort_key, -1).to_list(VIDEO_RESPONSE_LIMIT * 2)
    seen = set()
    videos = []
    for v in raw:
        vid = v.get("video_id")
        if vid and vid not in seen:
            seen.add(vid)
            videos.append(v)
    return {"videos": videos[:VIDEO_RESPONSE_LIMIT]}


@api_router.post("/celebrities/{celeb_id}/secondary-channels")
async def add_secondary_channel(celeb_id: str, payload: SecondaryChannelAdd):
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    info = await fetch_channel_info(payload.youtube_channel_id)
    if not info:
        raise HTTPException(status_code=400, detail="Canal de YouTube no encontrado")
    if any(sc["channel_id"] == info["channel_id"] for sc in celeb.get("secondary_channels", [])):
        raise HTTPException(status_code=400, detail="Canal ya agregado")
    if celeb.get("youtube_channel_id") == info["channel_id"]:
        raise HTTPException(status_code=400, detail="Es el canal principal")
    new_channel = {
        "channel_id": info["channel_id"],
        "title": info["title"],
        "thumbnail": info["thumbnail"],
    }
    await db.celebrities.update_one(
        {"id": celeb_id},
        {"$push": {"secondary_channels": new_channel}},
    )
    asyncio.create_task(refresh_celebrity_videos(celeb_id, info["channel_id"], notify=False))
    return {"ok": True, "channel": new_channel}


@api_router.delete("/celebrities/{celeb_id}/secondary-channels/{channel_id}")
async def remove_secondary_channel(celeb_id: str, channel_id: str):
    await db.celebrities.update_one(
        {"id": celeb_id},
        {"$pull": {"secondary_channels": {"channel_id": channel_id}}},
    )
    await db.videos.delete_many({"celebrity_id": celeb_id, "channel_id": channel_id})
    return {"ok": True}


@api_router.put("/celebrities/{celeb_id}/trending-context")
async def update_trending_context(celeb_id: str, payload: TrendingContextUpdate):
    res = await db.celebrities.update_one(
        {"id": celeb_id},
        {"$set": {"trending_context": payload.trending_context}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    return {"ok": True}


# ===== MODELO HÍBRIDO DE RECOMENDACIONES =====
#
# 30 videos divididos en 3 categorías de 10:
#   CATEGORÍA A – Recientes con potencial (últimos videos + buenas stats)
#   CATEGORÍA B – Virales históricos (los más vistos de todo el canal)
#   CATEGORÍA C – Tendencias (videos cuyo tema coincide con lo que está pasando HOY)
#
# El algoritmo ordena cada categoría. La IA solo redacta razones.
# ===============================================================

import math as _math

def _tokenize(text: str) -> set:
    import re as _re
    return set(_re.sub(r"[^\w\s]", " ", text.lower()).split())

def _extract_trend_keywords(trending_context: str) -> list:
    if not trending_context:
        return []
    import re as _re
    parts = _re.split(r"[,\n;.]", trending_context)
    return [p.strip() for p in parts if len(p.strip()) >= 3]

def _matches_trends(video: dict, trend_keywords: list) -> float:
    """Returns 0-1 score of how well a video matches trend keywords."""
    if not trend_keywords:
        return 0.0
    haystack = (video.get("title", "") + " " + video.get("description", "")[:300]).lower()
    hits = sum(1 for kw in trend_keywords if kw.lower() in haystack)
    return min(1.0, hits / max(len(trend_keywords), 1) * 3)

def _recency_score(video: dict) -> float:
    """Score based purely on how recent the video is (0-1)."""
    try:
        pub = video.get("published_at", "")
        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        days_old = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400
        return max(0.0, 1.0 - (days_old / 90))  # 0 days=1.0, 90 days=0.0
    except Exception:
        return 0.0

def _potential_score(video: dict, channel_subs: int) -> float:
    """Score for recent videos with growth potential (0-1)."""
    views = max(int(video.get("view_count", 0)), 0)
    likes = max(int(video.get("like_count", 0)), 0)
    comments = max(int(video.get("comment_count", 0)), 0)
    subs = max(int(channel_subs or 1), 1)
    try:
        pub = video.get("published_at", "")
        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        days_old = max((datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400, 0.5)
    except Exception:
        days_old = 30
    velocity = views / days_old
    reach = views / subs
    eng = (likes + comments * 3) / max(views, 1)
    # Combine velocity + engagement + reach, normalize to 0-1
    v_score = min(1.0, _math.log10(max(velocity, 1)) / 5)
    e_score = min(1.0, eng * 20)
    r_score = min(1.0, _math.log10(max(reach * 100, 1)) / 4)
    return (v_score * 0.5 + e_score * 0.3 + r_score * 0.2)


async def expand_keywords_with_ai(keywords: list, celebrity_name: str) -> list:
    """
    Usa LLaMA via Groq para expandir keywords con sinónimos, variantes y términos
    relacionados en contexto de medios y entretenimiento LATAM. Si falla, devuelve
    keywords originales.
    """
    if not keywords:
        return []
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return keywords

    try:
        groq_client = Groq(api_key=api_key)
        keywords_str = ", ".join(keywords)
        prompt = (
            f"Contexto: canal de YouTube de {celebrity_name} en México/LATAM.\n"
            f"Keywords del usuario: {keywords_str}\n\n"
            f"Tarea: Para cada keyword genera 5-8 sinónimos, variantes, términos relacionados "
            f"y palabras que frecuentemente aparecen en títulos de YouTube sobre ese tema en español LATAM. "
            f"Incluye variantes con/sin acento, abreviaciones, nombres propios relevantes.\n\n"
            f"Responde SOLO con JSON válido, sin markdown:\n"
            f'[["keyword_original", "sinonimo1", "sinonimo2"], ...]'
        )
        msg = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        # Try to find the JSON array in case the model wraps it
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            raw = match.group(0)
        expanded_groups = json.loads(raw)
        all_terms = list(keywords)
        for group in expanded_groups:
            if isinstance(group, list):
                for t in group:
                    if isinstance(t, str) and len(t.strip()) >= 2:
                        all_terms.append(t.lower().strip())
        # Deduplicate preserving order
        seen = set()
        deduped = []
        for t in all_terms:
            tl = t.lower().strip()
            if tl and tl not in seen:
                seen.add(tl)
                deduped.append(tl)
        return deduped
    except Exception as e:
        logging.warning(f"Keyword expansion failed, using originals: {e}")
        return keywords


@api_router.post("/celebrities/{celeb_id}/recommendations")
async def get_hybrid_recommendations(celeb_id: str, kind: str = "video"):
    """
    30 recomendaciones en 3 categorías de 10:
    - CAT A: 10 videos recientes con potencial
    - CAT B: 10 virales históricos del canal
    - CAT C: 10 por tendencias (tema coincide con contexto trending)
    """
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")

    is_short = kind == "short"
    trending_context = celeb.get("trending_context", "").strip()
    trend_keywords_raw = _extract_trend_keywords(trending_context)
    if trend_keywords_raw and os.environ.get("GROQ_API_KEY"):
        trend_keywords = await expand_keywords_with_ai(trend_keywords_raw, celeb["name"])
    else:
        trend_keywords = trend_keywords_raw
    channel_subs = celeb.get("subscriber_count", 1)

    # --- Obtener todos los videos disponibles ---
    all_recent = await db.videos.find(
        {"celebrity_id": celeb_id, "is_short": is_short}, {"_id": 0}
    ).sort("published_at", -1).to_list(200)

    viral_cache = await db.viral_cache.find_one({"_key": f"{celeb_id}:{kind}"}, {"_id": 0})
    viral_videos = viral_cache.get("videos", []) if viral_cache else []

    # Pool completo sin duplicados
    seen_ids = set()
    all_videos = []
    for v in all_recent + viral_videos:
        if v["video_id"] not in seen_ids:
            seen_ids.add(v["video_id"])
            all_videos.append(v)

    if not all_videos:
        return {"recommendations": [], "categories": {}, "strategy": "No hay videos para analizar."}

    # --- CATEGORÍA A: Recientes con potencial ---
    # Solo videos de los últimos 90 días, ordenados por potencial
    recent_pool = [v for v in all_videos if _recency_score(v) > 0.05]
    recent_pool.sort(key=lambda v: _potential_score(v, channel_subs) * 0.6 + _recency_score(v) * 0.4, reverse=True)
    cat_a = recent_pool[:10]
    cat_a_ids = {v["video_id"] for v in cat_a}

    # --- CATEGORÍA B: Virales históricos ---
    # Los más vistos de todo el canal, excluyendo los ya en cat_a
    historical_pool = sorted(all_videos, key=lambda v: v.get("view_count", 0), reverse=True)
    cat_b = [v for v in historical_pool if v["video_id"] not in cat_a_ids][:10]
    cat_b_ids = {v["video_id"] for v in cat_b}

    # --- CATEGORÍA C: Por tendencias ---
    # Videos cuyo título/descripción conecta con las tendencias actuales
    # Incluye videos viejos que "resurgen" por el tema (efecto BTS/Franco)
    excluded_ids = cat_a_ids | cat_b_ids
    if trend_keywords:
        trend_pool = [v for v in all_videos if v["video_id"] not in excluded_ids]
        trend_pool.sort(key=lambda v: _matches_trends(v, trend_keywords) * 0.7 + _potential_score(v, channel_subs) * 0.3, reverse=True)
        cat_c = [v for v in trend_pool if _matches_trends(v, trend_keywords) > 0][:10]
        # Si no hay suficientes con match, completar con los de mayor potencial restantes
        if len(cat_c) < 10:
            remaining = [v for v in trend_pool if v not in cat_c]
            cat_c += remaining[:10 - len(cat_c)]
    else:
        # Sin tendencias definidas, usar los de mayor engagement relativo
        trend_pool = sorted(
            [v for v in all_videos if v["video_id"] not in excluded_ids],
            key=lambda v: _potential_score(v, channel_subs), reverse=True
        )
        cat_c = trend_pool[:10]

    # --- Llamar a IA para redactar razones (no decide el ranking) ---
    api_key = os.environ.get("GROQ_API_KEY")
    ai_reasons = {}
    overall_strategy = ""

    if api_key:
        def _fmt(v, cat_label):
            return f"[{cat_label}][id:{v['video_id']}] \"{v['title']}\" · {v.get('view_count',0):,} vistas · {v['published_at'][:10]}"

        candidates_txt = "\n".join(
            [_fmt(v, "RECIENTE") for v in cat_a] +
            [_fmt(v, "VIRAL_HISTORICO") for v in cat_b] +
            [_fmt(v, "TENDENCIA") for v in cat_c]
        )
        kind_label = "Shorts" if is_short else "videos largos"
        system_msg = (
            "Eres experto en marketing digital latinoamericano. "
            "Te doy 30 videos YA CATEGORIZADOS por un algoritmo. "
            "Tu trabajo: escribir una razón corta (1-2 frases) y una predicción para cada uno. "
            "Responde SOLO JSON válido, sin markdown."
        )
        user_text = (
            f"Personaje: {celeb['name']} | Tipo: {kind_label}\n"
            f"Tendencias: {trending_context or '(México/LATAM en general)'}\n\n"
            f"VIDEOS (30 en total, 3 categorías):\n{candidates_txt}\n\n"
            f"Devuelve JSON:\n"
            f'{{"reasons":[{{"video_id":"...","reason":"...","prediction":"..."}}],"overall_strategy":"..."}}\n'
            f"Una entrada por video_id."
        )
        try:
            groq_client = Groq(api_key=api_key)
            msg = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=3000,
                messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_text}]
            )
            raw = msg.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                for r in parsed.get("reasons", []):
                    ai_reasons[r.get("video_id", "")] = r
                overall_strategy = parsed.get("overall_strategy", "")
        except Exception as e:
            logging.warning(f"IA reasons failed (algorithm still works): {e}")

    # --- Construir respuesta final ---
    def _build(videos, category_label, category_key):
        result = []
        for v in videos:
            exp = ai_reasons.get(v["video_id"], {})
            result.append({
                "video_id": v["video_id"],
                "category": category_key,
                "category_label": category_label,
                "reason": exp.get("reason", ""),
                "prediction": exp.get("prediction", ""),
                "trend_match": ", ".join(trend_keywords[:3]) if category_key == "trend" and trend_keywords else "—",
                "video": v,
            })
        return result

    recommendations = (
        _build(cat_a, "🔴 Reciente con potencial", "recent") +
        _build(cat_b, "🟡 Viral histórico del canal", "viral") +
        _build(cat_c, "🟢 Por tendencias / resurrección", "trend")
    )

    return {
        "recommendations": recommendations,
        "strategy": overall_strategy,
        "trend_keywords_used": trend_keywords_raw,
        "trend_keywords_expanded": trend_keywords[:20],
        "counts": {"recent": len(cat_a), "viral": len(cat_b), "trend": len(cat_c)},
        "model": "hybrid_v3_semantic",
    }


# ===== Google News scraping =====
@api_router.get("/celebrities/{celeb_id}/news")
async def get_celebrity_news(celeb_id: str, refresh: bool = False):
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    # cache: refresh if older than 1 hour or no entries
    cache = await db.news_cache.find_one({"celebrity_id": celeb_id}, {"_id": 0})
    needs_refresh = refresh or not cache
    if cache and not refresh:
        fetched = datetime.fromisoformat(cache["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
        if age > 3600:
            needs_refresh = True
    if needs_refresh:
        items = await fetch_google_news(celeb["name"])
        await db.news_cache.update_one(
            {"celebrity_id": celeb_id},
            {"$set": {
                "celebrity_id": celeb_id,
                "items": items,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        return {"news": items, "cached": False}
    return {"news": cache.get("items", []), "cached": True}


async def fetch_google_news(query: str, max_items: int = 20):
    try:
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=es-419&gl=MX&ceid=MX:es-419"
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}))
        feed = feedparser.parse(resp.text)
        items = []
        for entry in feed.entries[:max_items]:
            source = ""
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source = entry.source.title
            elif " - " in entry.title:
                source = entry.title.rsplit(" - ", 1)[-1]
            # Strip source from title
            clean_title = entry.title
            if source and clean_title.endswith(f" - {source}"):
                clean_title = clean_title[:-len(f" - {source}")]
            items.append({
                "title": clean_title,
                "link": entry.link,
                "source": source,
                "published": entry.get("published", ""),
                "summary": re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:300],
            })
        return items
    except Exception as e:
        logging.error(f"Google News fetch error: {e}")
        return []


async def refresh_viral_cache_for_celebrity(celeb: dict, kind: str = "video"):
    celeb_id = celeb["id"]
    is_short = kind == "short"
    cache_key = f"{celeb_id}:{kind}"
    channels = []
    if celeb.get("youtube_channel_id"):
        channels.append(celeb["youtube_channel_id"])
    for sc in celeb.get("secondary_channels", []):
        channels.append(sc["channel_id"])

    all_top = []
    loop = asyncio.get_event_loop()
    for ch_id in channels:
        vids = await loop.run_in_executor(
            None,
            lambda c=ch_id: fetch_top_viewed_from_channel(c, max_results=VIRAL_CHANNEL_SCAN_LIMIT),
        )
        all_top.extend(vids)

    channel_subs = celeb.get("subscriber_count", 1)
    for v in all_top:
        v["celebrity_id"] = celeb_id
        v["viral_score"] = compute_viral_score(v, channel_subs)

    seen = set()
    filtered = []
    for v in sorted(all_top, key=lambda x: x.get("view_count", 0), reverse=True):
        if v["video_id"] in seen:
            continue
        if v["is_short"] != is_short:
            continue
        seen.add(v["video_id"])
        filtered.append(v)

    filtered = filtered[:VIDEO_RESPONSE_LIMIT]
    await db.viral_cache.update_one(
        {"_key": cache_key},
        {"$set": {
            "_key": cache_key,
            "celebrity_id": celeb_id,
            "kind": kind,
            "videos": filtered,
            "scan_limit": VIRAL_CHANNEL_SCAN_LIMIT,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return filtered


@api_router.get("/celebrities/{celeb_id}/viral-videos")
async def get_viral_videos(celeb_id: str, kind: str = "video", refresh: bool = False):
    """All-time top viewed videos/shorts across the WHOLE channel(s) via YouTube search order=viewCount."""
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    is_short = kind == "short"
    cache_key = f"{celeb_id}:{kind}"
    cache = await db.viral_cache.find_one({"_key": cache_key}, {"_id": 0})
    needs_refresh = refresh or not cache
    if cache and not refresh:
        try:
            fetched = datetime.fromisoformat(cache["fetched_at"])
            # Refresh every 6 hours
            if (datetime.now(timezone.utc) - fetched).total_seconds() > 21600:
                needs_refresh = True
            if (
                len(cache.get("videos", [])) < MIN_RESULTS_PER_SECTION and
                cache.get("scan_limit", 0) < VIRAL_CHANNEL_SCAN_LIMIT
            ):
                needs_refresh = True
        except Exception:
            needs_refresh = True
    if needs_refresh:
        asyncio.create_task(refresh_viral_cache_for_celebrity(celeb, kind))
        fallback = cache.get("videos", []) if cache else []
        if not fallback:
            raw = await db.videos.find(
                {"celebrity_id": celeb_id, "is_short": is_short}, {"_id": 0}
            ).sort("view_count", -1).to_list(VIDEO_RESPONSE_LIMIT * 2)
            seen = set()
            fallback = []
            for v in raw:
                vid = v.get("video_id")
                if vid and vid not in seen:
                    seen.add(vid)
                    fallback.append(v)
            fallback = fallback[:VIDEO_RESPONSE_LIMIT]
        return {"videos": fallback, "refreshing": True}
    return {"videos": cache.get("videos", [])}


@api_router.get("/celebrities/{celeb_id}/videos/{video_id}/clips")
async def get_video_clips(celeb_id: str, video_id: str):
    """Detect viral clip segments from video chapters in description. Free, no API."""
    video = await db.videos.find_one(
        {"celebrity_id": celeb_id, "video_id": video_id}, {"_id": 0},
    )
    if not video:
        viral_caches = await db.viral_cache.find({"celebrity_id": celeb_id}, {"_id": 0}).to_list(10)
        for cache in viral_caches:
            for cached_video in cache.get("videos", []):
                if cached_video.get("video_id") == video_id:
                    video = cached_video
                    break
            if video:
                break
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    chapters = parse_chapters(video.get("description", ""), video.get("duration_seconds", 0))
    if not chapters:
        return {
            "video_id": video_id,
            "video_title": video.get("title"),
            "chapters": [],
            "clips": [],
            "message": "Este video no tiene capítulos/timestamps en la descripción. No se pueden detectar clips automáticamente.",
        }
    scored = []
    for c in chapters:
        c_copy = dict(c)
        c_copy["clip_score"] = score_chapter_for_clip(c)
        # build link with timestamp
        c_copy["link"] = f"https://www.youtube.com/watch?v={video_id}&t={c['start']}s"
        scored.append(c_copy)
    # top suggested clips (sorted by score, take top 10)
    clips = sorted(scored, key=lambda x: x["clip_score"], reverse=True)[:10]
    return {
        "video_id": video_id,
        "video_title": video.get("title"),
        "video_url": video.get("url"),
        "chapters": scored,
        "clips": clips,
    }


# ===== Routes: Virals =====
@api_router.get("/celebrities/{celeb_id}/virals")
async def list_virals(celeb_id: str):
    items = await db.virals.find({"celebrity_id": celeb_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"virals": items}


@api_router.post("/celebrities/{celeb_id}/virals", response_model=ViralEntry)
async def add_viral(celeb_id: str, payload: ViralCreate):
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    entry = ViralEntry(celebrity_id=celeb_id, **payload.model_dump())
    await db.virals.insert_one(entry.model_dump())
    # Create notification
    notif = Notification(
        celebrity_id=celeb_id,
        celebrity_name=celeb["name"],
        celebrity_color=celeb["color"],
        type=payload.tag,
        title=f"{celeb['name']}: nuevo {payload.tag}",
        message=payload.title,
        link=payload.source_url,
        image_url=payload.image_url,
    )
    await db.notifications.insert_one(notif.model_dump())
    return entry


@api_router.delete("/virals/{viral_id}")
async def delete_viral(viral_id: str):
    res = await db.virals.delete_one({"id": viral_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ===== Routes: Notifications =====
@api_router.get("/notifications")
async def list_notifications():
    items = await db.notifications.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = sum(1 for i in items if not i.get("read"))
    return {"notifications": items, "unread": unread}


@api_router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str):
    await db.notifications.update_one({"id": notif_id}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_read():
    await db.notifications.update_many({"read": False}, {"$set": {"read": True}})
    return {"ok": True}


# ===== Routes: Contacts =====
@api_router.post("/contacts", response_model=ContactSubscription)
async def add_contact(payload: ContactCreate):
    sub = ContactSubscription(**payload.model_dump())
    await db.contacts.insert_one(sub.model_dump())
    return sub


@api_router.get("/contacts/{celeb_id}")
async def list_contacts(celeb_id: str):
    items = await db.contacts.find({"celebrity_id": celeb_id}, {"_id": 0}).to_list(100)
    return {"contacts": items}


# ===== Routes: Refresh all =====
@api_router.post("/refresh-all")
async def refresh_all():
    celebs = await db.celebrities.find({}, {"_id": 0}).to_list(200)
    async def _refresh_in_background(items):
        for c in items:
            if c.get("youtube_channel_id") or c.get("secondary_channels"):
                await refresh_celebrity_videos(c["id"], notify=True)
                # Also reset viral cache so next load re-scans the whole channel
                await db.viral_cache.delete_many({"celebrity_id": c["id"]})

    asyncio.create_task(_refresh_in_background(celebs))
    return {"ok": True, "started": True, "queued": len(celebs)}


@api_router.post("/refresh-all-sync")
async def refresh_all_sync():
    celebs = await db.celebrities.find({}, {"_id": 0}).to_list(200)
    for c in celebs:
        if c.get("youtube_channel_id") or c.get("secondary_channels"):
            await refresh_celebrity_videos(c["id"], notify=True)
            # Also reset viral cache so next load re-scans the whole channel
            await db.viral_cache.delete_many({"celebrity_id": c["id"]})
    return {"ok": True, "refreshed": len(celebs)}


@api_router.get("/")
async def root():
    return {"message": "CelebTracker API", "ok": True}


# ===== App setup =====
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    try:
        await seed_celebrities()
        # Initial video fetch for all
        celebs = await db.celebrities.find({}, {"_id": 0}).to_list(200)
        for c in celebs:
            if c.get("youtube_channel_id"):
                existing = await db.videos.count_documents({"celebrity_id": c["id"]})
                if existing == 0:
                    asyncio.create_task(refresh_celebrity_videos(c["id"], notify=False))
    except Exception as e:
        logger.error(f"Startup error: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
