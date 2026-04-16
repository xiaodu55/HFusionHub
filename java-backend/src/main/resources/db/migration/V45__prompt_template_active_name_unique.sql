-- Keep uniqueness for active answer plans while allowing repeated names in the recycle bin.
ALTER TABLE `prompt_template`
    DROP INDEX `uk_prompt_template_user_name_deleted`,
    ADD COLUMN `active_name` VARCHAR(100)
        GENERATED ALWAYS AS (IF(`deleted` = 0, `name`, NULL)) STORED
        AFTER `name`,
    ADD UNIQUE KEY `uk_prompt_template_user_active_name` (`user_id`, `active_name`);
