-- Prompt Test Case Pass Rules — expected keywords + required cited documents.
-- Each case can define pass rules; batch runs evaluate them and compute a pass rate per version.

-- Expected keywords: every keyword must appear in the AI answer (case-insensitive substring).
-- Required document ids: every doc must be cited in the result sources.
ALTER TABLE `prompt_test_case`
    ADD COLUMN `expected_keywords` TEXT DEFAULT NULL COMMENT 'Expected keywords as JSON array of strings',
    ADD COLUMN `required_document_ids` TEXT DEFAULT NULL COMMENT 'Required cited document ids as JSON array';

-- Per-case evaluation outcome persisted with each run.
ALTER TABLE `prompt_test_case_result`
    ADD COLUMN `passed` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether the case met its pass rules',
    ADD COLUMN `pass_notes` TEXT DEFAULT NULL COMMENT 'Pass rule failure reasons as JSON array';

-- Pass rate = pass_count / total_cases for the run (per template version).
ALTER TABLE `prompt_test_set_run`
    ADD COLUMN `pass_count` INT NOT NULL DEFAULT 0;
