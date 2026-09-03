'use strict';
/**
 * server.js – HTTP server entry point.
 *
 * Connects to MongoDB, then starts the Express app. If Mongo is unreachable,
 * the server still starts (so /health stays up for orchestration probes) but
 * logs a warning, since every webhook route will fail without a DB.
 */

const app = require('./app');
const config = require('./config');
const { connectDB } = require('./config/db');

async function start() {
  try {
    await connectDB();
    console.log('[GigSave] Connected to MongoDB');
  } catch (err) {
    console.error(
      '[GigSave] MongoDB connection failed; webhook routes will error until it is reachable:',
      err.message
    );
  }

  app.listen(config.port, () => {
    console.log(`[GigSave] Node backend listening on port ${config.port}`);
  });
}

start();
