'use strict';
/**
 * server.js – HTTP server entry point.
 *
 * Connects to Supabase, then starts the Express app. If Supabase is unavailable,
 * the server still starts so /health remains available.
 */

const app = require('./app');
const config = require('./config');
const { connectDB } = require('./config/db');

async function start() {
  try {
    await connectDB();
    console.log('[GigSave] Connected to Supabase');
  } catch (err) {
    console.error(
      '[GigSave] Supabase connection failed; webhook routes will error until it is reachable:',
      err.message
    );
  }

  app.listen(config.port, () => {
    console.log(`[GigSave] Node backend listening on port ${config.port}`);
  });
}

start();
