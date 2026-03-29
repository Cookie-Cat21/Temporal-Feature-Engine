import { NextResponse } from 'next/server';
import neo4j from 'neo4j-driver';

const driver = neo4j.driver(
  process.env.MEMGRAPH_URI || 'bolt://localhost:7687',
  neo4j.auth.basic('', '')
);

export async function GET() {
  const session = driver.session();
  try {
    // Query Memgraph for identified fraud rings
    const result = await session.run(`
      MATCH (u:User)
      WHERE u.fraud_ring_id IS NOT NULL
      RETURN 
        u.fraud_ring_id as id, 
        count(u) as size,
        'active' as status,
        90 as risk_score
      LIMIT 10
    `);

    const rings = result.records.map((record) => ({
      id: `RING-${record.get('id')}`,
      size: record.get('size').toNumber(),
      status: record.get('status'),
      risk_score: record.get('risk_score')
    }));

    return NextResponse.json(rings);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  } finally {
    await session.close();
  }
}
