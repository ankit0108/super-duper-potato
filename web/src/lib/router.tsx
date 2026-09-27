// Hash routing: works on any static host (GitHub Pages, Cloudflare Pages, a local file server).
import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from "react";

export type Route = { path: string; parts: string[]; query: URLSearchParams };

function parse(): Route {
  const raw = (typeof window === "undefined" ? "" : window.location.hash).replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  return { path: path || "/", parts: path.split("/").filter(Boolean), query: new URLSearchParams(qs ?? "") };
}

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  const hash = to.startsWith("#") ? to : `#${to}`;
  if (opts.replace) window.location.replace(hash);
  else window.location.hash = hash;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string };

export function Link({ to, onClick, ...rest }: LinkProps) {
  const href = to.startsWith("#") ? to : `#${to}`;
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
  };
  return <a href={href} onClick={handle} {...rest} />;
}
