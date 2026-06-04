import React, { useState, useRef, useEffect } from "react";
import { Search, Bell, Command } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useApp } from "@/lib/AppContext";
import { timeAgo } from "@/lib/api";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";

const Header = ({ onAddCelebrity }) => {
    const { celebrities, notifications, unread, markAllRead, markRead } = useApp();
    const [query, setQuery] = useState("");
    const navigate = useNavigate();
    const inputRef = useRef(null);

    useEffect(() => {
        const onKey = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                inputRef.current?.focus();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    const filtered = query
        ? celebrities.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
        : [];

    const handleNotifClick = async (n) => {
        await markRead(n.id);
        if (n.celebrity_id) navigate(`/celebrity/${n.celebrity_id}`);
    };

    return (
        <header
            data-testid="app-header"
            className="sticky top-0 z-40 bg-[#0A0A0B]/80 backdrop-blur-xl border-b border-white/10"
        >
            <div className="flex items-center justify-between gap-4 px-6 lg:px-8 h-16">
                <div className="flex-1 max-w-xl relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" strokeWidth={1.5} />
                    <input
                        ref={inputRef}
                        data-testid="celebrity-search-input"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onBlur={() => setTimeout(() => setQuery(""), 200)}
                        placeholder="Buscar personajes..."
                        className="w-full bg-[#111113] border border-white/10 hover:border-white/20 focus:border-white/30 rounded-lg text-white px-9 py-2 text-sm outline-none transition placeholder:text-white/30"
                    />
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-[10px] text-white/30">
                        <kbd className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 flex items-center gap-0.5"><Command className="w-2.5 h-2.5" /> K</kbd>
                    </div>

                    {filtered.length > 0 && (
                        <div className="absolute top-full mt-2 w-full bg-[#111113] border border-white/10 rounded-lg overflow-hidden shadow-2xl">
                            {filtered.map((c) => (
                                <button
                                    key={c.id}
                                    data-testid={`search-result-${c.id}`}
                                    onClick={() => {
                                        navigate(`/celebrity/${c.id}`);
                                        setQuery("");
                                    }}
                                    className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition text-left"
                                >
                                    {c.image_url ? (
                                        <img src={c.image_url} alt={c.name} className="w-8 h-8 rounded-full object-cover" />
                                    ) : (
                                        <div className="w-8 h-8 rounded-full" style={{ background: c.color }} />
                                    )}
                                    <span className="text-sm font-medium text-white">{c.name}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    {/* Live status indicator (replaces manual refresh button) */}
                    <div
                        data-testid="live-status-indicator"
                        className="flex items-center gap-1.5 text-[11px] text-white/40 font-medium"
                    >
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
                        En vivo
                    </div>

                    <Popover>
                        <PopoverTrigger asChild>
                            <button
                                data-testid="notifications-bell"
                                className="relative h-9 w-9 rounded-lg bg-[#111113] hover:bg-[#1a1a1d] border border-white/10 text-white/70 hover:text-white flex items-center justify-center transition"
                                aria-label="Notificaciones"
                            >
                                <Bell className="w-4 h-4" strokeWidth={1.5} />
                                {unread > 0 && (
                                    <span
                                        data-testid="notif-badge"
                                        className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#0A0A0B]"
                                    >
                                        {unread > 99 ? "99+" : unread}
                                    </span>
                                )}
                            </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-96 p-0 bg-[#111113] border-white/10" align="end">
                            <div className="flex items-center justify-between p-3 border-b border-white/10">
                                <h4 className="font-display font-bold text-white">Notificaciones</h4>
                                {unread > 0 && (
                                    <button
                                        onClick={markAllRead}
                                        data-testid="mark-all-read-btn"
                                        className="text-xs text-white/60 hover:text-white"
                                    >
                                        Marcar todas
                                    </button>
                                )}
                            </div>
                            <div className="max-h-96 overflow-y-auto">
                                {notifications.length === 0 && (
                                    <div className="p-6 text-center text-white/40 text-sm">Sin notificaciones</div>
                                )}
                                {notifications.map((n) => {
                                    const isBomb = n.type === "video_bomb";
                                    const labelColor = isBomb ? "#FF3B30" : n.celebrity_color;
                                    const label = isBomb
                                        ? "💣 VIDEO BOMBA"
                                        : n.type === "new_video"
                                            ? "Nuevo video"
                                            : n.type;
                                    return (
                                        <button
                                            key={n.id}
                                            data-testid={`notif-item-${n.id}`}
                                            onClick={() => handleNotifClick(n)}
                                            className={`w-full text-left flex gap-3 p-3 border-b border-white/5 hover:bg-white/5 transition ${
                                                !n.read ? "bg-white/[0.02]" : ""
                                            }`}
                                        >
                                            {n.image_url ? (
                                                <img src={n.image_url} alt="" className="w-12 h-12 rounded object-cover shrink-0" />
                                            ) : (
                                                <div className="w-12 h-12 rounded shrink-0" style={{ background: n.celebrity_color }} />
                                            )}
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span
                                                        className="text-[10px] uppercase tracking-wider font-bold"
                                                        style={{ color: labelColor }}
                                                    >
                                                        {label}
                                                    </span>
                                                    {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-red-500 pulse-dot" />}
                                                </div>
                                                <p className="text-sm font-semibold text-white truncate mt-0.5">{n.title}</p>
                                                <p className="text-xs text-white/50 line-clamp-2 mt-0.5">{n.message}</p>
                                                <p className="text-[10px] text-white/30 mt-1">{timeAgo(n.created_at)}</p>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </PopoverContent>
                    </Popover>

                    <button
                        onClick={onAddCelebrity}
                        data-testid="header-add-celebrity-btn"
                        className="h-9 px-4 rounded-lg bg-white text-black text-sm font-bold hover:bg-white/90 transition flex items-center gap-1.5"
                    >
                        + Personaje
                    </button>
                </div>
            </div>
        </header>
    );
};

export default Header;
