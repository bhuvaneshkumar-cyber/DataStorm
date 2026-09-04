'use strict';
const { requireSupabase } = require('./supabase');

async function connectDB() {
  const client = requireSupabase();
  const { error } = await client.from('node_transactions').select('id').limit(1);
  if (error) throw error;
  return client;
}

module.exports = { connectDB };
