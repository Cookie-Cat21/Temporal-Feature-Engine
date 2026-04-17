"use client";

import { GlassCard } from "../ui/glass-card";
import { Activity, AlertTriangle, ShieldAlert, Users, Bot, Inbox, Zap } from "lucide-react";

interface Metrics {
  events_processed: number;
  velocity_high: number;
  violations: number;
  fraud_rings: number;
  investigations: number;
  dlq_events: number;
  active_users: number;
}

interface MetricTileProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  accent?: "default" | "warning" | "error" | "ring";
}

function MetricTile({ icon, label, value, accent = "default" }: MetricTileProps) {
  const colors = {
    default: "text-accent",
    warning: "text-warning",
    error:   "text-error",
    ring:    "text-ring",
  };
  return (
    <GlassCard className="flex items-center gap-3 px-4 py-3 bg-white/[0.02] border-white/5">
      <div className={`${colors[accent]} opacity-80`}>{icon}</div>
      <div className="flex flex-col">
        <span className="text-[10px] text-white/40 uppercase tracking-wider">{label}</span>
        <span className="text-sm font-bold tabular-nums">{value.toLocaleString()}</span>
      </div>
    </GlassCard>
  );
}

export function MetricsBar({ metrics }: { metrics: Metrics }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
      <MetricTile icon={<Activity size={16} className="animate-pulse" />} label="Events" value={metrics.events_processed} accent="default" />
      <MetricTile icon={<Users size={16} />}          label="Active Users"    value={metrics.active_users}    accent="ring" />
      <MetricTile icon={<Zap size={16} />}            label="Velocity HIGH"   value={metrics.velocity_high}   accent="warning" />
      <MetricTile icon={<ShieldAlert size={16} />}    label="Violations"      value={metrics.violations}      accent="error" />
      <MetricTile icon={<AlertTriangle size={16} />}  label="Fraud Rings"     value={metrics.fraud_rings}     accent="error" />
      <MetricTile icon={<Bot size={16} />}            label="Investigations"  value={metrics.investigations}  accent="ring" />
      <MetricTile icon={<Inbox size={16} />}          label="DLQ Events"      value={metrics.dlq_events}      accent="warning" />
    </div>
  );
}
