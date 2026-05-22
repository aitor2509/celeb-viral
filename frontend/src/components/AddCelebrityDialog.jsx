import React, { useState } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Search, Check } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useApp } from "@/lib/AppContext";

const PRESET_COLORS = [
    "#007AFF", "#FF6B00", "#00FF66", "#FF3B30", "#FF007F",
    "#8B5CF6", "#FACC15", "#06B6D4", "#EC4899", "#10B981",
];

const AddCelebrityDialog = ({ open, onOpenChange }) => {
    const { loadCelebrities } = useApp();
    const [step, setStep] = useState(1); // 1=search, 2=customize
    const [query, setQuery] = useState("");
    const [searching, setSearching] = useState(false);
    const [results, setResults] = useState([]);
    const [selected, setSelected] = useState(null);
    const [name, setName] = useState("");
    const [color, setColor] = useState(PRESET_COLORS[0]);
    const [saving, setSaving] = useState(false);

    const reset = () => {
        setStep(1);
        setQuery("");
        setResults([]);
        setSelected(null);
        setName("");
        setColor(PRESET_COLORS[0]);
    };

    const handleSearch = async (e) => {
        e?.preventDefault();
        if (!query.trim()) return;
        setSearching(true);
        try {
            const res = await api.get(`/youtube/search`, { params: { q: query } });
            setResults(res.data.results);
        } catch (err) {
            toast.error("Error al buscar en YouTube");
            console.error(err);
        } finally {
            setSearching(false);
        }
    };

    const handleSelect = (r) => {
        setSelected(r);
        setName(r.title);
        setStep(2);
    };

    const handleSave = async () => {
        if (!selected || !name) return;
        setSaving(true);
        try {
            await api.post("/celebrities", {
                name,
                color,
                youtube_channel_id: selected.channel_id,
                image_url: selected.thumbnail,
            });
            toast.success(`${name} agregado`);
            await loadCelebrities();
            reset();
            onOpenChange(false);
        } catch (err) {
            toast.error("Error al guardar");
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
            <DialogContent className="bg-[#111113] border-white/10 text-white max-w-xl" data-testid="add-celebrity-dialog">
                <DialogHeader>
                    <DialogTitle className="font-display text-2xl tracking-tight">
                        {step === 1 ? "Buscar personaje en YouTube" : "Personalizar"}
                    </DialogTitle>
                    <DialogDescription className="text-white/50">
                        {step === 1 ? "Busca el canal oficial del personaje" : "Asigna nombre y color de marca"}
                    </DialogDescription>
                </DialogHeader>

                {step === 1 && (
                    <div className="space-y-4">
                        <form onSubmit={handleSearch} className="flex gap-2">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
                                <Input
                                    data-testid="yt-search-input"
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="ej. Luis Fonsi"
                                    className="bg-[#0A0A0B] border-white/10 text-white pl-9"
                                    autoFocus
                                />
                            </div>
                            <Button
                                type="submit"
                                disabled={searching || !query.trim()}
                                data-testid="yt-search-submit"
                                className="bg-white text-black hover:bg-white/90"
                            >
                                {searching ? "Buscando..." : "Buscar"}
                            </Button>
                        </form>

                        <div className="max-h-80 overflow-y-auto space-y-1">
                            {results.map((r) => (
                                <button
                                    key={r.channel_id}
                                    data-testid={`yt-result-${r.channel_id}`}
                                    onClick={() => handleSelect(r)}
                                    className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 transition text-left border border-transparent hover:border-white/10"
                                >
                                    <img src={r.thumbnail} alt={r.title} className="w-12 h-12 rounded-full object-cover" />
                                    <div className="flex-1 min-w-0">
                                        <p className="font-semibold text-white truncate">{r.title}</p>
                                        <p className="text-xs text-white/50 line-clamp-1">{r.description}</p>
                                    </div>
                                </button>
                            ))}
                            {results.length === 0 && !searching && (
                                <div className="text-center text-white/30 text-sm py-8">
                                    {query ? "Sin resultados aún" : "Escribe para buscar"}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {step === 2 && selected && (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-[#0A0A0B] border border-white/10">
                            <img src={selected.thumbnail} alt="" className="w-12 h-12 rounded-full object-cover" />
                            <div>
                                <p className="text-xs text-white/40 uppercase tracking-widest">Canal YouTube</p>
                                <p className="text-sm font-medium text-white">{selected.title}</p>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="celeb-name" className="text-white/70">Nombre para mostrar</Label>
                            <Input
                                id="celeb-name"
                                data-testid="celeb-name-input"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="bg-[#0A0A0B] border-white/10 text-white"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label className="text-white/70">Color de marca</Label>
                            <div className="flex flex-wrap gap-2">
                                {PRESET_COLORS.map((c) => (
                                    <button
                                        key={c}
                                        type="button"
                                        data-testid={`color-${c.slice(1)}`}
                                        onClick={() => setColor(c)}
                                        className="relative w-10 h-10 rounded-lg ring-2 ring-transparent hover:ring-white/30 transition"
                                        style={{ background: c, ringColor: color === c ? c : undefined }}
                                    >
                                        {color === c && (
                                            <Check className="w-4 h-4 text-black absolute inset-0 m-auto" strokeWidth={3} />
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex justify-between pt-2">
                            <Button
                                variant="ghost"
                                onClick={() => setStep(1)}
                                className="text-white/60 hover:text-white hover:bg-white/5"
                            >
                                ← Volver
                            </Button>
                            <Button
                                onClick={handleSave}
                                disabled={saving || !name}
                                data-testid="save-celebrity-btn"
                                className="text-black font-bold"
                                style={{ background: color }}
                            >
                                {saving ? "Guardando..." : "Agregar personaje"}
                            </Button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
};

export default AddCelebrityDialog;
