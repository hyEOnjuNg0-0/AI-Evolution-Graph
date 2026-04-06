import Link from "next/link";
import { ChevronLeftIcon } from "lucide-react";

import { EvolutionView } from "@/components/evolution-view";

export default function EvolutionPage() {
  return (
    <main className="mx-auto w-full max-w-screen-xl px-4 py-10">
      <div className="mb-8 flex flex-col gap-1">
        <Link
          href="/"
          className="mb-3 flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeftIcon className="size-4" />
          Home
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">Method Evolution Path</h1>
        <p className="text-sm text-muted-foreground">
          Trace how an AI method evolved over time — which methods it extended, improved, or replaced.
        </p>
      </div>
      <EvolutionView />
    </main>
  );
}
