-- Migration: make etoro_position_id nullable to support optimistic position writes.
-- Optimistic rows use a "pending_<order_id>" placeholder until the fill handler
-- updates them with the real eToro position ID.
-- Safe to run on a live system — only relaxes a NOT NULL constraint.

ALTER TABLE positions ALTER COLUMN etoro_position_id DROP NOT NULL;
