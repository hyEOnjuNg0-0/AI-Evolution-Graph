import Link from "next/link";
import { ChevronLeftIcon } from "lucide-react";

import { TrendView } from "@/components/trend-view";

export default function TrendPage() {
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
        <h1 className="text-2xl font-bold tracking-tight">Trend Momentum Analysis</h1>
        <p className="text-sm text-muted-foreground">
          CAGR·Shannon 엔트로피·채택 속도로 AI 방법론의 성장 모멘텀을 정량화합니다.
        </p>
      </div>
      <TrendView />
    </main>
  );
}
