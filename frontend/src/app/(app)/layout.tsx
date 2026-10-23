"use client";
import { AppShell } from "@/components/app-shell";
import type { ReactNode } from "react";

export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
