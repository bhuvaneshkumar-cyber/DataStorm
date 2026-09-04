'use strict';

const { createClient } = require('@supabase/supabase-js');
const config = require('./index');

const isConfigured = Boolean(config.supabaseUrl && config.supabaseServiceRoleKey);

const supabase = isConfigured
  ? createClient(config.supabaseUrl, config.supabaseServiceRoleKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    })
  : null;

function requireSupabase() {
  if (!supabase) {
    throw new Error('Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.');
  }
  return supabase;
}

module.exports = { supabase, isConfigured, requireSupabase };
