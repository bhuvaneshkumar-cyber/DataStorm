'use strict';

const { requireSupabase } = require('../config/supabase');

function fromRow(row) {
  if (!row) return null;
  return {
    ...row,
    userId: row.user_id,
    currentBalance: Number(row.current_balance),
    pendingContributions: Number(row.pending_contributions),
    minimumThreshold: Number(row.minimum_threshold),
    mandateCap: Number(row.mandate_cap),
    lastSweepDate: row.last_sweep_date,
    sweepHistory: row.sweep_history || [],
  };
}

async function findOne({ userId }) {
  const { data, error } = await requireSupabase().from('node_savings_stashes')
    .select('*').eq('user_id', userId).maybeSingle();
  if (error) throw error;
  return fromRow(data);
}

async function findOneAndUpdate({ userId }, update) {
  const client = requireSupabase();
  const current = await findOne({ userId });
  if (!current) return null;
  const values = update.$set || {};
  const mapped = {};
  if (values.pendingContributions !== undefined) mapped.pending_contributions = values.pendingContributions;
  if (values.currentBalance !== undefined) mapped.current_balance = values.currentBalance;
  if (values.lastSweepDate !== undefined) mapped.last_sweep_date = values.lastSweepDate;
  if (update.$push?.sweepHistory) mapped.sweep_history = [...(current.sweepHistory || []), update.$push.sweepHistory];
  const { data, error } = await client.from('node_savings_stashes')
    .update(mapped).eq('user_id', userId).select('*').single();
  if (error) throw error;
  return fromRow(data);
}

module.exports = { findOne, findOneAndUpdate };
