"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Logo, Wordmark } from "@/components/brand";
import { useAuth } from "@/components/auth-context";
import { api } from "@/lib/api";
import { Button, Card, CardContent, Field, Input } from "@/components/ui/primitives";

type RegisterResponse = { id: string; email: string; workspace_id: string };

export default function RegisterPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Backend provisions a personal workspace for every new account,
      // so the user can start working immediately after registration.
      await api.post<RegisterResponse>("/api/v1/auth/register", {
        email: email.trim(),
        password,
        display_name: displayName.trim(),
      });
      await login(email.trim(), password); // auto sign-in with the same credentials
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
            Create your account — a personal workspace is provisioned automatically, so you can
            register a model and run experiments right away.
          </p>
        </div>

        <Card>
          <CardContent className="p-6 pt-0">
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <Field label="Display name" hint="Optional — shown in the sidebar and audit log">
                <Input
                  type="text"
                  autoComplete="name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Ada Lovelace"
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </Field>
              <Field label="Password" hint="At least 8 characters">
                <Input
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </Field>
              {error ? <p className="text-xs text-red-500">{error}</p> : null}
              <Button type="submit" disabled={busy}>
                {busy ? "Creating account…" : "Create account"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-foreground underline-offset-2 hover:underline">
            Sign in
          </Link>
        </p>

        <p className="mt-6 text-center text-2xs text-muted-foreground">
          &copy; 2026 <span className="font-medium text-foreground">Razer0x1</span> — All rights reserved.
        </p>
      </main>
    </div>
  );
}
