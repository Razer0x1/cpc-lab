"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Logo, Wordmark } from "@/components/brand";
import { useAuth } from "@/components/auth-context";
import { Button, Card, CardContent, Field, Input } from "@/components/ui/primitives";

export default function LoginPage() {
  const { me, loading, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("admin@cpc.lab");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && me) router.replace("/");
  }, [loading, me, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center px-4">
      {/* brand glow */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute left-1/2 top-0 h-72 w-[42rem] -translate-x-1/2 rounded-full bg-[#18A0FB]/10 blur-3xl" />
        <div className="absolute right-1/4 bottom-0 h-64 w-[32rem] translate-x-1/4 rounded-full bg-[#B02FF5]/10 blur-3xl" />
      </div>

      <main className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo size={72} />
          <Wordmark className="items-center" />
          <p className="max-w-xs text-xs text-muted-foreground">
            Cross-paradigm neural compression research — from literature to hypotheses to measured, reproducible runs.
          </p>
        </div>

        <Card>
          <CardContent className="p-6 pt-0">
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <Field label="Email">
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@cpc.lab"
                />
              </Field>
              <Field label="Password" hint="Seeded admin default: admin@cpc.lab / change-me-admin (set via ADMIN_EMAIL / ADMIN_PASSWORD env)">
                <Input
                  type="password"
                  required
                  minLength={6}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </Field>
              {error ? <p className="text-xs text-red-500">{error}</p> : null}
              <Button type="submit" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          New to CPC Lab?{" "}
          <Link
            href="/register"
            className="font-medium text-foreground underline-offset-2 hover:underline"
          >
            Create an account
          </Link>
        </p>

        <p className="mt-6 text-center text-2xs text-muted-foreground">
          &copy; 2026 <span className="font-medium text-foreground">Razer0x1</span> — All rights reserved.
        </p>
      </main>
    </div>
  );
}
