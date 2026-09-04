'use strict';

const { requireSupabase } = require('../config/supabase');

function fromRow(row) {
  if (!row) return null;
  return {
    ...row,
    userId: row.user_id,
    rolling30DayPayouts: row.rolling30_day_payouts || [],
    currentRollingAverage: row.current_rolling_average == null ? null : Number(row.current_rolling_average),
  };
}

async function findOne({ userId }) {
  const { data, error } = await requireSupabase().from('node_income_profiles')
    .select('*').eq('user_id', userId).maybeSingle();
  if (error) throw error;
  return fromRow(data);
}

async function findOneAndUpdate({ userId }, update) {
  const client = requireSupabase();
  const values = update.$set || {};
  const payload = {
    user_id: userId,
    rolling30_day_payouts: values.rolling30DayPayouts || [],
    current_rolling_average: values.currentRollingAverage ?? null,
  };
  const { data, error } = await client.from('node_income_profiles')
    .upsert(payload, { onConflict: 'user_id' }).select('*').single();
  if (error) throw error;
  return fromRow(data);
}

module.exports = { findOne, findOneAndUpdate };
