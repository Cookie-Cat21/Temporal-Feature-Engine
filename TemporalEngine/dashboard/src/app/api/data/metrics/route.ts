import { NextResponse } from "next/server";
import { getRedis } from "@/lib/redis";

export async function GET() {
  try {
    const r = getRedis();
    const [events, velocityHigh, violations, rings, investigations, dlq, userKeys] =
      await Promise.all([
        r.get("metrics:events_processed_total"),
        r.get("metrics:velocity_high_total"),
        r.get("metrics:violations_total"),
        r.get("metrics:fraud_rings_detected_total"),
        r.get("metrics:agent_investigations_total"),
        r.get("metrics:dlq_events_total"),
        r.keys("feature:user:*:status"),
      ]);

    return NextResponse.json({
      events_processed:   parseInt(events        ?? "0"),
      velocity_high:      parseInt(velocityHigh  ?? "0"),
      violations:         parseInt(violations    ?? "0"),
      fraud_rings:        parseInt(rings         ?? "0"),
      investigations:     parseInt(investigations ?? "0"),
      dlq_events:         parseInt(dlq           ?? "0"),
      active_users:       userKeys.length,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "unknown error";
    return NextResponse.json(
      { events_processed: 0, velocity_high: 0, violations: 0,
        fraud_rings: 0, investigations: 0, dlq_events: 0, active_users: 0,
        error: msg },
      { status: 200 }
    );
  }
}
