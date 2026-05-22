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
from emergentintegrations.llm.chat import LlmChat, UserMessage


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

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


async def fetch_latest_videos(channel_id: str, max_results: int = 30):
    """Fetch latest videos from a channel using the uploads playlist."""
    try:
        yt = yt_service()
        ch_resp = yt.channels().list(part="contentDetails,snippet", id=channel_id).execute()
        items = ch_resp.get("items", [])
        if not items:
            return []
        channel_title = items[0]["snippet"]["title"]
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
        videos = await fetch_latest_videos(ch_id, max_results=30)
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
    if notify and had_previous:
        for v in all_new:
            label = "short" if v["is_short"] else "video"
            notif = Notification(
                celebrity_id=celeb_id,
                celebrity_name=celeb["name"],
                celebrity_color=celeb["color"],
                type="new_video",
                title=f"{celeb['name']} subió un nuevo {label}",
                message=v["title"],
                link=v["url"],
                image_url=v["thumbnail_url"],
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
    if refresh and has_channels:
        await refresh_celebrity_videos(celeb_id)
    # If no videos, fetch now
    count = await db.videos.count_documents({"celebrity_id": celeb_id})
    if count == 0 and has_channels:
        await refresh_celebrity_videos(celeb_id, notify=False)
    is_short = kind == "short"
    query = {"celebrity_id": celeb_id, "is_short": is_short}
    sort_key = "view_count" if sort == "viral" else "published_at"
    videos = await db.videos.find(query, {"_id": 0}).sort(sort_key, -1).to_list(50)
    return {"videos": videos}


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


# ===== AI Recommendations =====
@api_router.post("/celebrities/{celeb_id}/recommendations")
async def get_ai_recommendations(celeb_id: str, kind: str = "video"):
    """Use Claude Sonnet 4.5 to recommend which videos to upload to Facebook."""
    celeb = await db.celebrities.find_one({"id": celeb_id}, {"_id": 0})
    if not celeb:
        raise HTTPException(status_code=404, detail="Celebrity not found")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")
    is_short = kind == "short"
    videos = await db.videos.find(
        {"celebrity_id": celeb_id, "is_short": is_short},
        {"_id": 0},
    ).sort("published_at", -1).to_list(40)
    if not videos:
        return {"recommendations": [], "reasoning": "No hay videos para analizar."}
    trending_context = celeb.get("trending_context", "").strip()
    # Build prompt
    videos_list = "\n".join([
        f"{i+1}. [id:{v['video_id']}] \"{v['title']}\" · {v['view_count']:,} views · {v['published_at'][:10]}"
        for i, v in enumerate(videos[:30])
    ])
    kind_label = "Shorts (videos cortos verticales)" if is_short else "videos largos / podcasts"
    system_msg = (
        "Eres un experto en marketing de redes sociales latinoamericanas trabajando para Meta Business. "
        "Analizas contenido de YouTube de personajes latinos y recomiendas qué subir a Facebook AHORA mismo "
        "para maximizar engagement. Considera: temas trending en Latinoamérica/México, controversia, "
        "humor cultural, relevancia actual (política, farándula, virales), y potencial de viralidad en Facebook. "
        "Respondes SIEMPRE en JSON válido."
    )
    user_text = (
        f"Personaje: {celeb['name']}\n"
        f"Tipo de contenido a recomendar: {kind_label}\n\n"
        f"TEMAS TRENDING ACTUALES (proporcionados por el community manager):\n"
        f"{trending_context if trending_context else '(no especificados - usa tu conocimiento general de tendencias actuales)'}\n\n"
        f"LISTA DE VIDEOS DISPONIBLES (más recientes primero):\n{videos_list}\n\n"
        f"Devuelve un JSON con esta estructura EXACTA (sin markdown, solo JSON puro):\n"
        f'{{"recommendations": [{{"video_id": "...", "score": 0-100, "reason": "razón breve en español (1-2 frases)"}}], "overall_strategy": "estrategia general 2-3 frases"}}\n'
        f"Selecciona los TOP 5 más recomendados, ordenados por score descendente. Sé crítico y específico."
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"reco-{celeb_id}-{uuid.uuid4().hex[:8]}",
            system_message=system_msg,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        response = await chat.send_message(UserMessage(text=user_text))
        # Parse JSON from response
        text = response.strip()
        # try to find json
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = {"recommendations": [], "overall_strategy": text[:300]}
        # Attach video details
        video_map = {v["video_id"]: v for v in videos}
        enriched = []
        for r in data.get("recommendations", []):
            vid = video_map.get(r.get("video_id"))
            if vid:
                enriched.append({**r, "video": vid})
        return {"recommendations": enriched, "strategy": data.get("overall_strategy", "")}
    except Exception as e:
        logging.error(f"AI recommendation error: {e}")
        raise HTTPException(status_code=500, detail=f"Error en IA: {str(e)}")


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


@api_router.get("/celebrities/{celeb_id}/viral-videos")
async def get_viral_videos(celeb_id: str, kind: str = "video"):
    """Top 10 videos/shorts by view count from this celebrity's channels."""
    is_short = kind == "short"
    videos = await db.videos.find(
        {"celebrity_id": celeb_id, "is_short": is_short}, {"_id": 0},
    ).sort("view_count", -1).to_list(10)
    return {"videos": videos}


@api_router.get("/celebrities/{celeb_id}/videos/{video_id}/clips")
async def get_video_clips(celeb_id: str, video_id: str):
    """Detect viral clip segments from video chapters in description. Free, no API."""
    video = await db.videos.find_one(
        {"celebrity_id": celeb_id, "video_id": video_id}, {"_id": 0},
    )
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
    for c in celebs:
        if c.get("youtube_channel_id") or c.get("secondary_channels"):
            await refresh_celebrity_videos(c["id"], notify=True)
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
