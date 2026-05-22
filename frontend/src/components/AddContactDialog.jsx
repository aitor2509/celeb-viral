import React, { useState } from "react";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Phone } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const AddContactDialog = ({ open, onOpenChange, celebrity }) => {
    const [phone, setPhone] = useState("");
    const [name, setName] = useState("");
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        if (!phone || !celebrity) return;
        setSaving(true);
        try {
            await api.post("/contacts", {
                celebrity_id: celebrity.id, phone, name: name || null,
            });
            toast.success("Contacto registrado · recibirás notificaciones in-app");
            setPhone(""); setName("");
            onOpenChange(false);
        } catch (err) {
            toast.error("Error al guardar");
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-[#111113] border-white/10 text-white max-w-md" data-testid="add-contact-dialog">
                <DialogHeader>
                    <DialogTitle className="font-display text-2xl tracking-tight flex items-center gap-2">
                        <Phone className="w-5 h-5 celeb-text" /> Suscribirse a alertas
                    </DialogTitle>
                    <DialogDescription className="text-white/50">
                        Te avisamos cuando {celebrity?.name} suba un nuevo video o haya algo viral.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3">
                    <div>
                        <Label className="text-white/70">Nombre</Label>
                        <Input
                            data-testid="contact-name-input"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Opcional"
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1"
                        />
                    </div>
                    <div>
                        <Label className="text-white/70">Teléfono *</Label>
                        <Input
                            data-testid="contact-phone-input"
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            placeholder="+52 55 1234 5678"
                            className="bg-[#0A0A0B] border-white/10 text-white mt-1"
                        />
                        <p className="text-[11px] text-white/40 mt-1">
                            Por ahora las alertas se entregan en la app. SMS próximamente.
                        </p>
                    </div>
                </div>

                <div className="flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-white/60 hover:text-white hover:bg-white/5">
                        Cancelar
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={saving || !phone}
                        data-testid="save-contact-btn"
                        className="celeb-bg text-black font-bold"
                    >
                        {saving ? "Guardando..." : "Suscribirme"}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default AddContactDialog;
