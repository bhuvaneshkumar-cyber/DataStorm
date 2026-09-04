'use strict';

const { requireSupabase } = require('../config/supabase');

function fromRow(row) {
  if (!row) return null;
  return {
    ...row,
    userId: row.user_id,
    transactionId: row.transaction_id,
    isProcessed: row.is_processed,
    rawPayload: row.raw_payload,
  };
}

async function findOne({ transactionId }) {
  const { data, error } = await requireSupabase()
    .from('node_transactions')
    .select('*')
    .eq('transaction_id', transactionId)
    .maybeSingle();
  if (error) throw error;
  return fromRow(data);
}

async function findOneAndUpdate({ transactionId }, update, options = {}) {
  const client = requireSupabase();
  const { data: existing, error: readError } = await client
    .from('node_transactions').select('*').eq('transaction_id', transactionId).maybeSingle();
  if (readError) throw readError;

  if (!existing && options.upsert && update.$setOnInsert) {
    const source = update.$setOnInsert;
    const { data, error } = await client.from('node_transactions').insert({
      transaction_id: source.transactionId,
      user_id: source.userId,
      type: source.type,
      amount: source.amount,
      source: source.source,
      timestamp: source.timestamp,
      status: source.status || 'pending',
      is_processed: source.isProcessed || false,
      raw_payload: source.rawPayload || null,
    }).select('*').single();
    if (error) throw error;
    return fromRow(data);
  }

  if (!existing) return null;
  const values = update.$set || {};
  const mapped = {};
  if (values.status !== undefined) mapped.status = values.status;
  if (values.isProcessed !== undefined) mapped.is_processed = values.isProcessed;
  const { data, error } = await client.from('node_transactions')
    .update(mapped).eq('transaction_id', transactionId).select('*').single();
  if (error) throw error;
  return fromRow(data);
}

module.exports = { findOne, findOneAndUpdate };
