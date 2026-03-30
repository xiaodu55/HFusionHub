-- Allow feature_flag_rule.enabled to be NULL (NULL = inherit from flag's global default)
ALTER TABLE feature_flag_rule MODIFY COLUMN enabled BOOLEAN DEFAULT NULL;
