import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Home, Radio, Plus, Sparkles } from "lucide-react";
import { useApp } from "@/lib/AppContext";

const Sidebar = ({ onAddCelebrity }) => {
    const { celebrities, setSelectedColor } = useApp();
    const location = useLocation();

    const isActive = (id) => location.pathname === `/celebrity/${id}`;

    return (
        <aside
            data-testid="sidebar"
            className="hidden md:flex flex-col w-64 shrink-0 bg-[#0A0A0B] border-r border-white/10 h-screen sticky top-0"
        >
            <div className="px-6 pt-6 pb-4 border-b border-white/10">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-white text-black flex items-center justify-center">
                        <Sparkles className="w-4 h-4" strokeWidth={2.5} />
                    </div>
                    <span className="font-display font-black text-xl tracking-tight" data-testid="app-logo">
                        CelebTrack
                    </span>
                </div>
                <p className="text-xs text-white/40 mt-2 uppercase tracking-widest">Meta Buster CMS</p>
            </div>

            <nav className="px-3 py-4 space-y-1">
                <NavLink
                    to="/"
                    data-testid="nav-dashboard"
                    onClick={() => setSelectedColor("#007AFF")}
                    className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                            isActive ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
                        }`
                    }
                >
                    <Home className="w-4 h-4" strokeWidth={1.5} />
                    Dashboard
                </NavLink>
            </nav>

            <div className="px-6 pt-2 pb-2 flex items-center justify-between">
                <p className="text-xs font-medium text-white/40 uppercase tracking-widest">Personajes</p>
                <button
                    onClick={onAddCelebrity}
                    data-testid="sidebar-add-celebrity-btn"
                    className="w-6 h-6 rounded-md hover:bg-white/10 flex items-center justify-center text-white/60 hover:text-white transition"
                    aria-label="Agregar personaje"
                >
                    <Plus className="w-4 h-4" strokeWidth={2} />
                </button>
            </div>

            <div className="px-3 flex-1 overflow-y-auto pb-6 space-y-0.5">
                {celebrities.map((c) => (
                    <NavLink
                        key={c.id}
                        to={`/celebrity/${c.id}`}
                        data-testid={`celebrity-list-item-${c.id}`}
                        onClick={() => setSelectedColor(c.color)}
                        className={`group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all relative ${
                            isActive(c.id)
                                ? "bg-white/10 text-white"
                                : "text-white/60 hover:bg-white/5 hover:text-white"
                        }`}
                    >
                        {isActive(c.id) && (
                            <span
                                className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r"
                                style={{ background: c.color }}
                            />
                        )}
                        {c.image_url ? (
                            <img src={c.image_url} alt={c.name} className="w-7 h-7 rounded-full object-cover ring-1 ring-white/10" />
                        ) : (
                            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: c.color, color: "#000" }}>
                                {c.name[0]}
                            </div>
                        )}
                        <span className="truncate flex-1 font-medium">{c.name}</span>
                        <Radio className="w-3 h-3 opacity-0 group-hover:opacity-60" />
                    </NavLink>
                ))}
            </div>

            <div className="px-6 py-4 border-t border-white/10">
                <p className="text-xs text-white/30">v1.0 · {celebrities.length} personajes</p>
            </div>
        </aside>
    );
};

export default Sidebar;
