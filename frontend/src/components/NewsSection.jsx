import React, { useEffect, useState, useCallback } from "react";
import { api, timeAgo } from "@/lib/api";
import { Newspaper, ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const NewsSection = ({ celebrity }) => {
    const [news, setNews] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async (refresh = false) => {
        if (refresh) setRefreshing(true);
        try {
            const res = await api.get(`/celebrities/${celebrity.id}/news`, { params: { refresh } });
            setNews(res.data.news);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, [celebrity.id]);

    useEffect(() => { load(); }, [load]);

    const handleRefresh = async () => {
        await load(true);
        toast.success("Noticias actualizadas");
    };

    return (
        <div>
            <div className="flex items-end justify-between mb-5">
                <div>
                    <h3 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2">
                        <Newspaper className="w-5 h-5 celeb-text" />
                        Noticias & funas
                    </h3>
                    <p className="text-sm text-white/40 mt-1">
                        Auto-scrapeado de Google News (México, español) sobre {celebrity.name}
                    </p>
                </div>
                <button
                    onClick={handleRefresh}
                    disabled={refreshing}
                    data-testid="refresh-news-btn"
                    className="h-9 px-4 rounded-lg bg-[#1a1a1d] border border-white/10 text-white/70 hover:text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} /> Actualizar
                </button>
            </div>

            {loading && <div className="text-white/40 p-8">Cargando noticias...</div>}

            <div className="grid gap-3">
                {!loading && news.length === 0 && (
                    <div className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                        Sin noticias recientes en Google News.
                    </div>
                )}
                {news.map((n, i) => (
                    <a
                        key={n.link || `news-${i}`}
                        href={n.link}
                        target="_blank"
                        rel="noreferrer"
                        data-testid={`news-item-${i}`}
                        className="group flex gap-4 p-4 rounded-xl bg-[#111113] border border-white/10 hover:celeb-border transition"
                    >
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] uppercase tracking-widest font-bold celeb-text">
                                    {n.source || "Noticia"}
                                </span>
                                {n.published && (
                                    <span className="text-[10px] text-white/30">· {timeAgo(new Date(n.published).toISOString())}</span>
                                )}
                            </div>
                            <h4 className="font-display font-bold text-base text-white mt-1 leading-snug">{n.title}</h4>
                            {n.summary && (
                                <p className="text-sm text-white/50 mt-1 line-clamp-2 leading-relaxed">{n.summary}</p>
                            )}
                        </div>
                        <ExternalLink className="w-4 h-4 text-white/30 group-hover:text-white shrink-0 self-start mt-1" />
                    </a>
                ))}
            </div>
        </div>
    );
};

export default NewsSection;
