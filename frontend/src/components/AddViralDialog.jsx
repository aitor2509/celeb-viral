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
import { Textarea } from "@/components/ui/textarea";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { toast } from "sonner";

const TAGS = [
    { value: "viral", label: "Viral" },
    { value: "funa", label: "Funa" },
    { value: "colab", label: "Colaboración" },
    { value: "noticia", label: "Noticia" },
];

const AddViralDialog = ({ open, onOpenChange, celebrity, onAdded }) => {
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [url, setUrl] = useState("");
    const [imageUrl, setImageUrl] = useState("");
    const [tag, setTag] = useState("viral");
    const [saving, setSaving] = useState(false);

    const reset = () => {
        setTitle(""); setDescription(""); setUrl(""); setImageUrl(""); setTag("viral");
    };

    const handleSave = async () => {
        if (!title || !celebrity) return;
        setSaving(true);
        try {
            await api.post(`/celebrities/${celebrity.id}/virals`, {
                title, description, source_url: url || null, image_url: imageUrl || null, tag,
            });
            toast.success("Entrada agregada");
            onAdded?.();
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
            <DialogContent className="bg-[#111113] border-white/10 text-white max-w-lg" data-testid="add-viral-dialog">
                <DialogHeader>
                    <DialogTitle className="font-display text-2xl tracking-tight">
                        Nueva entrada {celebrity ? `· ${celebrity.name}` : ""}
                    </DialogTitle>
                    <DialogDescription className="text-white/50">
                        Registra contenido viral, funas, colabs o noticias.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3">
                    <div>
                        <Label className="text-white/70">Tipo</Label>
                        <Select value={tag} onValueChange={setTag}>
                            <SelectTrigger data-testid="viral-tag-select" className="bg-[#0A0A0B] border-white/10 text-white mt-1">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-[#111113] border-white/10 text-white">
                                {TAGS.map((t) => (
                                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div>
                        <Label className="text-white/70">Título *</Label>
                        <Input
                            data-testid="viral-title-input"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="ej. Funa por chiste polémico"
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1"
                        />
                    </div>

                    <div>
                        <Label className="text-white/70">Descripción</Label>
                        <Textarea
                            data-testid="viral-desc-input"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Contexto del contenido viral..."
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1 min-h-[80px]"
                        />
                    </div>

                    <div>
                        <Label className="text-white/70">URL fuente</Label>
                        <Input
                            data-testid="viral-url-input"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://..."
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1"
                        />
                    </div>

                    <div>
                        <Label className="text-white/70">URL imagen (opcional)</Label>
                        <Input
                            data-testid="viral-image-input"
                            value={imageUrl}
                            onChange={(e) => setImageUrl(e.target.value)}
                            placeholder="https://..."
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1"
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-white/60 hover:text-white hover:bg-white/5">
                        Cancelar
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={saving || !title}
                        data-testid="save-viral-btn"
                        className="celeb-bg text-black font-bold"
                    >
                        {saving ? "Guardando..." : "Guardar"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default AddViralDialog;
