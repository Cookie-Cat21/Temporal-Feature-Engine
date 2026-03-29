"use client";

import { motion } from "motion/react";
import { GlassCard } from "../ui/glass-card";
import { Terminal, Cpu, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  node: string;
  status: "pending" | "running" | "completed" | "error";
  message: string;
}

export function AgentReasoning({ steps }: { steps: Step[] }) {
  return (
    <GlassCard className="h-full flex flex-col gap-4 overflow-hidden" glow>
      <div className="flex items-center gap-2 border-b border-white/10 pb-4">
        <Cpu className="text-accent size-5" />
        <h2 className="text-lg font-semibold text-balance">Investigator Intelligence</h2>
      </div>

      <div className="flex flex-col gap-4 overflow-y-auto pr-2 custom-scrollbar">
        {steps.map((step, index) => (
          <motion.div
            key={step.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 }}
            className="flex gap-4"
          >
            <div className="flex flex-col items-center">
              <div className={cn(
                "size-8 rounded-full flex items-center justify-center border",
                step.status === "completed" ? "bg-accent/20 border-accent/50 text-accent" :
                step.status === "running" ? "bg-ring/20 border-ring/50 text-ring animate-pulse" :
                "bg-white/5 border-white/10 text-white/40"
              )}>
                {step.status === "completed" ? <CheckCircle2 size={16} /> : 
                 step.status === "running" ? <Terminal size={16} /> :
                 <div className="size-2 rounded-full bg-current" />}
              </div>
              {index < steps.length - 1 && (
                <div className="w-px h-full bg-white/10 my-1" />
              )}
            </div>
            
            <div className="flex flex-col gap-1 pb-6">
              <span className="text-sm font-medium text-white/90">{step.node}</span>
              <p className="text-xs text-white/50 leading-relaxed font-mono">
                {step.message}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}
