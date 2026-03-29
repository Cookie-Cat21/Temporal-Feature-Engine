import { NextResponse } from 'next/server';

// Live simulation engine - generates evolving fraud ring data
// When Memgraph is online, swap this for the neo4j-driver queries

const RING_TEMPLATES = [
  { id: "RING-104", baseSize: 12, status: "active", baseRisk: 92 },
  { id: "RING-112", baseSize: 7, status: "active", baseRisk: 78 },
  { id: "RING-088", baseSize: 5, status: "investigating", baseRisk: 65 },
  { id: "RING-201", baseSize: 3, status: "active", baseRisk: 88 },
  { id: "RING-045", baseSize: 9, status: "neutralized", baseRisk: 12 },
];

function generateLiveRings() {
  const now = Date.now();
  return RING_TEMPLATES.map((ring) => {
    // Simulate organic growth: size fluctuates slightly over time
    const drift = Math.sin(now / 10000 + parseInt(ring.id.replace(/\D/g, ''))) * 2;
    const size = Math.max(2, Math.round(ring.baseSize + drift));
    
    // Risk score pulses realistically
    const riskPulse = Math.sin(now / 5000 + parseInt(ring.id.replace(/\D/g, ''))) * 5;
    const risk_score = Math.min(99, Math.max(5, Math.round(ring.baseRisk + riskPulse)));

    return {
      id: ring.id,
      size,
      status: ring.status,
      risk_score,
    };
  });
}

export async function GET() {
  return NextResponse.json(generateLiveRings());
}
