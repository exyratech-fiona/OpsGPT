import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DARK, LIGHT, type Palette } from "./theme";

type Mode = "light" | "dark";
const Ctx = createContext<{ mode: Mode; toggle: () => void; C: Palette }>({
  mode: "light",
  toggle: () => {},
  C: LIGHT,
});

export function DashThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem("opsgpt.dash.theme") as Mode) || "light");
  useEffect(() => {
    localStorage.setItem("opsgpt.dash.theme", mode);
  }, [mode]);
  const toggle = () => setMode((m) => (m === "light" ? "dark" : "light"));
  return <Ctx.Provider value={{ mode, toggle, C: mode === "dark" ? DARK : LIGHT }}>{children}</Ctx.Provider>;
}

export const useDash = () => useContext(Ctx);
export const useDashColors = () => useContext(Ctx).C;
