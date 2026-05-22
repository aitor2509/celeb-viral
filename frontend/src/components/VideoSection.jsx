import React, { useState, useEffect, useCallback } from "react";
import { api, fmtNumber, timeAgo } from "@/lib/api";
import { Play, Eye, ThumbsUp, MessageCircle, Sparkles, Loader2, Settings2 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";

const VideoSection = ({ celebrity, kind, onCelebrityUpdate }) => {
    const [recent, setRecent] = useState([]);
    const [viral, setViral] = useState([]);
    const [recommendations, setRecommendations] = useState(null);
    const [recoLoading, setRecoLoading] = useState(false);
    const [contextOpen, setContextOpen] = useState(false);
    const [contextDraft, setContextDraft] = useState(celebrity.trending_context || "");

    const load = useCallback(async () => {
        const [r, v] = await Promise.all([
            api.get(`/celebrities/${celebrity.id}/videos`, { params: { kind, sort: "recent" } }),
            api.get(`/celebrities/${celebrity.id}/viral-videos`, { params: { kind } }),
        ]);
        setRecent(r.data.videos);
        setViral(v.data.videos);
    }, [celebrity.id, kind]);

    useEffect(() => { load(); }, [load]);

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
                    <Grid videos={recent} kind={kind} />
                </TabsContent>

                <TabsContent value="viral" className="mt-5">
                    <Grid videos={viral} kind={kind} />
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
                                    Claude Sonnet 4.5 analiza el contenido de {celebrity.name} y recomienda qué subir AHORA según tendencias.
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

                        {recommendations?.strategy && (
                            <div className="mt-4 p-4 rounded-lg celeb-border border bg-black/30">
                                <p className="text-[10px] uppercase tracking-widest celeb-text font-bold mb-1.5">Estrategia general</p>
                                <p className="text-sm text-white/80 leading-relaxed">{recommendations.strategy}</p>
                            </div>
                        )}
                    </div>

                    {!recommendations && !recoLoading && (
                        <div className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                            Genera recomendaciones para ver el ranking IA.
                        </div>
                    )}

                    {recommendations?.recommendations?.length > 0 && (
                        <div className="space-y-3">
                            {recommendations.recommendations.map((r, idx) => (
                                <a
                                    key={r.video.video_id}
                                    href={r.video.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    data-testid={`${kind}-reco-item-${idx}`}
                                    className="group flex gap-4 p-4 rounded-xl bg-[#111113] border border-white/10 hover:celeb-border transition"
                                >
                                    <div className="relative shrink-0">
                                        <img src={r.video.thumbnail_url} alt="" className={`${kind === "short" ? "w-24 h-32" : "w-40 h-24"} rounded-lg object-cover`} />
                                        <div
                                            className="absolute -top-2 -left-2 w-9 h-9 rounded-full celeb-bg text-black font-display font-black flex items-center justify-center text-sm"
                                        >
                                            #{idx + 1}
                                        </div>
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="text-[10px] uppercase tracking-widest font-bold celeb-text">
                                                Score {r.score}/100
                                            </span>
                                            <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                                                <div className="h-full celeb-bg" style={{ width: `${r.score}%` }} />
                                            </div>
                                        </div>
                                        <h4 className="font-semibold text-white text-sm line-clamp-2">{r.video.title}</h4>
                                        <p className="text-xs text-white/60 mt-1.5 line-clamp-3 leading-relaxed">{r.reason}</p>
                                        <div className="flex items-center gap-3 mt-2 text-[11px] text-white/40">
                                            <span className="flex items-center gap-1"><Eye className="w-3 h-3" /> {fmtNumber(r.video.view_count)}</span>
                                            <span>{timeAgo(r.video.published_at)}</span>
                                        </div>
                                    </div>
                                </a>
                            ))}
                        </div>
                    )}
                </TabsContent>
            </Tabs>

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

const Grid = ({ videos, kind }) => {
    if (!videos || videos.length === 0) {
        return (
            <div className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                Sin {kind === "short" ? "shorts" : "videos"}. Pulsa "Actualizar" arriba para sincronizar.
            </div>
        );
    }
    const isShort = kind === "short";
    const gridCls = isShort
        ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
        : "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4";
    return (
        <div className={gridCls}>
            {videos.map((v) => (
                <a
                    key={v.video_id}
                    href={v.url}
                    target="_blank"
                    rel="noreferrer"
                    data-testid={`${kind}-video-${v.video_id}`}
                    className="group rounded-xl bg-[#111113] border border-white/10 hover:border-white/20 overflow-hidden transition-all"
                >
                    <div className={`relative ${isShort ? "aspect-[9/16]" : "aspect-video"} overflow-hidden bg-black`}>
                        <img src={v.thumbnail_url} alt={v.title} className="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                            <div className="w-12 h-12 rounded-full celeb-bg flex items-center justify-center">
                                <Play className="w-5 h-5 text-black fill-black ml-0.5" />
                            </div>
                        </div>
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
            ))}
        </div>
    );
};

export default VideoSection;
