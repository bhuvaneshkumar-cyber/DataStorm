'use strict';
/**
 * User.js – Mongoose schema for a GigSave registered user.
 *
 * One document per gig worker. Holds identity, linked banking details,
 * and the UPI AutoPay mandate that drives automated sweeps.
 */

const mongoose = require('mongoose');

const { Schema, model } = mongoose;

// ---------------------------------------------------------------------------
// Sub-schema: UPI AutoPay mandate details
// ---------------------------------------------------------------------------
const MandateSchema = new Schema(
  {
    /** Unique mandate reference ID issued by the payment gateway / NPCI. */
    mandateId: {
      type: String,
      default: null,
    },

    /**
     * Maximum single-sweep amount allowed under this mandate (in INR).
     * Mirrors mandate_limit in savings.py. Default ₹1000.
     * savingsEngine will never authorise a sweep exceeding this value.
     */
    capAmount: {
      type: Number,
      default: 1000,
      min: [1, 'Mandate cap must be at least ₹1'],
    },

    /** Whether the mandate is currently active (registered & not revoked). */
    isActive: {
      type: Boolean,
      default: false,
    },
  },
  { _id: false } // embedded sub-doc, no separate _id needed
);

// ---------------------------------------------------------------------------
// Sub-schema: Linked bank account (placeholder – real integration comes later)
// ---------------------------------------------------------------------------
const BankAccountSchema = new Schema(
  {
    /**
     * Opaque reference token returned by the bank adapter / AA framework.
     * Never store raw account numbers here – use a tokenised reference.
     */
    accountRef: {
      type: String,
      default: null,
    },

    /** Human-readable label, e.g. "SBI Savings ••••4321". */
    label: {
      type: String,
      default: null,
    },

    /** ISO 4217 currency code – always "INR" for this product. */
    currency: {
      type: String,
      default: 'INR',
    },
  },
  { _id: false }
);

// ---------------------------------------------------------------------------
// Main User schema
// ---------------------------------------------------------------------------
const UserSchema = new Schema(
  {
    /**
     * Application-level user identifier (UUID v4).
     * Decoupled from Mongo's _id so downstream services can reference users
     * without leaking ObjectId internals.
     */
    userId: {
      type: String,
      required: [true, 'userId is required'],
      unique: true,
      index: true,
    },

    /** Full name of the gig worker. */
    name: {
      type: String,
      required: [true, 'name is required'],
      trim: true,
    },

    /**
     * Mobile number in E.164 format (e.g. +919876543210).
     * Used for UPI mandate registration and OTP flows.
     */
    phone: {
      type: String,
      required: [true, 'phone is required'],
      unique: true,
    },

    /** Optional email address for notifications / receipts. */
    email: {
      type: String,
      default: null,
      lowercase: true,
      trim: true,
    },

    /**
     * Linked bank account details.
     * Placeholder – real AA / banking-stack integration happens in a later phase.
     */
    bankAccount: {
      type: BankAccountSchema,
      default: () => ({}),
    },

    /**
     * UPI AutoPay mandate registered for automatic sweep debits.
     * capAmount here must be kept in sync with SavingsStash.mandateCap.
     */
    mandate: {
      type: MandateSchema,
      default: () => ({}),
    },
  },
  {
    timestamps: true, // adds createdAt + updatedAt automatically
    collection: 'users',
  }
);

module.exports = model('User', UserSchema);
