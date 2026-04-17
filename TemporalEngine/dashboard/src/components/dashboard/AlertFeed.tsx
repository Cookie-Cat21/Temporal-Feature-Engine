"use client";

import { motion, AnimatePresence } from "motion/react";
import { GlassCard } from "../ui/glass-card";
import { Bell, Zap, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface Alert {
  user_id: string;
  alert_type: "VELOCITY" | "GOVERNANCE";
  amount: string;
  merchant: string;
  ts: number;
}

function timeAgo(ts: number) {
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 60)  return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

export function AlertFeed({ alerts }: { alerts: Alert[] }) {
  return (
    <GlassCard className="flex flex-col gap-4 overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/10 pb-4">
        <div className="flex items-center gap-2">
          <Bell className="text-warning size-5" />
          <h2 className="text-lg font-semibold">Fraud Alert Feed</h2>
        </div>
        {alerts.length > 0 && (
          <span className="text-[10px] font-mono bg-warning/10 text-warning border border-warning/20 px-2 py-0.5 rounded-full">
            {alerts.length} LIVE
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2 overflow-y-auto max-h-64 pr-1">
        <AnimatePresence initial={false}>
          {alerts.length === 0 ? (
            <p className="text-xs text-white/30 text-center py-6">No alerts — pipeline is clean.</p>
          ) : (
            alerts.map((alert, i) => (
              <motion.div
                key={`${alert.user_id}-${alert.ts}-${i}`}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className={cn(
                  "flex items-center justify-between p-3 rounded-xl border text-xs",
                  alert.alert_type === "VELOCITY"
                    ? "border-warning/20 bg-warning/5"
                    : "border-error/20 bg-error/5"
                )}
              >
                <div className="flex items-center gap-3">
                  {alert.alert_type === "VELOCITY"
                    ? <Zap size={14} className="text-warning shrink-0" />
                    : <ShieldAlert size={14} className="text-error shrink-0" />
                  }
                  <div>
                    <span className="font-medium text-white/90">{alert.user_id}</span>
                    <p className="text-white/40 font-mono truncate max-w-36">{alert.merchant || "—"}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className={cn(
                    "font-bold tabular-nums",
                    alert.alert_type === "VELOCITY" ? "text-warning" : "text-error"
                  )}>
                    ${alert.amount}
                  </span>
                  <span className="text-white/30 font-mono">{timeAgo(alert.ts)}</span>
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </GlassCard>
  );
}
