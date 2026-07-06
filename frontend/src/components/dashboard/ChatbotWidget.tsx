import { useState } from "react";
import { Bot, X } from "lucide-react";
import { GrcChat } from "./GrcChat";
import { useDashColors } from "./DashTheme";

/** Floating bottom-right compliance chatbot (launcher bubble + popup panel). */
export function ChatbotWidget() {
  const C = useDashColors();
  const [open, setOpen] = useState(false);
  const grad = "linear-gradient(135deg,#10b981,#059669)";

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-5 z-50 flex w-[380px] max-w-[92vw] flex-col overflow-hidden rounded-2xl shadow-2xl"
          style={{ background: C.card, border: `1px solid ${C.border}` }}>
          <div className="flex items-center gap-2 px-4 py-3" style={{ background: grad }}>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
              <Bot size={18} className="text-white" />
            </span>
            <div className="text-white">
              <div className="text-[13px] font-semibold leading-tight">Compliance Assistant</div>
              <div className="text-[10px] opacity-85">Ask about your GRC posture</div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close" className="ml-auto text-white/80 hover:text-white">
              <X size={18} />
            </button>
          </div>
          <div className="px-3 pb-3 pt-2">
            <GrcChat />
          </div>
        </div>
      )}

      <button onClick={() => setOpen((o) => !o)} aria-label="Compliance assistant"
        className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full text-white shadow-2xl transition hover:scale-105 active:scale-95"
        style={{ background: grad, boxShadow: "0 8px 24px rgba(16,185,129,.45)" }}>
        {open ? <X size={24} /> : <Bot size={26} />}
        {!open && <span className="absolute right-0 top-0 h-3 w-3 animate-pulse rounded-full bg-white" />}
      </button>
    </>
  );
}
