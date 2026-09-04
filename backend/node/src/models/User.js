'use strict';

const { requireSupabase } = require('../config/supabase');

async function findOne({ userId }) {
  const { data, error } = await requireSupabase().from('users').select('*').eq('id', userId).maybeSingle();
  if (error) throw error;
  return data;
}

module.exports = { findOne };
