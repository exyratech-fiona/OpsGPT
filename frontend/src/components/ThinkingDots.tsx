/** Three-dot "thinking" indicator shown before the first token arrives. */
export function ThinkingDots() {
  return (
    <div className="mx-auto flex max-w-3xl gap-4 px-4 py-5">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-gemini text-xs font-semibold text-white shadow-glow">
        Ops
      </div>
      <div className="flex items-center gap-1.5 pt-2">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 animate-bounce-dot rounded-full bg-ops-muted"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </div>
    </div>
  );
}
