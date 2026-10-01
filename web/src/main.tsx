import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App";
import { BUILD } from "./lib/version";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    // The build in the URL gives every deploy its own worker and cache, so old app files can't linger.
    navigator.serviceWorker.register(`./sw.js?v=${encodeURIComponent(BUILD.id)}`).catch(() => {
      /* offline support is a bonus, never a requirement */
    });
  });
}
