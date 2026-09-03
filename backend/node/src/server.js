'use strict';
/**
 * server.js – HTTP server entry point (stub)
 *
 * Reads PORT from environment (default 3001) and starts the Express app.
 * TODO (Phase 3): Add MongoDB connection before listen().
 */

const app = require('./app');

const PORT = process.env.PORT || 3001;

app.listen(PORT, () => {
  console.log(`[GigSave] Node backend listening on port ${PORT}`);
});
