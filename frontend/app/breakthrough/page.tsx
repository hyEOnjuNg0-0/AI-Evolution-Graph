import Link from "next/link";
import { ChevronLeftIcon } from "lucide-react";

import { BreakthroughView } from "@/components/breakthrough-view";

export default function BreakthroughPage() {
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
        <h1 className="text-2xl font-bold tracking-tight">Breakthrough Detection</h1>
        <p className="text-sm text-muted-foreground">
          Kleinberg burst 분석과 중심성 이동으로 구조적 전환점 논문을 탐지합니다.
        </p>
      </div>
      <BreakthroughView />
    </main>
  );
}
