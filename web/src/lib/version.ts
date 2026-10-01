// The desk's own version: which build is running, and whether a newer one has been deployed since.
export type Build = { id: string; at: string };

export const BUILD: Build = typeof __BUILD__ === "undefined" ? { id: "dev", at: "" } : __BUILD__;

/** The deployed build (dist/version.json), never from a cache. Null when it can't be read (offline, dev). */
export async function deployedBuild(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<Build | null> {
  try {
    const res = await fetchImpl(`./version.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return null;
    const v = (await res.json()) as Partial<Build> | null;
    return typeof v?.id === "string" && v.id ? { id: v.id, at: String(v.at ?? "") } : null;
  } catch {
    return null;
  }
}
