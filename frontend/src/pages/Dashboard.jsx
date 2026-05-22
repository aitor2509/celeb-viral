import React from "react";
import { Link } from "react-router-dom";
import { useApp } from "@/lib/AppContext";
import { fmtNumber, timeAgo } from "@/lib/api";
import { Radio, Flame, Bell, ArrowRight, Users, Video } from "lucide-react";

const Dashboard = () => {
    const { celebrities, notifications, unread, setSelectedColor, loading } = useApp();

    if (loading) {
        return (
            <div className="p-8 text-white/40">Cargando...</div>
        );
    }

    const totalSubs = celebrities.reduce((sum, c) => sum + (c.subscriber_count || 0), 0);
    const totalVids = celebrities.reduce((sum, c) => sum + (c.video_count || 0), 0);
    const recentNotifs = notifications.slice(0, 5);

    return (
        <div className="px-6 lg:px-8 py-8 space-y-8 anim-fade-up" data-testid="dashboard-page">
            {/* Hero */}
            <section className="relative overflow-hidden rounded-2xl bg-[#111113] border border-white/10 p-8 lg:p-12 grain">
                <div className="absolute -top-32 -right-32 w-96 h-96 celeb-glow" />
                <div className="relative">
                    <p className="text-xs uppercase tracking-[0.3em] text-white/40 font-medium">
                        Meta Buster · Social Media Intelligence
                    </p>
                    <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-black tracking-tighter mt-3 max-w-3xl">
                        El radar de tus <span className="celeb-text">personajes</span>.
                    </h1>
                    <p className="text-base text-white/60 mt-4 max-w-2xl leading-relaxed">
                        Sigue lo último, lo más viral y lo que está incendiando internet sobre cada cuenta que manejas.
                    </p>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8 max-w-3xl">
                        <Stat icon={Users} label="Personajes" value={celebrities.length} />
                        <Stat icon={Radio} label="Subs totales" value={fmtNumber(totalSubs)} />
                        <Stat icon={Video} label="Videos" value={fmtNumber(totalVids)} />
                        <Stat icon={Bell} label="Sin leer" value={unread} highlight={unread > 0} />
                    </div>
                </div>
            </section>

            {/* Celebrities grid */}
            <section>
                <div className="flex items-end justify-between mb-5">
                    <div>
                        <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Personajes</h2>
                        <p className="text-sm text-white/40 mt-1">Click para entrar al radar de cada uno</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                    {celebrities.map((c) => (
                        <Link
                            to={`/celebrity/${c.id}`}
                            key={c.id}
                            data-testid={`celebrity-card-${c.id}`}
                            onClick={() => setSelectedColor(c.color)}
                            className="group relative rounded-xl bg-[#111113] border border-white/10 hover:border-white/20 overflow-hidden transition-all hover:-translate-y-0.5"
                        >
                            <div className="aspect-[4/3] relative overflow-hidden">
                                {c.image_url ? (
                                    <img
                                        src={c.image_url}
                                        alt={c.name}
                                        className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
                                    />
                                ) : (
                                    <div className="w-full h-full" style={{ background: c.color }} />
                                )}
                                <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0B] via-[#0A0A0B]/40 to-transparent" />
                                <div
                                    className="absolute top-3 left-3 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-widest text-black"
                                    style={{ background: c.color }}
                                >
                                    Activo
                                </div>
                            </div>
                            <div className="p-4">
                                <h3 className="font-display font-bold text-lg tracking-tight text-white">{c.name}</h3>
                                <div className="flex items-center justify-between mt-2">
                                    <p className="text-xs text-white/40">
                                        {fmtNumber(c.subscriber_count)} subs · {fmtNumber(c.video_count)} videos
                                    </p>
                                    <ArrowRight className="w-4 h-4 text-white/30 group-hover:text-white group-hover:translate-x-1 transition" />
                                </div>
                            </div>
                            <div
                                className="absolute inset-x-0 bottom-0 h-0.5"
                                style={{ background: c.color }}
                            />
                        </Link>
                    ))}

                    {celebrities.length === 0 && (
                        <div className="col-span-full p-12 text-center text-white/40 border border-dashed border-white/10 rounded-xl">
                            No hay personajes aún. Agrega uno con el botón "+ Personaje".
                        </div>
                    )}
                </div>
            </section>

            {/* Recent notifications */}
            {recentNotifs.length > 0 && (
                <section>
                    <div className="flex items-end justify-between mb-5">
                        <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-2">
                            <Flame className="w-6 h-6 celeb-text" />
                            Lo más reciente
                        </h2>
                    </div>
                    <div className="grid gap-3">
                        {recentNotifs.map((n) => (
                            <Link
                                to={`/celebrity/${n.celebrity_id}`}
                                key={n.id}
                                data-testid={`recent-notif-${n.id}`}
                                onClick={() => setSelectedColor(n.celebrity_color)}
                                className="group flex items-center gap-4 p-3 rounded-xl bg-[#111113] border border-white/10 hover:border-white/20 transition"
                            >
                                {n.image_url ? (
                                    <img src={n.image_url} alt="" className="w-16 h-16 rounded-lg object-cover" />
                                ) : (
                                    <div className="w-16 h-16 rounded-lg" style={{ background: n.celebrity_color }} />
                                )}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] uppercase tracking-widest font-bold" style={{ color: n.celebrity_color }}>
                                            {n.celebrity_name}
                                        </span>
                                        <span className="text-[10px] text-white/30">· {timeAgo(n.created_at)}</span>
                                    </div>
                                    <p className="text-sm font-semibold text-white mt-0.5 line-clamp-1">{n.title}</p>
                                    <p className="text-xs text-white/50 line-clamp-1 mt-0.5">{n.message}</p>
                                </div>
                                <ArrowRight className="w-4 h-4 text-white/30 group-hover:text-white group-hover:translate-x-1 transition shrink-0" />
                            </Link>
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
};

const Stat = ({ icon: Icon, label, value, highlight }) => (
    <div className={`rounded-xl border p-4 ${highlight ? "border-white/30 bg-white/5" : "border-white/10 bg-black/30"}`}>
        <div className="flex items-center gap-2 text-white/40">
            <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
            <span className="text-[10px] uppercase tracking-widest font-medium">{label}</span>
        </div>
        <p className="font-display text-3xl font-black tracking-tight text-white mt-2">{value}</p>
    </div>
);

export default Dashboard;
