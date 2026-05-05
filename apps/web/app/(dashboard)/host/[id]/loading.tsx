import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex items-center justify-center h-[calc(100vh-64px)] gap-2 text-[#497f8b] dark:text-[var(--strix-text-muted)]">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span className="text-[12px]">Loading host detail…</span>
    </div>
  );
}
