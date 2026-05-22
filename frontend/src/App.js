import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppProvider } from "@/lib/AppContext";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import CelebrityDetail from "@/pages/CelebrityDetail";

function App() {
    return (
        <div className="App">
            <AppProvider>
                <BrowserRouter>
                    <Routes>
                        <Route element={<Layout />}>
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/celebrity/:id" element={<CelebrityDetail />} />
                        </Route>
                    </Routes>
                </BrowserRouter>
            </AppProvider>
        </div>
    );
}

export default App;
