import { useEffect } from "react";
import { BUILD, deployedBuild } from "@/lib/version";
import { useDesk } from "./store";

const RELOADED_KEY = "pbs.reloadedFor";

/**
 * Notice a newer deployed desk: at start, every 15 minutes and whenever the desk comes back into view (a
 * home-screen app or a tab left open otherwise keeps running old code for days). Coming back with nothing unsent
 * and nothing being typed reloads straight into the new version, once per version; otherwise a banner offers it.
 */
export function useUpdateCheck(enabled: boolean = import.meta.env.PROD) {
  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    const check = async (comingBack: boolean) => {
      const latest = await deployedBuild();
      if (stopped || !latest || latest.id === BUILD.id) return;
      useDesk.setState({ update: latest });
      // Never mid-task: something unsent, a dialog open (a skip note being typed) or a field in use.
      const unsent = useDesk.getState().outbox.some((i) => i.state === "pending" || i.state === "sending");
      const typing = !!document.querySelector("dialog[open]") || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName ?? "");
      let done: string | null = null;
      try {
        done = sessionStorage.getItem(RELOADED_KEY);
      } catch {
        /* storage blocked: the banner still offers it */
      }
      if (comingBack && !unsent && !typing && done !== latest.id) {
        try {
          sessionStorage.setItem(RELOADED_KEY, latest.id);
        } catch {
          return;
        }
        window.location.reload();
      }
    };
    void check(false);
    const timer = setInterval(() => void check(false), 15 * 60_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") void check(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled]);
}
