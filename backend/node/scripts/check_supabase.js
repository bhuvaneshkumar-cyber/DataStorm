'use strict';

require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!url || !key) {
  throw new Error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured.');
}

const supabase = createClient(url, key, {
  auth: { autoRefreshToken: false, persistSession: false },
});

(async () => {
  const { data, error } = await supabase
    .from('node_transactions')
    .select('id, transaction_id, type, amount')
    .limit(1);

  if (error) throw error;
  console.log('Supabase live query succeeded.');
  console.log(JSON.stringify(data, null, 2));
})().catch((error) => {
  console.error('Supabase live query failed:', error);
  process.exitCode = 1;
});
