import { useState } from "react";
import { KeyRound, Lock, PlayCircle } from "lucide-react";
import { verifyConnection, type GitHubConnection } from "@/lib/github";
import { navigate } from "@/lib/router";
import { newId } from "@/lib/storage";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";
import { Banner, Panel } from "@/components/ui/Feedback";
import { Field, Input } from "@/components/ui/Field";

const env = import.meta.env as Record<string, string | undefined>;

export function Connect() {
  const connect = useDesk((s) => s.connect);
  const existing = useDesk((s) => s.connection);
  const prev = existing?.mode === "github" ? existing : null;
  const [dataRepo, setDataRepo] = useState(prev?.dataRepo ?? env.VITE_DEFAULT_DATA_REPO ?? "");
  const [dataBranch, setDataBranch] = useState(prev?.dataBranch ?? "main");
  const [codeRepo, setCodeRepo] = useState(prev?.codeRepo ?? env.VITE_DEFAULT_CODE_REPO ?? "");
  const [codeRef, setCodeRef] = useState(prev?.codeRef ?? "main");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const repoOk = (r: string) => /^[\w.-]+\/[\w.-]+$/.test(r.trim());

  const submit = async () => {
    setBusy(true);
    setProblems([]);
    const conn: GitHubConnection = {
      mode: "github",
      dataRepo: dataRepo.trim(),
      dataBranch: dataBranch.trim() || "main",
      codeRepo: codeRepo.trim(),
      codeRef: codeRef.trim() || "main",
      workflow: "pbs.yml",
      token: token.trim() || prev?.token || "",
      device: prev?.device ?? newId("dev").slice(-8),
    };
    const found = await verifyConnection(conn);
    setBusy(false);
    if (found.length) {
      setProblems(found);
      return;
    }
    await connect(conn);
    navigate("/");
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 py-4">
      <header className="text-center">
        <img src="./icon.svg" alt="" className="mx-auto mb-3 size-12 rounded-xl" />
        <h1 className="text-2xl font-semibold tracking-tight">Connect your desk</h1>
        <p className="mx-auto mt-1 max-w-lg text-sm text-muted">
          The desk reads and writes your private data repo on GitHub. There is no server: your token stays in this browser.
        </p>
      </header>
      <Panel>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label="Private data repo" htmlFor="c-data" hint="owner/name, for example ankit0108/pbs-data" error={dataRepo && !repoOk(dataRepo) ? "Use owner/name." : undefined}>
              <Input id="c-data" value={dataRepo} onChange={(e) => setDataRepo(e.target.value)} autoComplete="off" spellCheck={false} />
            </Field>
            <Field label="Branch" htmlFor="c-branch">
              <Input id="c-branch" value={dataBranch} onChange={(e) => setDataBranch(e.target.value)} />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label="Pipeline repo" htmlFor="c-code" hint="Where .github/workflows/pbs.yml lives" error={codeRepo && !repoOk(codeRepo) ? "Use owner/name." : undefined}>
              <Input id="c-code" value={codeRepo} onChange={(e) => setCodeRepo(e.target.value)} autoComplete="off" spellCheck={false} />
            </Field>
            <Field label="Branch" htmlFor="c-ref">
              <Input id="c-ref" value={codeRef} onChange={(e) => setCodeRef(e.target.value)} />
            </Field>
          </div>
          <Field
            label="Fine-grained personal access token"
            htmlFor="c-token"
            hint={
              <>
                Repository access: both repos above. Permissions: Contents read and write, Actions read and write. {prev && "Leave blank to keep the current token."}
              </>
            }
          >
            <Input id="c-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" placeholder={prev ? "•••• (unchanged)" : "github_pat_…"} />
          </Field>
          {problems.length > 0 && (
            <Banner tone="bad">
              <ul className="list-disc pl-4">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </Banner>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 text-[12.5px] text-muted">
              <Lock className="size-3.5" /> The token is saved on this device only. Use "Forget token" in Settings to remove it.
            </span>
            <Button type="submit" variant="primary" icon={<KeyRound className="size-4" />} loading={busy} disabled={!repoOk(dataRepo) || !repoOk(codeRepo) || (!token.trim() && !prev)}>
              Connect
            </Button>
          </div>
        </form>
      </Panel>
      <div className="text-center">
        <p className="text-sm text-muted">Not set up yet? The setup guide in the repo's docs/SETUP.md takes about 15 minutes.</p>
        <Button
          variant="ghost"
          className="mt-2"
          icon={<PlayCircle className="size-4" />}
          onClick={async () => {
            await connect({ mode: "demo", device: "demo" });
            navigate("/");
          }}
        >
          Explore the demo first
        </Button>
      </div>
    </div>
  );
}
