"use client";

import { motion } from "motion/react";
import { GlassCard } from "../ui/glass-card";
import { Users, Crosshair, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface FraudRing {
  id: string;
  size: number;
  status: "active" | "investigating" | "neutralized";
  risk_score: number;
}

export function RingGallery({ rings }: { rings: FraudRing[] }) {
  return (
    <GlassCard className="h-full flex flex-col gap-4 overflow-hidden" glow>
      <div className="flex items-center gap-2 border-b border-white/10 pb-4">
        <Crosshair className="text-error size-5" />
        <h2 className="text-lg font-semibold tabular-nums text-balance text-error">Ring Hunter: ACTIVE</h2>
      </div>

      <div className="flex flex-col gap-4 overflow-y-auto pr-2 custom-scrollbar">
        {rings.map((ring, index) => (
          <motion.div
            key={ring.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="group relative flex flex-col gap-3 p-4 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-error/5 hover:border-error/20 transition-all"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-white/40 group-hover:text-error/60" />
                <span className="text-xs font-mono text-white/60">CLUSTER_{ring.id}</span>
              </div>
              <div className={cn(
                "px-2 py-0.5 rounded text-[10px] font-bold border",
                ring.status === "active" ? "bg-error/20 border-error/50 text-error animate-pulse" :
                "bg-white/5 border-white/10 text-white/40"
              )}>
                {ring.status.toUpperCase()}
              </div>
            </div>

            <div className="flex items-end justify-between">
              <div className="flex flex-col">
                 <span className="text-2xl font-bold tabular-nums">{ring.size}</span>
                 <span className="text-[10px] text-white/30 uppercase tracking-widest">Entities Linked</span>
              </div>
              
              <div className="flex flex-col items-end gap-1">
                 <div className="flex items-center gap-1 text-[10px] text-error font-medium">
                    <AlertTriangle size={12} />
                    <span>RISK: {ring.risk_score}%</span>
                 </div>
                 <div className="w-24 h-1 bg-white/5 rounded-full overflow-hidden">
                    <div 
                        className="h-full bg-error transition-all duration-500" 
                        style={{ width: `${ring.risk_score}%` }} 
                    />
                 </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}
