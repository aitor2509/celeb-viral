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

    const silentRefreshAll = useCallback(async () => {
        try {
            await api.post("/refresh-all");
        } catch (e) {
            // silent - no toast, no UI block
            console.debug("Background refresh-all failed", e);
        }
    }, []);

    useEffect(() => {
        (async () => {
            await Promise.all([loadCelebrities(), loadNotifications()]);
            setLoading(false);
        })();

        // Poll notifications every 20s (was 60s)
        const notifInterval = setInterval(loadNotifications, 20000);
        // Detect new celebrities/accounts every 30s
        const celebInterval = setInterval(loadCelebrities, 30000);
        // Silent backend refresh every 5 minutes
        const refreshInterval = setInterval(silentRefreshAll, 5 * 60 * 1000);

        return () => {
            clearInterval(notifInterval);
            clearInterval(celebInterval);
            clearInterval(refreshInterval);
        };
    }, [loadCelebrities, loadNotifications, silentRefreshAll]);

    useEffect(() => {
        document.documentElement.style.setProperty("--celebrity-color", selectedColor);
    }, [selectedColor]);

    const markAllRead = useCallback(async () => {
        await api.post("/notifications/read-all");
        await loadNotifications();
    }, [loadNotifications]);

    const markRead = useCallback(async (id) => {
        await api.post(`/notifications/${id}/read`);
        await loadNotifications();
    }, [loadNotifications]);

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
    }), [celebrities, notifications, unread, selectedColor, loadCelebrities, loadNotifications, markAllRead, markRead, loading]);

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
