-- HFusionHub V31 — Plugin Image Digest for Supply-Chain Verification
-- Adds image_digest column to plugin table for container image integrity verification.

ALTER TABLE plugin ADD COLUMN image_digest VARCHAR(128) DEFAULT NULL COMMENT 'SHA-256 digest of the container image for supply-chain verification';
