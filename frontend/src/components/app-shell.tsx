"use client";
/** Authenticated application shell: sidebar navigation, workspace header, app-wide footer. */
import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Compass, Lightbulb, Wrench, FlaskConical, Gauge, Share2, BookOpen,
  FileText, Settings2, LogOut, RefreshCw, Menu, X,
} from "lucide-react";
import { Logo, Wordmark } from "@/components/brand";
import { useAuth } from "@/components/auth-context";
import { Badge, Button, Select, Spinner } from "@/components/ui/primitives";
import { useConnection } from "@/lib/api";
import { cn } from "@/lib/utils";

const APP_VERSION = "0.1.0";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/explorer", label: "Research Explorer", icon: Compass },
  { href: "/hypotheses", label: "Hypothesis Studio", icon: Lightbulb },
  { href: "/workbench", label: "Compression Workbench", icon: Wrench },
  { href: "/experiments", label: "Experiment Lab", icon: FlaskConical },
  { href: "/benchmarks", label: "Benchmark Center", icon: Gauge },
  { href: "/graph", label: "Knowledge Graph", icon: Share2 },
  { href: "/papers", label: "Paper Library", icon: BookOpen },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { me, workspaces, loading, logout, switchWorkspace } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!loading && !me) router.replace("/login");
  }, [loading, me, router]);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  if (loading || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-muted-foreground">
        <Spinner /> Loading CPC Lab…
      </div>
    );
  }

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <Link href="/" className="flex items-center gap-2.5">
          <Logo size={34} />
          <Wordmark />
        </Link>
        <button
          type="button"
          className="ml-auto rounded-md p-1.5 text-muted-foreground hover:bg-secondary md:hidden"
          onClick={() => setNavOpen(false)}
          aria-label="Close navigation"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mx-4 mb-3 h-px bg-border" />
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2.5 scrollbar-thin">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
              isActive(item.href)
                ? "bg-secondary font-medium text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            )}
          >
            <item.icon className={cn("h-4 w-4", isActive(item.href) && "brand-gradient-text")} />
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="space-y-3 border-t border-border p-4">
        <div className="flex items-center justify-between gap-2 text-xs">
          <div className="min-w-0">
            <p className="truncate font-medium">{me.user.display_name || me.user.email}</p>
            <p className="truncate text-2xs text-muted-foreground">{me.user.email}</p>
          </div>
          <Badge tone={me.user.is_admin ? "violet" : "neutral"}>{me.role}</Badge>
        </div>
        <Select
          aria-label="Active workspace"
          className="h-9 text-xs"
          value={me.workspace.id}
          onChange={(e) => switchWorkspace(e.target.value)}
        >
          {(workspaces.length ? workspaces : [me.workspace]).map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </Select>
        <Button variant="ghost" size="sm" className="w-full justify-start text-muted-foreground" onClick={logout}>
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </Button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <ConnectionBanner />
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-border bg-card/40 md:block">
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {navOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setNavOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 border-r border-border bg-card">{sidebar}</aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur md:px-6">
          <button
            type="button"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary md:hidden"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className="flex flex-col">
            <span className="text-sm font-semibold">{titleFor(pathname)}</span>
            <span className="text-2xs text-muted-foreground">
              Workspace: {me.workspace.name}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-2 text-2xs text-muted-foreground">
            <Badge tone="blue">offline-capable</Badge>
            <Badge tone="neutral">measured metrics only</Badge>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6">{children}</main>

        {/* App-wide footer (brand requirement) */}
        <footer className="mt-8 border-t border-border bg-card/40 px-4 py-4 md:px-6">
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <Logo size={22} />
              <span className="text-xs text-muted-foreground">CPC Lab — Cross-Paradigm Compression workspace</span>
            </div>
            <p className="text-xs text-muted-foreground">&copy; 2026 <span className="font-medium text-foreground">Razer0x1</span> — All rights reserved.</p>
          </div>
        </footer>
      </div>
    </div>
  );
}

/** Offline-aware banner: fixed UI lane rendered when the backend is unreachable. */
function ConnectionBanner() {
  const { offline } = useConnection();
  if (!offline) return null;
  return (
    <div
      role="status"
      className="z-40 flex w-full items-center gap-2 border-b border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs text-amber-700 md:px-6"
    >
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
      </span>
      <span className="font-medium">Offline.</span>
      <span className="text-amber-700/80">
        Backend unreachable — showing cached data where available. Live runs, writes and streaming logs need a reachable
        API; pages reconnect automatically.
      </span>
    </div>
  );
}

function titleFor(pathname: string): string {
  const exact: Record<string, string> = {
    "/": "Overview",
    "/explorer": "Research Explorer",
    "/hypotheses": "Hypothesis Studio",
    "/workbench": "Compression Workbench",
    "/experiments": "Experiment Lab",
    "/benchmarks": "Benchmark Center",
    "/graph": "Knowledge Graph",
    "/papers": "Paper Library",
    "/reports": "Results & Reports",
    "/settings": "Settings",
  };
  if (exact[pathname]) return exact[pathname];
  if (pathname.startsWith("/experiments/")) return "Experiment Detail";
  return "CPC Lab";
}

/** Small inline page-calendar refresh used by pages that poll. */
export function PollingHint({ onRefresh, label = "Refresh" }: { onRefresh: () => void; label?: string }) {
  return (
    <Button variant="outline" size="sm" onClick={onRefresh}>
      <RefreshCw className="h-3.5 w-3.5" /> {label}
    </Button>
  );
}
