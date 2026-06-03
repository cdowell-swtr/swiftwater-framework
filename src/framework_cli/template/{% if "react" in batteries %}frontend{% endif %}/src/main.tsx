import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initRum } from "./observability/rum";

initRum();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
