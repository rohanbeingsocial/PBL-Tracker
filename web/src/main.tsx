import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import { Agentation } from "agentation";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { applyTheme, savedTheme } from "./theme";

applyTheme(savedTheme());   // before the first paint, so the page doesn't flash the other theme

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    {/* Feedback toolbar for `npm run dev` only; notes go to agentation-mcp on :4747 */}
    {import.meta.env.DEV && <Agentation endpoint="http://localhost:4747" />}
  </StrictMode>,
);
