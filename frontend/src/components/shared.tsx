import type { ReactNode } from "react";
import { Card, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label, value, hint, tone,
}: { label: string; value: ReactNode; hint?: string; tone?: "blue" | "green" | "violet" | "amber" }) {
  const barStyle = tone === undefined ? undefined
    : tone === "green" ? { background: "linear-gradient(90deg,#34d399,#059669)" }
    : tone === "violet" ? { background: "linear-gradient(90deg,#B02FF5,#7C3AED)" }
    : tone === "amber" ? { background: "linear-gradient(90deg,#fbbf24,#d97706)" }
    : undefined;
  return (
    <Card className="relative overflow-hidden">
      <div className={cn("absolute inset-x-0 top-0 h-0.5", !barStyle && "brand-gradient-bar")} style={barStyle} />
      <div className="p-4 pt-3">
        <p className="text-2xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
        {hint ? <p className="mt-1 text-2xs text-muted-foreground">{hint}</p> : null}
      </div>
    </Card>
  );
}

export function StatCardSkeleton() {
  return (
    <Card>
      <div className="p-4 pt-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-2 h-6 w-16" />
        <Skeleton className="mt-2 h-3 w-32" />
      </div>
    </Card>
  );
}

export function SectionCard({ title, description, actions, children, className }: {
  title: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <Card className={className}>
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description ? <p className="text-2xs text-muted-foreground">{description}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </Card>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
      {children}
    </p>
  );
}

export function SimpleTable({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            {head.map((h) => (
              <th key={h} className="whitespace-nowrap px-4 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  );
}
