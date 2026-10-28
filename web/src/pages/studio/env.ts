import { useMemo } from "react";
import type { Platform } from "@/types";
import { parseTerms } from "@/lib/guard";
import { useDesk } from "@/state/store";
import { useTz } from "@/state/hooks";

/** What the Studio's blocks need from the desk: limits, your lists, the kit and your guard terms. */
export function useStudioEnv() {
  const view = useDesk((s) => s.view);
  const guardRaw = useDesk((s) => s.guardTerms);
  const tz = useTz();
  return useMemo(() => {
    const settings = (view?.settings ?? {}) as Record<string, any>;
    const kit = view?.studio ?? null;
    const name = view?.meta?.display_name || settings.display_name || "";
    return {
      kit,
      name,
      tz,
      visualName: (p: Platform) => (p === "linkedin" ? settings.visuals?.name_linkedin : settings.visuals?.name_x) || name,
      accent: (settings.visuals?.accent as string | undefined) ?? null,
      xLimit: settings.platforms?.x?.premium ? (settings.platforms?.x?.premium_char_limit ?? 25000) : (kit?.x_limit ?? settings.platforms?.x?.char_limit ?? 280),
      liLimit: (settings.platforms?.linkedin?.char_limit as number | undefined) ?? 3000,
      fold: kit?.fold ?? settings.platforms?.linkedin?.fold_chars ?? 210,
      threadMin: (settings.platforms?.x?.thread_min as number | undefined) ?? 3,
      threadMax: (settings.platforms?.x?.thread_max as number | undefined) ?? 7,
      avoid: [...(kit?.avoid ?? settings.voice?.avoid_phrases ?? []), ...(view?.voice?.avoid ?? [])] as string[],
      bait: (kit?.bait ?? settings.voice?.bait_phrases ?? []) as string[],
      pillars: (kit?.pillars ?? {}) as Record<string, Record<string, string>>,
      guardTerms: parseTerms(guardRaw),
    };
  }, [view, guardRaw, tz]);
}

export type StudioEnv = ReturnType<typeof useStudioEnv>;
