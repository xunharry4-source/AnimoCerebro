import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { BrowserRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";

import App from "./App";
import i18n from "./i18nConfig";

const theme = createTheme();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nextProvider i18n={i18n}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ThemeProvider>
    </I18nextProvider>
  </React.StrictMode>
);
