import { useEffect, useState } from "react";
import { useRoute } from "@/lib/router";
import { useDesk } from "@/state/store";
import { AppShell } from "@/components/shell/AppShell";
import { Dialog } from "@/components/ui/Dialog";
import { Empty, Kbd, Spinner, Toasts } from "@/components/ui/Feedback";
import { Board } from "@/pages/Board";
import { CardPage } from "@/pages/CardPage";
import { Connect } from "@/pages/Connect";
import { History } from "@/pages/History";
import { Insights } from "@/pages/Insights";
import { Metrics } from "@/pages/Metrics";
import { Requests } from "@/pages/Requests";
import { Settings } from "@/pages/Settings";
import { Sources } from "@/pages/Sources";
import { Stances } from "@/pages/Stances";
import { System } from "@/pages/System";

const TITLES: Record<string, string> = {
  "": "Board",
  card: "Card",
  requests: "Requests",
  stances: "Stances",
  metrics: "Metrics",
  insights: "Insights",
  sources: "Sources",
  history: "History",
  system: "System",
  settings: "Settings",
  connect: "Connect",
};

function Page({ parts }: { parts: string[] }) {
  switch (parts[0] ?? "") {
    case "":
      return <Board />;
    case "card":
      return parts[1] ? <CardPage id={decodeURIComponent(parts[1])} /> : <Board />;
    case "requests":
      return <Requests />;
    case "stances":
      return <Stances />;
    case "metrics":
      return <Metrics />;
    case "insights":
      return <Insights />;
    case "sources":
      return <Sources />;
    case "history":
      return <History />;
    case "system":
      return <System />;
    case "settings":
      return <Settings />;
    default:
      return <Empty title="Page not found">That link doesn't match anything on the desk.</Empty>;
  }
}

function HelpDialog() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "?") setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const rows: Array<[string, string]> = [
    ["j / k", "Next / previous card on the board"],
    ["Enter", "Open the focused card"],
    ["Ctrl/⌘ + Enter", "Mark the open card as posted"],
    ["Ctrl/⌘ + Shift + C", "Copy the open card's text"],
    ["?", "Show this help"],
  ];
  return (
    <Dialog open={open} onClose={() => setOpen(false)} title="Keyboard shortcuts">
      <dl className="space-y-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-4 text-sm">
            <dt>
              <Kbd>{k}</Kbd>
            </dt>
            <dd className="text-muted">{v}</dd>
          </div>
        ))}
      </dl>
    </Dialog>
  );
}

export function App() {
  const route = useRoute();
  const connection = useDesk((s) => s.connection);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void useDesk
      .getState()
      .init()
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    document.title = `${TITLES[route.parts[0] ?? ""] ?? "PBS"} · PBS Desk`;
  }, [route.path]);

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner label="Opening your desk" />
      </div>
    );
  }
  const onConnect = route.parts[0] === "connect" || !connection;
  return (
    <>
      {onConnect ? (
        <main className="min-h-full px-4">
          <Connect />
        </main>
      ) : (
        <AppShell>
          <Page parts={route.parts} />
        </AppShell>
      )}
      <Toasts />
      <HelpDialog />
    </>
  );
}
