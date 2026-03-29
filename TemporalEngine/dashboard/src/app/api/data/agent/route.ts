import { NextResponse } from 'next/server';
import Redis from 'ioredis';

const redis = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: 6379,
});

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
