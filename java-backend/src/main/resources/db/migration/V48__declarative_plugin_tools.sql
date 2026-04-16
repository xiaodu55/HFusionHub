-- Low-code plugins contain declarative HTTP GET tools created in the web UI.
ALTER TABLE plugin
    ADD COLUMN plugin_kind VARCHAR(24) NOT NULL DEFAULT 'package' AFTER source,
    ADD COLUMN tool_specs_json LONGTEXT DEFAULT NULL AFTER permissions;

