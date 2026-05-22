import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, fmtNumber, timeAgo } from "@/lib/api";
import { useApp } from "@/lib/AppContext";
import {
    ExternalLink, Phone, Plus, Flame, Trash2, ArrowLeft, RefreshCw, Video, Film, Newspaper, Megaphone,
} from "lucide-react";
import AddViralDialog from "@/components/AddViralDialog";
import AddContactDialog from "@/components/AddContactDialog";
import VideoSection from "@/components/VideoSection";
import NewsSection from "@/components/NewsSection";
import SecondaryChannels from "@/components/SecondaryChannels";
import { toast } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const TAG_LABEL = { viral: "Viral", funa: "Funa", colab: "Colab", noticia: "Noticia" };
const TAG_COLOR = { viral: "#FACC15", funa: "#FF3B30", colab: "#06B6D4", noticia: "#A1A1AA" };

const CelebrityDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { setSelectedColor, loadCelebrities } = useApp();
    const [celeb, setCeleb] = useState(null);
    const [virals, setVirals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [viralOpen, setViralOpen] = useState(false);
    const [contactOpen, setContactOpen] = useState(false);

    const loadCeleb = useCallback(async () => {
        try {
            const [c, v] = await Promise.all([
                api.get(`/celebrities/${id}`),
                api.get(`/celebrities/${id}/virals`),
            ]);
            setCeleb(c.data);
            setSelectedColor(c.data.color);
            setVirals(v.data.virals);
        } catch (e) {
            toast.error("Error al cargar");
        } finally {
            setLoading(false);
        }
    }, [id, setSelectedColor]);

    useEffect(() => { loadCeleb(); }, [loadCeleb]);

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await api.get(`/celebrities/${id}/videos`, { params: { refresh: true } });
            await loadCeleb();
            toast.success("Videos actualizados");
        } catch {
            toast.error("Error al actualizar");
        } finally {
            setRefreshing(false);
        }
    };

    const handleDeleteViral = async (vid) => {
        await api.delete(`/virals/${vid}`);
        toast.success("Eliminado");
        loadCeleb();
    };

    const handleDeleteCelebrity = async () => {
        if (!window.confirm(`¿Eliminar a ${celeb.name}? Esta acción es permanente.`)) return;
        await api.delete(`/celebrities/${id}`);
        await loadCelebrities();
        toast.success("Personaje eliminado");
        navigate("/");
    };

    if (loading) return <div className="p-8 text-white/40">Cargando...</div>;
    if (!celeb) return <div className="p-8 text-white/40">No encontrado</div>;

    return (
        <div className="px-6 lg:px-8 py-6 space-y-8 anim-fade-up" data-testid={`celebrity-detail-${id}`}>
            {/* Profile header */}
            <section className="relative rounded-2xl bg-[#111113] border border-white/10 overflow-hidden grain">
                <div className="absolute -top-48 -left-32 w-[500px] h-[500px] celeb-glow" />
                <div className="relative p-6 lg:p-10">
                    <button
                        onClick={() => navigate("/")}
                        data-testid="back-btn"
                        className="text-sm text-white/50 hover:text-white flex items-center gap-1 mb-6"
                    >
                        <ArrowLeft className="w-3.5 h-3.5" /> Dashboard
                    </button>

                    <div className="flex flex-col lg:flex-row lg:items-end gap-6">
                        <div className="flex items-center gap-5">
                            {celeb.image_url ? (
                                <img src={celeb.image_url} alt={celeb.name} className="w-24 h-24 lg:w-32 lg:h-32 rounded-2xl object-cover ring-2 celeb-border" />
                            ) : (
                                <div className="w-24 h-24 lg:w-32 lg:h-32 rounded-2xl celeb-bg" />
                            )}
                            <div>
                                <p className="text-xs uppercase tracking-[0.3em] celeb-text font-bold">En radar · YouTube</p>
                                <h1 data-testid="celebrity-name" className="font-display text-4xl sm:text-5xl lg:text-6xl font-black tracking-tighter text-white mt-1">
                                    {celeb.name}
                                </h1>
                                <div className="flex items-center gap-4 text-sm text-white/50 mt-3">
                                    <span>{fmtNumber(celeb.subscriber_count)} subs</span>
                                    <span className="w-1 h-1 rounded-full bg-white/30" />
                                    <span>{fmtNumber(celeb.video_count)} videos</span>
                                    {celeb.secondary_channels?.length > 0 && (
                                        <>
                                            <span className="w-1 h-1 rounded-full bg-white/30" />
                                            <span>+{celeb.secondary_channels.length} canales</span>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="lg:ml-auto flex flex-wrap gap-2">
                            <button onClick={() => setContactOpen(true)} data-testid="add-contact-btn" className="h-10 px-4 rounded-lg border celeb-border celeb-text text-sm font-bold hover:bg-white/5 flex items-center gap-2 transition">
                                <Phone className="w-4 h-4" /> Suscribirme
                            </button>
                            <button onClick={handleRefresh} disabled={refreshing} data-testid="refresh-celebrity-btn" className="h-10 px-4 rounded-lg bg-[#1a1a1d] border border-white/10 text-white/70 hover:text-white text-sm font-bold flex items-center gap-2 disabled:opacity-50">
                                <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} /> Actualizar
                            </button>
                            <button onClick={handleDeleteCelebrity} data-testid="delete-celebrity-btn" className="h-10 px-3 rounded-lg bg-transparent border border-white/10 text-white/40 hover:text-red-400 hover:border-red-400/50 text-sm flex items-center gap-2 transition">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                </div>
            </section>

            {/* Secondary channels manager */}
            <SecondaryChannels celebrity={celeb} onUpdate={loadCeleb} />

            {/* Main content tabs */}
            <Tabs defaultValue="videos" className="w-full" data-testid="main-content-tabs">
                <TabsList className="bg-[#111113] border border-white/10 p-1 h-auto flex-wrap">
                    <TabsTrigger value="videos" data-testid="tab-videos" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 flex items-center gap-1.5">
                        <Video className="w-3.5 h-3.5" /> Videos
                    </TabsTrigger>
                    <TabsTrigger value="shorts" data-testid="tab-shorts" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 flex items-center gap-1.5">
                        <Film className="w-3.5 h-3.5" /> Shorts
                    </TabsTrigger>
                    <TabsTrigger value="news" data-testid="tab-news" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 flex items-center gap-1.5">
                        <Newspaper className="w-3.5 h-3.5" /> Noticias
                    </TabsTrigger>
                    <TabsTrigger value="funas" data-testid="tab-funas" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:font-bold px-4 py-2 flex items-center gap-1.5">
                        <Megaphone className="w-3.5 h-3.5" /> Funas manuales
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="videos" className="mt-6">
                    <VideoSection celebrity={celeb} kind="video" onCelebrityUpdate={loadCeleb} />
                </TabsContent>

                <TabsContent value="shorts" className="mt-6">
                    <VideoSection celebrity={celeb} kind="short" onCelebrityUpdate={loadCeleb} />
                </TabsContent>

                <TabsContent value="news" className="mt-6">
                    <NewsSection celebrity={celeb} />
                </TabsContent>

                <TabsContent value="funas" className="mt-6">
                    <div className="flex items-end justify-between mb-5">
                        <div>
                            <h3 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2">
                                <Flame className="w-5 h-5 celeb-text" /> Entradas manuales
                            </h3>
                            <p className="text-sm text-white/40 mt-1">Funas, colabs, virales que tú anotes manualmente</p>
                        </div>
                        <button onClick={() => setViralOpen(true)} data-testid="add-viral-btn" className="h-9 px-4 rounded-lg celeb-bg text-black text-sm font-bold flex items-center gap-1.5 hover:opacity-90 transition">
                            <Plus className="w-4 h-4" /> Agregar
                        </button>
                    </div>
                    <div className="grid gap-3">
                        {virals.length === 0 && (
                            <div className="p-12 text-center text-white/30 border border-dashed border-white/10 rounded-xl">
                                Sin entradas manuales aún.
                            </div>
                        )}
                        {virals.map((v) => (
                            <div key={v.id} data-testid={`viral-item-${v.id}`} className="group flex gap-4 p-4 rounded-xl bg-[#111113] border border-white/10 hover:border-white/20 transition">
                                {v.image_url && <img src={v.image_url} alt="" className="w-24 h-24 rounded-lg object-cover shrink-0" />}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] uppercase tracking-widest font-bold px-2 py-0.5 rounded" style={{ background: TAG_COLOR[v.tag] + "20", color: TAG_COLOR[v.tag] }}>
                                            {TAG_LABEL[v.tag] || v.tag}
                                        </span>
                                        <span className="text-xs text-white/30">{timeAgo(v.created_at)}</span>
                                    </div>
                                    <h4 className="font-display font-bold text-lg text-white mt-1">{v.title}</h4>
                                    <p className="text-sm text-white/60 mt-1 line-clamp-2">{v.description}</p>
                                    {v.source_url && (
                                        <a href={v.source_url} target="_blank" rel="noreferrer" className="text-xs celeb-text font-medium hover:underline mt-2 inline-flex items-center gap-1">
                                            Ver fuente <ExternalLink className="w-3 h-3" />
                                        </a>
                                    )}
                                </div>
                                <button onClick={() => handleDeleteViral(v.id)} data-testid={`delete-viral-${v.id}`} className="text-white/30 hover:text-red-400 opacity-0 group-hover:opacity-100 transition self-start">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                </TabsContent>
            </Tabs>

            <AddViralDialog open={viralOpen} onOpenChange={setViralOpen} celebrity={celeb} onAdded={loadCeleb} />
            <AddContactDialog open={contactOpen} onOpenChange={setContactOpen} celebrity={celeb} />
        </div>
    );
};

export default CelebrityDetail;
