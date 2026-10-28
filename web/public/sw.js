// PBS Desk service worker: the app shell works offline. GitHub API calls are never cached here
// (the desk keeps its own copy of desk.json with ETags). Each deploy registers it as sw.js?v=<build>, so every
// build gets its own cache and the old one is deleted when the new worker takes over.
const VERSION = new URL(self.location.href).searchParams.get("v") || "1";
const CACHE = `pbs-desk-${VERSION}`;
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon.svg", "./theme.js"];
// Android's Share → PBS Desk (share_target in the manifest) posts here; the Studio picks it up (src/lib/studio/shared.ts).
const SHARE_CACHE = "pbs-share";

self.addEventListener("install", (event) => {
  // "reload": straight from the server, not an HTTP-cached copy of the previous deploy.
  const fresh = SHELL.map((u) => new Request(u, { cache: "reload" }));
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(fresh)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== SHARE_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function keepShared(req) {
  const form = await req.formData();
  const files = form.getAll("images").filter((f) => f && typeof f !== "string" && f.size > 0).slice(0, 10);
  const cache = await caches.open(SHARE_CACHE);
  for (const old of await cache.keys()) await cache.delete(old);
  const text = (k) => String(form.get(k) || "").slice(0, 20000);
  await cache.put("shared/meta", new Response(JSON.stringify({ title: text("title"), text: text("text"), url: text("url"), files: files.length })));
  await Promise.all(files.map((f, i) => cache.put(`shared/file-${i}`, new Response(f, { headers: { "content-type": f.type || "application/octet-stream" } }))));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method === "POST" && url.origin === self.location.origin && url.pathname.endsWith("/share-target")) {
    const studio = new URL("./#/studio?shared=1", self.registration.scope).href;
    event.respondWith(keepShared(req).then(() => Response.redirect(studio, 303), () => Response.redirect(studio, 303)));
    return;
  }
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/version.json")) return; // the update check: always the network, never stored
  if (req.mode === "navigate") {
    // Network first, revalidated (GitHub Pages lets browsers cache pages for 10 minutes): a new deploy shows up
    // on the next open, and the cached page is only for offline.
    event.respondWith(
      fetch(new Request(req.url, { cache: "no-cache", credentials: "same-origin" }))
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy));
          return res;
        })
        .catch(() => caches.match("./index.html")),
    );
    return;
  }
  if (url.pathname.includes("/assets/")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
            return res;
          }),
      ),
    );
    return;
  }
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req)),
  );
});
