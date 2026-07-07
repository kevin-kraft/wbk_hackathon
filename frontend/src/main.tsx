import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadConfig } from "./config/runtime";
import "./index.css";
import App from "./App";

// Load runtime endpoint config (public/config.json + overrides) BEFORE first render
// so every component sees resolved service URLs synchronously.
loadConfig().finally(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
