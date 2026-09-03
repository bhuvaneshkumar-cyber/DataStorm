'use strict';
/**
 * config/db.js – Mongoose connection helper.
 */

const mongoose = require('mongoose');

const config = require('./index');

async function connectDB() {
  mongoose.set('strictQuery', true);
  return mongoose.connect(config.mongoUri);
}

module.exports = { connectDB };
