import Link from "next/link";
import { ArrowRightIcon, GitBranchIcon, TrendingUpIcon, ZapIcon } from "lucide-react";

const FEATURES = [
  {
    href: "/lineage",
    icon: GitBranchIcon,
    title: "Research Lineage Exploration",
    description:
      "Explore research lineages by keyword or paper title. Hybrid search combining semantic similarity and citation structure surfaces the most relevant papers.",
    label: "Explore",
  },
  {
    href: "/breakthrough",
    icon: ZapIcon,
    title: "Breakthrough Detection",
    description:
      "Detect structural inflection papers in a research field using Kleinberg burst analysis combined with centrality shift scoring.",
    label: "Detect",
  },
  {
    href: "/trend",
    icon: TrendingUpIcon,
    title: "Trend Momentum Analysis",
    description:
      "Quantify growth momentum of AI methods using CAGR, Shannon entropy, and adoption velocity, and trace their evolution paths.",
    label: "Analyze",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col items-center px-4 py-20 gap-16">
      {/* Hero */}
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-4xl font-bold tracking-tight">AI EvoGraph</h1>
        <p className="max-w-lg text-base text-muted-foreground">
          A GraphRAG-powered platform for analysing AI paper citations and method evolution graphs.
          <br />
          Quantitatively explore research lineages, structural inflection points, and diffusion dynamics.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid w-full grid-cols-1 gap-5 sm:grid-cols-3">
        {FEATURES.map(({ href, icon: Icon, title, description, label }) => (
          <Link
            key={href}
            href={href}
            className="group flex flex-col gap-4 rounded-xl border bg-card px-5 py-6 ring-1 ring-foreground/10 transition-shadow hover:shadow-md hover:ring-foreground/20"
          >
            <div className="flex items-center justify-between">
              <div className="flex size-10 items-center justify-center rounded-lg bg-muted">
                <Icon className="size-5 text-foreground/70" />
              </div>
              <ArrowRightIcon className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </div>
            <div className="flex flex-col gap-1.5">
              <p className="font-medium leading-snug">{title}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
            </div>
            <span className="mt-auto text-xs font-medium text-foreground/60 group-hover:text-foreground transition-colors">
              {label} →
            </span>
          </Link>
        ))}
      </div>
    </main>
  );
}
