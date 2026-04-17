import { NextResponse } from 'next/server';
import { getRedis } from '@/lib/redis';

const redis = getRedis();

export async function GET() {
  try {
    // Fetch the latest 10 reasoning steps from Redis
    const stepsRaw = await redis.lrange('agent:reasoning:steps', 0, 9);
    const steps = stepsRaw.map(s => JSON.parse(s)).reverse(); // Show oldest to newest in UI

    return NextResponse.json(steps);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
