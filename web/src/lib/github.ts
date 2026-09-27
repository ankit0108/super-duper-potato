// The desk's only backend: the GitHub REST API, called from the browser with a fine-grained token that
// never leaves this device. Reads the private data repo, writes new files under inbox/, and starts the
// pipeline workflow in the code repo.

export type GitHubConnection = {
  mode: "github";
  dataRepo: string; // owner/name (private)
  dataBranch: string;
  codeRepo: string; // owner/name (where .github/workflows/pbs.yml lives)
  workflow: string; // pbs.yml
  codeRef: string; // branch to run the workflow from
  token: string;
  device: string;
};

export type DemoConnection = { mode: "demo"; device: string };
export type Connection = GitHubConnection | DemoConnection;

export class GitHubError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter?: number,
  ) {
    super(message);
  }
  get rateLimited() {
    return this.status === 429 || (this.status === 403 && /rate limit/i.test(this.message));
  }
}

export type WorkflowRun = {
  id: number;
  status: "queued" | "in_progress" | "completed" | "waiting" | "requested" | "pending";
  conclusion: string | null;
  created_at: string;
  updated_at: string;
  run_started_at?: string;
  html_url: string;
  event: string;
};

const API = "https://api.github.com";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function utf8ToBase64(text: string): string {
  return bytesToBase64(new TextEncoder().encode(text));
}

export function bytesToBase64(bytes: Uint8Array): string {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

export function encodePath(path: string): string {
  return path
    .split("/")
    .map((p) => encodeURIComponent(p))
    .join("/");
}

export class GitHub {
  rateRemaining: number | null = null;

  constructor(
    private conn: GitHubConnection,
    private fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async req(path: string, init: RequestInit & { accept?: string } = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${this.conn.token}`);
    headers.set("X-GitHub-Api-Version", "2022-11-28");
    headers.set("Accept", init.accept ?? "application/vnd.github+json");
    let res: Response;
    try {
      res = await this.fetchImpl(`${API}${path}`, { ...init, headers, cache: "no-store" });
    } catch {
      throw new GitHubError("Network error: can't reach GitHub", 0);
    }
    const remaining = res.headers.get("x-ratelimit-remaining");
    if (remaining != null) this.rateRemaining = Number(remaining);
    if (res.ok || res.status === 304) return res;
    let message = `GitHub ${res.status}`;
    try {
      const body = await res.json();
      if (body?.message) message = `${message}: ${body.message}`;
    } catch {
      /* ignore */
    }
    const ra = res.headers.get("retry-after");
    throw new GitHubError(message, res.status, ra ? Number(ra) : undefined);
  }

  /** Raw file from the data repo. 304 when the ETag matches; null text on 404. */
  async getRaw(path: string, etag?: string | null): Promise<{ status: number; text: string | null; etag: string | null }> {
    const { dataRepo, dataBranch } = this.conn;
    const headers: Record<string, string> = {};
    if (etag) headers["If-None-Match"] = etag;
    try {
      const res = await this.req(`/repos/${dataRepo}/contents/${encodePath(path)}?ref=${encodeURIComponent(dataBranch)}`, {
        headers,
        accept: "application/vnd.github.raw+json",
      });
      if (res.status === 304) return { status: 304, text: null, etag: etag ?? null };
      return { status: res.status, text: await res.text(), etag: res.headers.get("etag") };
    } catch (e) {
      if (e instanceof GitHubError && e.status === 404) return { status: 404, text: null, etag: null };
      throw e;
    }
  }

  async listDir(path: string): Promise<Array<{ name: string; path: string; sha: string; type: string; size: number }>> {
    const { dataRepo, dataBranch } = this.conn;
    try {
      const res = await this.req(`/repos/${dataRepo}/contents/${encodePath(path)}?ref=${encodeURIComponent(dataBranch)}`);
      const body = await res.json();
      return Array.isArray(body) ? body : [];
    } catch (e) {
      if (e instanceof GitHubError && e.status === 404) return [];
      throw e;
    }
  }

  /** Create a new file on the data branch. Retries conflicts (another write landed) and server errors. */
  async createFile(path: string, base64: string, message: string): Promise<void> {
    const { dataRepo, dataBranch } = this.conn;
    let lastError: unknown;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        await this.req(`/repos/${dataRepo}/contents/${encodePath(path)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, content: base64, branch: dataBranch }),
        });
        return;
      } catch (e) {
        lastError = e;
        if (!(e instanceof GitHubError)) throw e;
        if (e.status === 422 && /sha/i.test(e.message)) return; // already exists: an earlier attempt landed
        if (![0, 409, 500, 502, 503, 504].includes(e.status) && !e.rateLimited) throw e;
        await sleep((e.retryAfter ? e.retryAfter * 1000 : 800) * (attempt + 1));
      }
    }
    throw lastError;
  }

  async repoInfo(repo: string): Promise<{ private: boolean; permissions?: { push?: boolean; pull?: boolean }; default_branch: string }> {
    const res = await this.req(`/repos/${repo}`);
    return res.json();
  }

  async dispatch(inputs: Record<string, string | boolean> = {}): Promise<void> {
    const { codeRepo, workflow, codeRef } = this.conn;
    await this.req(`/repos/${codeRepo}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: codeRef, inputs }),
    });
  }

  async latestRuns(n = 5): Promise<WorkflowRun[]> {
    const { codeRepo, workflow } = this.conn;
    const res = await this.req(`/repos/${codeRepo}/actions/workflows/${encodeURIComponent(workflow)}/runs?per_page=${n}`);
    const body = await res.json();
    return body?.workflow_runs ?? [];
  }

  async workflowState(): Promise<string> {
    const { codeRepo, workflow } = this.conn;
    const res = await this.req(`/repos/${codeRepo}/actions/workflows/${encodeURIComponent(workflow)}`);
    return (await res.json())?.state ?? "unknown";
  }

  async enableWorkflow(): Promise<void> {
    const { codeRepo, workflow } = this.conn;
    await this.req(`/repos/${codeRepo}/actions/workflows/${encodeURIComponent(workflow)}/enable`, { method: "PUT" });
  }
}

/** Check a new connection: token works, data repo is private and writable, workflow reachable. */
export async function verifyConnection(conn: GitHubConnection, fetchImpl?: typeof fetch): Promise<string[]> {
  const gh = new GitHub(conn, fetchImpl);
  const problems: string[] = [];
  try {
    const data = await gh.repoInfo(conn.dataRepo);
    if (!data.private) problems.push(`${conn.dataRepo} is public. Your drafts and answers must live in a private repo.`);
    if (data.permissions && !data.permissions.push) problems.push(`The token can't write to ${conn.dataRepo} (needs Contents: read and write).`);
  } catch (e) {
    const status = e instanceof GitHubError ? e.status : 0;
    problems.push(
      status === 401
        ? "The token was rejected. Check that it hasn't expired."
        : status === 404
          ? `Can't see ${conn.dataRepo}. Check the name and that the token includes this repository.`
          : `Couldn't reach ${conn.dataRepo} (${(e as Error).message}).`,
    );
    return problems;
  }
  try {
    await gh.workflowState();
  } catch (e) {
    const status = e instanceof GitHubError ? e.status : 0;
    problems.push(
      status === 404
        ? `Can't find the workflow ${conn.workflow} in ${conn.codeRepo}. Include that repository in the token (Actions: read and write).`
        : `Couldn't check the workflow (${(e as Error).message}).`,
    );
  }
  return problems;
}
