import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { AppProvider } from "./store";
import { Sidebar } from "./components/Sidebar";
import Home from "./pages/Home";
import Dataset from "./pages/Dataset";
import Settings from "./pages/Settings";

function App() {
  return (
    <div className="h-full flex">
      <Sidebar />
      <main className="flex-1 min-w-0 h-full overflow-y-auto">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/d/:id" element={<Dataset />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
