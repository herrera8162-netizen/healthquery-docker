import { useCallback, useEffect, useState } from "react";
import { Copy, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

type AuthStatus = { enrolled: boolean };
type AuthSetup = { secret: string; otpauth_uri: string };
type GateState = "loading" | "setup" | "login" | "authenticated";

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/auth${path}`, { credentials: "same-origin", ...init });
  if (!response.ok) throw new Error(`Authentication request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

function CodeInput({ value, onChange, onSubmit, disabled }: { value: string; onChange: (value: string) => void; onSubmit: () => void; disabled?: boolean }) {
  return <input autoFocus inputMode="numeric" pattern="[0-9]*" maxLength={6} value={value} disabled={disabled}
    onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
    onKeyDown={(event) => event.key === "Enter" && value.length === 6 && onSubmit()}
    placeholder="000000" className="w-full rounded-lg border border-border bg-secondary px-4 py-3 text-center font-mono text-2xl tracking-[0.5em] focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50" />;
}

function SetupScreen({ onComplete }: { onComplete: () => void }) {
  const [setupToken, setSetupToken] = useState("");
  const [setup, setSetup] = useState<AuthSetup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const beginSetup = useCallback(async () => {
    setError("");
    try {
      setSetup(await authFetch<AuthSetup>("/setup", { headers: { "X-HealthQuery-Setup-Token": setupToken } }));
    } catch {
      setError("The setup token was not accepted.");
    }
  }, [setupToken]);

  const confirm = useCallback(async () => {
    if (code.length !== 6) return;
    setSubmitting(true);
    setError("");
    try {
      await authFetch("/setup/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-HealthQuery-Setup-Token": setupToken },
        body: JSON.stringify({ code }),
      });
      onComplete();
    } catch {
      setError("The authenticator code was not accepted.");
      setCode("");
    } finally {
      setSubmitting(false);
    }
  }, [code, onComplete, setupToken]);

  return <div className="flex h-screen items-center justify-center bg-background p-4"><div className="w-full max-w-sm space-y-5">
    <div className="space-y-1 text-center"><ShieldCheck className="mx-auto h-8 w-8 text-primary" /><h1 className="text-lg font-semibold">Set up HealthQuery login</h1><p className="text-xs text-muted-foreground">Use the one-time setup token, then enroll an authenticator app.</p></div>
    {!setup ? <><input type="password" value={setupToken} onChange={(event) => setSetupToken(event.target.value)} placeholder="One-time setup token" className="w-full rounded-md border border-border bg-secondary px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" />
      <button onClick={beginSetup} disabled={!setupToken} className="w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-40">Start setup</button></> : <>
      <div className="flex justify-center rounded-lg bg-white p-4"><QRCodeSVG value={setup.otpauth_uri} size={200} /></div>
      <div className="flex items-center gap-2"><code className="flex-1 truncate rounded border border-border bg-secondary px-2 py-1.5 font-mono text-[10px]">{setup.secret}</code><button onClick={() => navigator.clipboard?.writeText(setup.secret)} className="p-1.5 text-muted-foreground" title="Copy manual entry key"><Copy className="h-3.5 w-3.5" /></button></div>
      <CodeInput value={code} onChange={setCode} onSubmit={confirm} disabled={submitting} />
      <button onClick={confirm} disabled={code.length !== 6 || submitting} className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-40">{submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Confirm setup</button></>}
    {error && <p className="text-center text-xs text-destructive">{error}</p>}
  </div></div>;
}

function LoginScreen({ onComplete }: { onComplete: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const login = useCallback(async () => {
    if (code.length !== 6) return;
    setSubmitting(true); setError("");
    try { await authFetch("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) }); onComplete(); }
    catch { setError("The authenticator code was not accepted."); setCode(""); }
    finally { setSubmitting(false); }
  }, [code, onComplete]);
  return <div className="flex h-screen items-center justify-center bg-background p-4"><div className="w-full max-w-sm space-y-6"><div className="space-y-1 text-center"><KeyRound className="mx-auto h-8 w-8 text-primary" /><h1 className="text-lg font-semibold">HealthQuery</h1><p className="text-xs text-muted-foreground">Enter your authenticator code</p></div><CodeInput value={code} onChange={setCode} onSubmit={login} disabled={submitting} /><button onClick={login} disabled={code.length !== 6 || submitting} className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-40">{submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Log in</button>{error && <p className="text-center text-xs text-destructive">{error}</p>}</div></div>;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("loading");
  const check = useCallback(async () => {
    try {
      const status = await authFetch<AuthStatus>("/status");
      if (!status.enrolled) { setState("setup"); return; }
      const me = await authFetch<{ authenticated: boolean }>("/me");
      setState(me.authenticated ? "authenticated" : "login");
    } catch { setState("login"); }
  }, []);
  useEffect(() => { check(); }, [check]);
  if (state === "loading") return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
  if (state === "setup") return <SetupScreen onComplete={check} />;
  if (state === "login") return <LoginScreen onComplete={check} />;
  return <>{children}</>;
}
