import Link from "next/link";
import { ChevronLeftIcon } from "lucide-react";
import { MainView } from "@/components/main-view";

export default function LineagePage() {
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
        <h1 className="text-2xl font-bold tracking-tight">Research Lineage Exploration</h1>
        <p className="text-sm text-muted-foreground">
          Search by keyword or paper title to explore related research lineages and visualise the citation graph.
        </p>
      </div>
      <MainView />
    </main>
  );
}
