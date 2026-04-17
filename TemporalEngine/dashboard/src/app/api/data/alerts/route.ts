import { NextResponse } from "next/server";
import { getRedis } from "@/lib/redis";

export async function GET() {
  try {
    const r = getRedis();
    const raw = await r.lrange("fraud:alerts", 0, 19);
    const alerts = raw.map((s) => JSON.parse(s));
    return NextResponse.json(alerts);
  } catch {
    return NextResponse.json([]);
  }
}
