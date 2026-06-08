import React, { useState, useEffect, useCallback } from "react";
import { api, fmtNumber, timeAgo } from "@/lib/api";
import { Play, Eye, ThumbsUp, MessageCircle, Sparkles, Loader2, Settings2, Flame, Scissors, ExternalLink } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";

// Detectar timestamps en descripción para saber si el video tiene chapters
const TIMESTAMP_RE = /(?:^|\s)(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—:]?\s*([^\n]{3,80})/gm;
const countChapters = (description) => {
    if (!description) return 0;
    const matches = description.match(TIMESTAMP_RE);
    return matches ? matches.length : 0;
};

// Deduplicar array de videos por video_id
const dedup = (arr) => {
    const seen = new Set();
    return (arr || []).filter(v => {
        if (seen.has(v.video_id)) return false;
        seen.add(v.video_id);
        return true;
    });
};

const VideoSection = ({ celebrity, kind, refreshSignal = 0, onCelebrityUpdate }) => {
    const [recent, setRecent] = useState([]);
    const [viral, setViral] = useState([]);
    const [loading, setLoading] = useState(true);
    const [recommendations, setRecommendations] = useState(null);
    const [recoLoading, setRecoLoading] = useState(false);
    const [contextOpen, setContextOpen] = useState(false);
    const [contextDraft, setContextDraft] = useState(celebrity.trending_context || "");
    const [clipsModal, setClipsModal] = useState(null);
    const [clipsLoading, setClipsLoading] = useState(false);

    const handleShowClips = async (video) => {
        setClipsModal({ video, data: null });
        setClipsLoading(true);
        try {
            const res = await api.get(`/celebrities/${celebrity.id}/videos/${video.video_id}/clips`);
            setClipsModal({ video, data: res.data });
        } catch (e) {
            toast.error("Error al detectar clips");
            setClipsModal(null);
        } finally {
            setClipsLoading(false);
        }
    };

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [r, v] = await Promise.all([
                api.get(`/celebrities/${celebrity.id}/videos`, { params: { kind, sort: "recent" } }),
                api.get(`/celebrities/${celebrity.id}/viral-videos`, { params: { kind } }),
            ]);
            setRecent(dedup(r.data.videos));
            setViral(dedup(v.data.videos));
        } catch (e) {
            toast.error("Error al cargar videos");
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [celebrity.id, kind]);

    useEffect(() => { load(); }, [load, refreshSignal]);

    const fetchRecommendations = async () => {
        setRecoLoading(true);
        try {
            const res = await api.post(`/celebrities/${celebrity.id}/recommendations?kind=${kind}`);
            setRecommendations(res.data);
        } catch (e) {
            toast.error("Error con la IA. Reintenta.");
            console.error(e);
        } finally {
            setRecoLoading(false);
        }
    };

    const saveContext = async () => {
        await api.put(`/celebrities/${celebrity.id}/trending-context`, { trending_context: contextDraft });
        toast.success("Contexto guardado");
        setContextOpen(false);
        onCelebrityUpdate?.();
        // Auto-refresh recommendations
        if (recommendations) fetchRecommendations();
    };

    const label = kind === "short" ? "Shorts" : "Videos";

    return (
        <div>
            <Tabs defaultValue="recent" className="w-full">
                <TabsList className="bg-[#111113] border border-white/10 p-1 h-auto" data-testid={`${kind}-subtabs`}>
                    <TabsTrigger value="recent" data-testid={`${kind}-tab-recent`} className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 text-sm">
                        Más recientes
                    </TabsTrigger>
                    <TabsTrigger value="viral" data-testid={`${kind}-tab-viral`} className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 text-sm">
                        Más virales del canal
                    </TabsTrigger>
                    <TabsTrigger value="reco" data-testid={`${kind}-tab-reco`} className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 text-sm flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" /> Recomendados Facebook
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="recent" className="mt-5">
                    <Grid videos={recent} kind={kind} loading={loading} label="Más recientes" onShowClips={handleShowClips} />
                </TabsContent>

                <TabsContent value="viral" className="mt-5">
                    <Grid videos={viral} kind={kind} loading={loading} label="Más virales del canal" onShowClips={handleShowClips} />
                </TabsContent>

                <TabsContent value="reco" className="mt-5">
                    <div className="rounded-xl bg-[#111113] border border-white/10 p-5 mb-5">
                        <div className="flex items-start justify-between gap-4 flex-wrap">
                            <div className="flex-1 min-w-0">
                                <h3 className="font-display text-lg font-bold flex items-center gap-2">
                                    <Sparkles className="w-4 h-4 celeb-text" />
                                    IA · {label} recomendados para Facebook
                                </h3>
                                <p className="text-sm text-white/50 mt-1 leading-relaxed">
                                    Modelo híbrido: algoritmo propio de scoring + IA. El ranking lo decide el algoritmo (viral, tendencias, resurrección). Score máximo: 30 pts.
                                </p>
                                {celebrity.trending_context && (
                                    <div className="mt-3 p-3 rounded-lg bg-black/40 border border-white/5">
                                        <p className="text-[10px] uppercase tracking-widest text-white/40 font-bold mb-1">Tu contexto trending</p>
                                        <p className="text-xs text-white/70">{celebrity.trending_context}</p>
                                    </div>
                                )}
                            </div>
                            <div className="flex flex-col gap-2">
                                <Button
                                    onClick={() => { setContextDraft(celebrity.trending_context || ""); setContextOpen(true); }}
                                    data-testid={`${kind}-edit-context-btn`}
                                    variant="ghost"
                                    className="text-white/60 hover:text-white hover:bg-white/5 text-xs h-8"
                                >
                                    <Settings2 className="w-3.5 h-3.5 mr-1.5" /> Editar contexto
                                </Button>
                                <Button
                                    onClick={fetchRecommendations}
                                    disabled={recoLoading}
                                    data-testid={`${kind}-fetch-reco-btn`}
                                    className="celeb-bg text-black font-bold h-9"
                                >
                                    {recoLoading ? (
                                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analizando...</>
                                    ) : (
                                        <><Sparkles className="w-4 h-4 mr-1.5" /> Generar recomendaciones</>
                                    )}
                                </Button>
                            </div>
                        </div>

                        {recommendations?.trend_keywords_used?.length > 0 && (
                            <div className="mt-3 p-3 rounded-lg bg-yellow-400/5 border border-yellow-400/20">
                                <p className="text-[9px] uppercase tracking-widest text-yellow-400/60 font-bold mb-1">Keywords trending detectados por algoritmo</p>
                                <div className="flex flex-wrap gap-1.5">
                                    {recommendations.trend_keywords_used.map((kw, i) => (
                                        <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400/10 text-yellow-300/80">{kw}</span>
                                    ))}
                                </div>
                            </div>
                        )}
                        {recommendations?.strategy && (
                            <div className="mt-3 p-4 rounded-lg celeb-border border bg-black/30">
                                <p className="text-[10px] uppercase tracking-widest celeb-text font-bold mb-1.5">Estrategia general</p>
                                <p className="text-sm text-white/80 leading-relaxed">{recommendations.strategy}</p>
                            </div>
                        )}
                        {recommendations?.trending_patterns && (
                            <div className="mt-3 p-4 rounded-lg bg-white/3 border border-white/8">
                                <p className="text-[10px] uppercase tracking-widest text-white/40 font-bold mb-1.5">Patrones de redes sociales detectados</p>
                                <p className="text-xs text-white/60 leading-relaxed">{recommendations.trending_patterns}</p>
                            </div>
                        )}
                    </div>

                    {!recommendations && !recoLoading && (
                        <div className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                            Genera recomendaciones para ver el ranking IA.
                        </div>
                    )}

                    {recommendations?.recommendations?.length > 0 && (() => {
                        const cats = ["recent", "viral", "trend"];
                        const catColors = { recent: "#FF3B30", viral: "#FACC15", trend: "#34D399" };
                        const grouped = cats.reduce((acc, c) => {
                            acc[c] = recommendations.recommendations.filter(r => r.category === c);
                            return acc;
                        }, {});
                        return (
                            <div className="space-y-8">
                                {cats.map(catKey => {
                                    const items = grouped[catKey];
                                    if (!items || items.length === 0) return null;
                                    const label = items[0].category_label;
                                    const color = catColors[catKey];
                                    return (
                                        <div key={catKey}>
                                            <div className="flex items-center gap-2 mb-3">
                                                <div className="w-3 h-3 rounded-full" style={{ background: color }} />
                                                <h3 className="font-bold text-sm text-white">{label}</h3>
                                                <span className="text-[10px] text-white/30">{items.length} videos</span>
                                            </div>
                                            <div className="space-y-2">
                                                {items.map((r, idx) => (
                                                    <a
                                                        key={r.video.video_id}
                                                        href={r.video.url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        data-testid={`${kind}-reco-item-${catKey}-${idx}`}
                                                        className="group flex gap-4 p-4 rounded-xl bg-[#111113] border border-white/10 hover:border-white/25 transition"
                                                    >
                                                        <div className="relative shrink-0">
                                                            <img src={r.video.thumbnail_url} alt="" className={`${kind === "short" ? "w-20 h-28" : "w-36 h-20"} rounded-lg object-cover`} />
                                                            <div className="absolute -top-2 -left-2 w-7 h-7 rounded-full text-black font-black flex items-center justify-center text-xs" style={{ background: color }}>
                                                                {idx + 1}
                                                            </div>
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <h4 className="font-semibold text-white text-sm line-clamp-2">{r.video.title}</h4>
                                                            {r.ai_trend_reason && (
                                                                <div className="mt-1.5 px-2 py-1 rounded bg-purple-500/10 border border-purple-500/20">
                                                                    <p className="text-[10px] text-purple-300 leading-snug">🔥 {r.ai_trend_reason}</p>
                                                                </div>
                                                            )}
                                                            {r.reason && <p className="text-xs text-white/55 mt-1 line-clamp-2 leading-relaxed">{r.reason}</p>}
                                                            {r.trend_match && r.trend_match !== "—" && (
                                                                <p className="text-[10px] text-yellow-400/70 mt-1">📡 {r.trend_match}</p>
                                                            )}
                                                            {r.prediction && (
                                                                <p className="text-[10px] text-green-400/70 mt-0.5">🔮 {r.prediction}</p>
                                                            )}
                                                            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-white/35">
                                                                <span className="flex items-center gap-1"><Eye className="w-3 h-3" /> {fmtNumber(r.video.view_count)}</span>
                                                                <span>{timeAgo(r.video.published_at)}</span>
                                                            </div>
                                                        </div>
                                                    </a>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        );
                    })()}
                </TabsContent>
            </Tabs>

            <Dialog open={!!clipsModal} onOpenChange={(o) => !o && setClipsModal(null)}>
                <DialogContent className="bg-[#111113] border-white/10 text-white max-w-2xl max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="font-display text-xl tracking-tight flex items-center gap-2 flex-wrap">
                            <Scissors className="w-4 h-4 celeb-text" /> Clips virales detectados
                            {clipsModal?.data?.source === "ai" && (
                                <span className="text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-full font-medium">
                                    ✨ Generado por IA
                                </span>
                            )}
                            {clipsModal?.data?.source === "chapters" && (
                                <span className="text-[10px] bg-green-500/20 text-green-300 border border-green-500/30 px-2 py-0.5 rounded-full font-medium">
                                    📋 Chapters detectados
                                </span>
                            )}
                            {clipsModal?.data?.source === "peaks" && (
                                <span className="text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/30 px-2 py-0.5 rounded-full font-medium">
                                    🔥 Picos de retención YouTube
                                </span>
                            )}
                        </DialogTitle>
                        <DialogDescription className="text-white/50 line-clamp-2">
                            {clipsModal?.video?.title}
                        </DialogDescription>
                    </DialogHeader>
                    {clipsLoading && (
                        <div className="py-12 text-center text-white/40 flex items-center justify-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            {clipsModal?.video && countChapters(clipsModal.video.description) === 0
                                ? "Analizando con IA..."
                                : "Analizando capítulos..."}
                        </div>
                    )}
                    {clipsModal?.data?.message && !clipsModal?.data?.clips?.length && (
                        <div className="p-6 text-center text-white/50 text-sm border border-dashed border-white/10 rounded-xl">
                            {clipsModal.data.message}
                        </div>
                    )}
                    {clipsModal?.data?.clips?.length > 0 && (
                        <div className="space-y-2">
                            <p className="text-xs text-white/40">
                                {clipsModal.data.source === "ai"
                                    ? "Segmentos recomendados por IA. Click para abrir en YouTube en ese minuto exacto."
                                    : clipsModal.data.source === "peaks"
                                    ? "Segmentos con mayor retención (Most Replayed). Click para abrir en YouTube."
                                    : "Top segmentos rankeados por duración óptima + heat de keywords. Click para abrir en YouTube."}
                            </p>
                            {clipsModal.data.clips.map((c, i) => (
                                <a
                                    key={i}
                                    href={c.link}
                                    target="_blank"
                                    rel="noreferrer"
                                    data-testid={`clip-item-${i}`}
                                    className="flex items-center gap-3 p-3 rounded-lg bg-black/40 border border-white/10 hover:celeb-border transition"
                                >
                                    <div
                                        className="w-12 h-12 rounded-lg font-display font-black flex items-center justify-center text-black text-lg shrink-0"
                                        style={{ background: c.clip_score >= 70 ? "#FF3B30" : c.clip_score >= 50 ? "#FACC15" : "#06B6D4" }}
                                    >
                                        {c.clip_score}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-mono text-sm font-bold text-white bg-white/10 px-2 py-0.5 rounded">{c.ts}</span>
                                            <span className="text-white/40 text-xs">→</span>
                                            <span className="font-mono text-sm font-bold text-white bg-white/10 px-2 py-0.5 rounded">{c.end_ts}</span>
                                            <span className="text-white/30 text-[10px]">({c.duration}s)</span>
                                            <button
                                                onClick={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    navigator.clipboard.writeText(`${c.ts} - ${c.end_ts}`);
                                                    toast.success("Timestamps copiados");
                                                }}
                                                className="text-white/30 hover:text-white text-xs px-1.5 py-0.5 rounded bg-white/5 hover:bg-white/10 transition"
                                                title="Copiar rango"
                                            >
                                                📋
                                            </button>
                                        </div>
                                        <p className="text-sm font-medium text-white truncate mt-0.5">{c.topic}</p>
                                        {c.reason && (
                                            <p className="text-[10px] text-white/40 leading-snug mt-0.5">{c.reason}</p>
                                        )}
                                    </div>
                                    <ExternalLink className="w-3.5 h-3.5 text-white/40 shrink-0" />
                                </a>
                            ))}
                        </div>
                    )}
                </DialogContent>
            </Dialog>

            <Dialog open={contextOpen} onOpenChange={setContextOpen}>
                <DialogContent className="bg-[#111113] border-white/10 text-white max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-display text-2xl tracking-tight">Contexto trending</DialogTitle>
                        <DialogDescription className="text-white/50">
                            Escribe qué está pegando ahorita en redes (política, controversias, virales). La IA usará esto para recomendar.
                        </DialogDescription>
                    </DialogHeader>
                    <Textarea
                        data-testid="trending-context-textarea"
                        value={contextDraft}
                        onChange={(e) => setContextDraft(e.target.value)}
                        placeholder="ej. Cruz Azul campeón, política mexicana, funa por comentario X, guerra Ucrania, día del padre..."
                        className="bg-[#0A0A0B] border-white/10 text-white min-h-[140px]"
                    />
                    <div className="flex justify-end gap-2">
                        <Button variant="ghost" onClick={() => setContextOpen(false)} className="text-white/60 hover:text-white hover:bg-white/5">
                            Cancelar
                        </Button>
                        <Button onClick={saveContext} data-testid="save-context-btn" className="celeb-bg text-black font-bold">
                            Guardar
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
};

const Grid = ({ videos, kind, loading, label, onShowClips }) => {
    if (loading) {
        return (
            <div data-testid={`${kind}-${label === "Más recientes" ? "recent" : "viral"}-loading`} className="p-12 text-center text-white/40 border border-dashed border-white/10 rounded-xl">
                Cargando más videos del canal...
            </div>
        );
    }
    if (!videos || videos.length === 0) {
        return (
            <div data-testid={`${kind}-${label === "Más recientes" ? "recent" : "viral"}-empty`} className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                Sin {kind === "short" ? "shorts" : "videos"}. Pulsa "Actualizar" arriba para sincronizar.
            </div>
        );
    }
    const isShort = kind === "short";
    const gridCls = isShort
        ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
        : "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4";
    const scoreColor = (s) => s >= 75 ? "#FF3B30" : s >= 55 ? "#FACC15" : s >= 35 ? "#06B6D4" : "#71717A";
    const sectionKey = label === "Más recientes" ? "recent" : "viral";
    return (
        <div>
            <div className="flex items-center justify-between gap-3 mb-3 text-xs text-white/45">
                <span data-testid={`${kind}-${sectionKey}-count`} className="font-bold uppercase tracking-widest">
                    {videos.length} {kind === "short" ? "shorts" : "videos"} cargados
                </span>
                <span data-testid={`${kind}-${sectionKey}-hint`}>Se muestran los disponibles sin limitar por fecha.</span>
            </div>
            <div className={gridCls}>
                {videos.map((v) => (
                    <div key={v.video_id} data-testid={`${kind}-${sectionKey}-video-${v.video_id}`} className="group rounded-xl bg-[#111113] border border-white/10 hover:border-white/20 overflow-hidden transition-all">
                    <a href={v.url} target="_blank" rel="noreferrer" className="block">
                        <div className={`relative ${isShort ? "aspect-[9/16]" : "aspect-video"} overflow-hidden bg-black`}>
                            <img src={v.thumbnail_url} alt={v.title} className="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
                            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                                <div className="w-12 h-12 rounded-full celeb-bg flex items-center justify-center">
                                    <Play className="w-5 h-5 text-black fill-black ml-0.5" />
                                </div>
                            </div>
                            {/* Viral score badge */}
                            {v.viral_score != null && (
                                <div
                                    data-testid={`viral-score-${v.video_id}`}
                                    className="absolute top-2 right-2 px-2 py-1 rounded-md font-display font-black text-xs text-black shadow-lg flex items-center gap-1"
                                    style={{ background: scoreColor(v.viral_score) }}
                                    title={`Score viral ${v.viral_score}/100`}
                                >
                                    <Flame className="w-3 h-3" strokeWidth={3} />
                                    {v.viral_score}
                                </div>
                            )}
                            <div className="absolute bottom-2 left-2 text-[10px] uppercase tracking-widest font-bold text-white/80">
                                {timeAgo(v.published_at)}
                            </div>
                            {v.duration_seconds > 0 && (
                                <div className="absolute bottom-2 right-2 text-[10px] font-bold text-white bg-black/70 px-1.5 py-0.5 rounded">
                                    {Math.floor(v.duration_seconds / 60)}:{String(v.duration_seconds % 60).padStart(2, "0")}
                                </div>
                            )}
                        </div>
                        <div className="p-3">
                            <h4 className={`font-medium text-white line-clamp-2 leading-snug ${isShort ? "text-xs min-h-[2rem]" : "text-sm min-h-[2.5rem]"}`}>
                                {v.title}
                            </h4>
                            <div className="flex items-center gap-3 mt-2 text-[10px] text-white/40">
                                <span className="flex items-center gap-1"><Eye className="w-3 h-3" /> {fmtNumber(v.view_count)}</span>
                                {!isShort && (
                                    <>
                                        <span className="flex items-center gap-1"><ThumbsUp className="w-3 h-3" /> {fmtNumber(v.like_count)}</span>
                                        <span className="flex items-center gap-1"><MessageCircle className="w-3 h-3" /> {fmtNumber(v.comment_count)}</span>
                                    </>
                                )}
                            </div>
                        </div>
                    </a>
                    {!isShort && onShowClips && v.duration_seconds > 300 && (() => {
                        const chapCount = countChapters(v.description);
                        return (
                            <button
                                onClick={() => onShowClips(v)}
                                data-testid={`detect-clips-${v.video_id}`}
                                className="w-full px-3 py-2 border-t border-white/10 text-xs font-bold hover:bg-white/5 transition flex items-center justify-center gap-1.5"
                                style={{ color: chapCount > 0 ? "inherit" : "#a78bfa" }}
                            >
                                {chapCount > 0 ? (
                                    <><Scissors className="w-3 h-3 celeb-text" /> {chapCount} clips detectables</>
                                ) : (
                                    <><Sparkles className="w-3 h-3" style={{ color: "#a78bfa" }} /> Analizar con IA</>
                                )}
                            </button>
                        );
                    })()}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default VideoSection;
