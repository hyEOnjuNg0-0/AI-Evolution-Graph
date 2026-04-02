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
          Keyword나 논문 제목으로 관련 연구 계보를 탐색하고 인용 그래프를 시각화합니다.
        </p>
      </div>
      <MainView />
    </main>
  );
}
