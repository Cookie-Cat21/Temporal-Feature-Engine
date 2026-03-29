"use client";

import { AgentReasoning } from "@/components/dashboard/AgentReasoning";
import { SovereigntyMonitor } from "@/components/dashboard/SovereigntyMonitor";
import { RingGallery } from "@/components/dashboard/RingGallery";
import { GlassCard } from "@/components/ui/glass-card";
import { Shield, Activity, Zap, Info } from "lucide-react";
import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function Home() {
  const { data: rings_raw } = useSWR('/api/data/rings', fetcher, { refreshInterval: 2000 });
  const { data: transactions_raw } = useSWR('/api/data/transactions', fetcher, { refreshInterval: 1000 });
  const { data: steps_raw } = useSWR('/api/data/agent', fetcher, { refreshInterval: 1000 });

  const rings = Array.isArray(rings_raw) ? rings_raw : [];
  const transactions = Array.isArray(transactions_raw) ? transactions_raw : [];
  const steps = Array.isArray(steps_raw) ? steps_raw : [
    { id: "idle", node: "Awaiting Trigger", status: "pending" as const, message: "Monitoring system for autonomous investigation triggers..." }
  ];

  return (
    <main className="min-h-dvh background-grid p-8 lg:p-12 font-sans">
      <div className="max-w-7xl mx-auto flex flex-col gap-8">
        
        {/* Header */}
        <header className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              <div className="bg-ring/10 p-2 rounded-xl border border-ring/20">
                <Shield className="text-ring size-6" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-balance">Temporal Intelligence Hub</h1>
            </div>
            <p className="text-sm text-white/40 ml-12">Production Command Center v1.0.4-sovereign</p>
          </div>
          
          <div className="flex gap-4">
             <GlassCard className="px-4 py-2 flex items-center gap-3 bg-white/[0.02] border-white/5">
                <Activity className="size-4 text-accent animate-pulse" />
                <div className="flex flex-col">
                    <span className="text-[10px] text-white/40 uppercase">Cluster Load</span>
                    <span className="text-sm font-bold tabular-nums">1.2k tx/s</span>
                </div>
             </GlassCard>
             <GlassCard className="px-4 py-2 flex items-center gap-3 bg-white/[0.02] border-white/5">
                <Zap className="size-4 text-warning" />
                <div className="flex flex-col">
                    <span className="text-[10px] text-white/40 uppercase">Decision Latency</span>
                    <span className="text-sm font-bold tabular-nums">142ms</span>
                </div>
             </GlassCard>
          </div>
        </header>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 xl:grid-cols-16 gap-8 items-start">
          
          {/* Autonomous Ring Gallery */}
          <aside className="lg:col-span-12 xl:col-span-4 h-full">
            <RingGallery rings={rings} />
          </aside>

          {/* Main Monitor */}
          <section className="lg:col-span-12 xl:col-span-8">
             <SovereigntyMonitor transactions={transactions} />
          </section>

          {/* Reasoning Sidebar */}
          <aside className="lg:col-span-12 xl:col-span-4 h-full">
            <AgentReasoning steps={steps} />
          </aside>

        </div>

        {/* Footer info */}
        <footer className="flex items-center gap-2 text-xs text-white/20 mt-4">
          <Info size={14} />
          <span>Real-time data provided by Temporal Flink Engine & Memgraph Cypher-Mage</span>
        </footer>

      </div>
    </main>
  );
}
