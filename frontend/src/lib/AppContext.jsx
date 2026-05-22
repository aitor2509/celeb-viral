import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import { api } from "@/lib/api";

const AppCtx = createContext(null);

export const AppProvider = ({ children }) => {
    const [celebrities, setCelebrities] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [unread, setUnread] = useState(0);
    const [selectedColor, setSelectedColor] = useState("#007AFF");
    const [loading, setLoading] = useState(true);

    const loadCelebrities = useCallback(async () => {
        try {
            const res = await api.get("/celebrities");
            setCelebrities(res.data);
        } catch (e) {
            console.error("Failed to load celebrities", e);
        }
    }, []);

    const loadNotifications = useCallback(async () => {
        try {
            const res = await api.get("/notifications");
            setNotifications(res.data.notifications);
            setUnread(res.data.unread);
        } catch (e) {
            console.error("Failed to load notifications", e);
        }
    }, []);

    useEffect(() => {
        (async () => {
            await Promise.all([loadCelebrities(), loadNotifications()]);
            setLoading(false);
        })();
        const interval = setInterval(loadNotifications, 60000);
        return () => clearInterval(interval);
    }, [loadCelebrities, loadNotifications]);

    useEffect(() => {
        document.documentElement.style.setProperty("--celebrity-color", selectedColor);
    }, [selectedColor]);

    const markAllRead = async () => {
        await api.post("/notifications/read-all");
        await loadNotifications();
    };

    const markRead = async (id) => {
        await api.post(`/notifications/${id}/read`);
        await loadNotifications();
    };

    const value = useMemo(() => ({
        celebrities,
        notifications,
        unread,
        selectedColor,
        setSelectedColor,
        loadCelebrities,
        loadNotifications,
        markAllRead,
        markRead,
        loading,
    }), [celebrities, notifications, unread, selectedColor, loadCelebrities, loadNotifications, loading]);

    return (
        <AppCtx.Provider value={value}>
            {children}
        </AppCtx.Provider>
    );
};

export const useApp = () => {
    const ctx = useContext(AppCtx);
    if (!ctx) throw new Error("useApp must be used within AppProvider");
    return ctx;
};
