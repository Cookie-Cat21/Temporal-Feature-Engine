import Redis from "ioredis";

// Reuse the same connection across serverless invocations.
// REDIS_URL takes priority (Vercel KV / Upstash).
// Falls back to REDIS_HOST + REDIS_PORT for the local Docker stack.
declare global {
  // eslint-disable-next-line no-var
  var __redis: Redis | undefined;
}

export function getRedis(): Redis {
  if (global.__redis) return global.__redis;

  const url = process.env.REDIS_URL;
  global.__redis = url
    ? new Redis(url, { tls: url.startsWith("rediss://") ? {} : undefined })
    : new Redis({
        host: process.env.REDIS_HOST ?? "localhost",
        port: parseInt(process.env.REDIS_PORT ?? "6379"),
        lazyConnect: true,
      });

  return global.__redis;
}
