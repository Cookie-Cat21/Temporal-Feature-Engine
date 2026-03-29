"use client";

import { motion } from "motion/react";
import { GlassCard } from "../ui/glass-card";
import { ShieldCheck, ShieldAlert, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

interface Transaction {
  id: string;
  user_id: string;
  merchant: string;
  amount: string;
  governance_status: "OK" | "VIOLATION";
  violations?: string[];
}

export function SovereigntyMonitor({ transactions }: { transactions: Transaction[] }) {
  return (
    <GlassCard className="h-full flex flex-col gap-4 overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/10 pb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="text-accent size-5" />
          <h2 className="text-lg font-semibold tabular-nums">Sovereignty Guard</h2>
        </div>
        <div className="flex gap-4 text-xs font-mono text-white/40">
          <div className="flex items-center gap-1">
            <div className="size-2 rounded-full bg-accent" />
            <span>PROTECTED</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="size-2 rounded-full bg-error" />
            <span>VIOLATION</span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2 overflow-y-auto pr-2 custom-scrollbar">
        {transactions.map((tx, index) => (
          <motion.div
            key={tx.id}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.05 }}
            className={cn(
              "flex items-center justify-between p-3 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all",
              tx.governance_status === "VIOLATION" && "border-error/20 bg-error/5"
            )}
          >
            <div className="flex items-center gap-4">
              <div className={cn(
                "p-2 rounded-lg",
                tx.governance_status === "OK" ? "bg-accent/10" : "bg-error/10"
              )}>
                {tx.governance_status === "OK" ? (
                  <ShieldCheck size={16} className="text-accent" />
                ) : (
                  <ShieldAlert size={16} className="text-error" />
                )}
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium tabular-nums">{tx.user_id}</span>
                <span className="text-[10px] text-white/40 uppercase tracking-wider font-mono">
                  {tx.merchant}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-6">
               <div className="flex items-center gap-2 bg-white/5 px-2 py-1 rounded text-[10px] font-mono border border-white/5">
                <EyeOff size={10} className="text-white/40" />
                <span className="text-accent">PII MASKED</span>
              </div>
              <span className="text-sm font-bold tabular-nums">${tx.amount}</span>
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}


