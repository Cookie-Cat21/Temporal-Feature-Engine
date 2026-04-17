import { NextResponse } from 'next/server';
import neo4j from 'neo4j-driver';

const driver = neo4j.driver(
  process.env.MEMGRAPH_URI || 'bolt://localhost:7687',
  neo4j.auth.basic('', '')
);

export async function GET() {
  const session = driver.session();
  try {
    // Query Memgraph for the most recent transaction relationships
    const result = await session.run(`
      MATCH (u:User)-[r:TRANSACTED_WITH]->(m:Merchant)
      RETURN
        u.user_id as user_id,
        m.merchant_name as merchant,
        r.amount as amount,
        COALESCE(u.governance_status, 'OK') as governance_status,
        COALESCE(u.velocity_flag, 'NORMAL') as velocity_flag,
        u.violations as violations
      ORDER BY r.ts DESC
      LIMIT 20
    `);

    const transactions = result.records.map((record, index) => ({
      id: `live_${index}`,
      user_id: record.get('user_id'),
      merchant: record.get('merchant'),
      amount: record.get('amount').toString(),
      governance_status: record.get('governance_status'),
      velocity_flag: record.get('velocity_flag'),
      violations: record.get('violations'),
    }));

    return NextResponse.json(transactions);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  } finally {
    await session.close();
  }
}
