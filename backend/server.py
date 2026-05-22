from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')

app = FastAPI(title="CelebTracker API")
api_router = APIRouter(prefix="/api")


# ===== Models =====
class Celebrity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    color: str  # hex like #007AFF
    image_url: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    youtube_channel_handle: Optional[str] = None
    subscriber_count: int = 0
    video_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CelebrityCreate(BaseModel):
    name: str
    color: str
    youtube_channel_id: str
    image_url: Optional[str] = None


class CelebrityVideo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    celebrity_id: str
    video_id: str
    title: str
    description: str
    thumbnail_url: str
    published_at: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration: Optional[str] = None
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


async def fetch_latest_videos(channel_id: str, max_results: int = 12):
    """Fetch latest videos from a channel using the uploads playlist (cheaper than search)."""
    try:
        yt = yt_service()
        ch_resp = yt.channels().list(part="contentDetails", id=channel_id).execute()
        items = ch_resp.get("items", [])
        if not items:
            return []
        uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        pl_resp = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=max_results,
        ).execute()
        video_ids = [it["contentDetails"]["videoId"] for it in pl_resp.get("items", [])]
        if not video_ids:
            return []
        vids_resp = yt.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()
        results = []
        for v in vids_resp.get("items", []):
            results.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "description": v["snippet"].get("description", "")[:500],
                "thumbnail_url": v["snippet"]["thumbnails"].get("high", v["snippet"]["thumbnails"]["default"])["url"],
                "published_at": v["snippet"]["publishedAt"],
                "view_count": int(v["statistics"].get("viewCount", 0)),
                "like_count": int(v["statistics"].get("likeCount", 0)),
                "comment_count": int(v["statistics"].get("commentCount", 0)),
                "duration": v["contentDetails"].get("duration"),
                "url": f"https://www.youtube.com/watch?v={v['id']}",
            })
        return results
    except HttpError as e:
        logging.error(f"YouTube fetch_latest_videos error: {e}")
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
    # fetch initial videos in background-ish (await but small)
    asyncio.create_task(refresh_celebrity_videos(celeb.id, payload.youtube_channel_id, notify=False))
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
async def refresh_celebrity_videos(celeb_id: str, channel_id: str, notify: bool = True):
    videos = await fetch_latest_videos(channel_id, max_results=12)
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb or not videos:
        return []
    # Find new videos (not in DB)
    existing_ids = set()
    async for v in db.videos.find({"celebrity_id": celeb_id}, {"_id": 0, "video_id": 1}):
        existing_ids.add(v["video_id"])
    new_videos = [v for v in videos if v["video_id"] not in existing_ids]
    # Upsert all videos (to refresh stats)
    for v in videos:
        doc = CelebrityVideo(celebrity_id=celeb_id, **v).model_dump()
        await db.videos.update_one(
            {"celebrity_id": celeb_id, "video_id": v["video_id"]},
            {"$set": doc},
            upsert=True,
        )
    # Create notifications for new videos
    if notify and existing_ids:  # only notify if we had previous data
        for v in new_videos:
            notif = Notification(
                celebrity_id=celeb_id,
                celebrity_name=celeb["name"],
                celebrity_color=celeb["color"],
                type="new_video",
                title=f"{celeb['name']} subió un nuevo video",
                message=v["title"],
                link=v["url"],
                image_url=v["thumbnail_url"],
            )
            await db.notifications.insert_one(notif.model_dump())
    return videos


@api_router.get("/celebrities/{celeb_id}/videos")
async def get_celebrity_videos(celeb_id: str, refresh: bool = False):
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    if refresh and celeb.get("youtube_channel_id"):
        await refresh_celebrity_videos(celeb_id, celeb["youtube_channel_id"])
    videos = await db.videos.find({"celebrity_id": celeb_id}, {"_id": 0}).sort("published_at", -1).to_list(50)
    # if no videos and we have channel id, fetch now
    if not videos and celeb.get("youtube_channel_id"):
        await refresh_celebrity_videos(celeb_id, celeb["youtube_channel_id"], notify=False)
        videos = await db.videos.find({"celebrity_id": celeb_id}, {"_id": 0}).sort("published_at", -1).to_list(50)
    return {"videos": videos}


@api_router.get("/celebrities/{celeb_id}/viral-videos")
async def get_viral_videos(celeb_id: str):
    """Top 10 videos by view count from this celebrity's channel."""
    videos = await db.videos.find({"celebrity_id": celeb_id}, {"_id": 0}).sort("view_count", -1).to_list(10)
    return {"videos": videos}


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
    total_new = 0
    for c in celebs:
        if c.get("youtube_channel_id"):
            await refresh_celebrity_videos(c["id"], c["youtube_channel_id"], notify=True)
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
                    asyncio.create_task(refresh_celebrity_videos(c["id"], c["youtube_channel_id"], notify=False))
    except Exception as e:
        logger.error(f"Startup error: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
