import React, { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Plus, X, Search } from "lucide-react";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const SecondaryChannels = ({ celebrity, onUpdate }) => {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [searching, setSearching] = useState(false);
    const [adding, setAdding] = useState(false);

    const handleSearch = async (e) => {
        e?.preventDefault();
        if (!query.trim()) return;
        setSearching(true);
        try {
            const res = await api.get("/youtube/search", { params: { q: query } });
            setResults(res.data.results);
        } catch {
            toast.error("Error en búsqueda");
        } finally {
            setSearching(false);
        }
    };

    const handleAdd = async (channelId) => {
        setAdding(true);
        try {
            await api.post(`/celebrities/${celebrity.id}/secondary-channels`, { youtube_channel_id: channelId });
            toast.success("Canal agregado");
            setOpen(false);
            setQuery(""); setResults([]);
            onUpdate?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Error al agregar");
        } finally {
            setAdding(false);
        }
    };

    const handleRemove = async (channelId) => {
        if (!window.confirm("¿Eliminar este canal?")) return;
        await api.delete(`/celebrities/${celebrity.id}/secondary-channels/${channelId}`);
        toast.success("Canal eliminado");
        onUpdate?.();
    };

    const channels = celebrity.secondary_channels || [];

    return (
        <div className="rounded-xl bg-[#111113] border border-white/10 p-5">
            <div className="flex items-center justify-between mb-3">
                <div>
                    <h3 className="font-display text-base font-bold">Canales adicionales</h3>
                    <p className="text-xs text-white/40 mt-0.5">Ej. canal de shorts, "Lo mejor de...", etc.</p>
                </div>
                <Button
                    onClick={() => setOpen(true)}
                    data-testid="add-secondary-channel-btn"
                    size="sm"
                    className="celeb-bg text-black font-bold h-8"
                >
                    <Plus className="w-3.5 h-3.5 mr-1" /> Agregar canal
                </Button>
            </div>

            {channels.length === 0 ? (
                <p className="text-xs text-white/30 py-2">Sin canales adicionales.</p>
            ) : (
                <div className="flex flex-wrap gap-2 mt-2">
                    {channels.map((c) => (
                        <div
                            key={c.channel_id}
                            data-testid={`secondary-channel-${c.channel_id}`}
                            className="flex items-center gap-2 px-2 py-1 rounded-lg bg-black/40 border border-white/10"
                        >
                            <img src={c.thumbnail} alt="" className="w-6 h-6 rounded-full object-cover" />
                            <span className="text-xs text-white">{c.title}</span>
                            <button
                                onClick={() => handleRemove(c.channel_id)}
                                data-testid={`remove-channel-${c.channel_id}`}
                                className="text-white/40 hover:text-red-400 transition"
                            >
                                <X className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="bg-[#111113] border-white/10 text-white max-w-xl">
                    <DialogHeader>
                        <DialogTitle className="font-display text-2xl">Agregar canal adicional</DialogTitle>
                        <DialogDescription className="text-white/50">
                            Busca en YouTube el canal extra de {celebrity.name}.
                        </DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleSearch} className="flex gap-2">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
                            <Input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                data-testid="secondary-search-input"
                                placeholder={`ej. Lo mejor de ${celebrity.name}`}
                                className="bg-[#0A0A0B] border-white/10 text-white pl-9"
                                autoFocus
                            />
                        </div>
                        <Button type="submit" disabled={searching || !query.trim()} className="bg-white text-black hover:bg-white/90">
                            {searching ? "Buscando..." : "Buscar"}
                        </Button>
                    </form>
                    <div className="max-h-80 overflow-y-auto space-y-1">
                        {results.map((r) => (
                            <button
                                key={r.channel_id}
                                onClick={() => handleAdd(r.channel_id)}
                                disabled={adding}
                                data-testid={`secondary-result-${r.channel_id}`}
                                className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 transition text-left border border-transparent hover:border-white/10 disabled:opacity-50"
                            >
                                <img src={r.thumbnail} alt="" className="w-10 h-10 rounded-full object-cover" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold text-white truncate">{r.title}</p>
                                    <p className="text-xs text-white/50 line-clamp-1">{r.description}</p>
                                </div>
                                <Plus className="w-4 h-4 text-white/40" />
                            </button>
                        ))}
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default SecondaryChannels;
