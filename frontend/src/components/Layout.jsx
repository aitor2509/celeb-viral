import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import AddCelebrityDialog from "./AddCelebrityDialog";
import { Toaster } from "@/components/ui/sonner";

const Layout = () => {
    const [addOpen, setAddOpen] = useState(false);

    return (
        <div className="min-h-screen flex bg-[#0A0A0B] text-white">
            <Sidebar onAddCelebrity={() => setAddOpen(true)} />
            <main className="flex-1 min-w-0 flex flex-col">
                <Header onAddCelebrity={() => setAddOpen(true)} />
                <div className="flex-1">
                    <Outlet />
                </div>
            </main>
            <AddCelebrityDialog open={addOpen} onOpenChange={setAddOpen} />
            <Toaster theme="dark" richColors position="bottom-right" />
        </div>
    );
};

export default Layout;
