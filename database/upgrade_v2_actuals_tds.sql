-- Budget Planner version 2: actuals (Tally and manual), TDS, alerts and simulations.
-- Safe to apply to an existing MySQL 8.0 database; it only adds tables and does not touch existing data.
-- You normally do not need it: the API creates these tables itself when it starts.
-- If you run it by hand and an index already exists, MySQL reports it; that error can be ignored.

CREATE TABLE IF NOT EXISTS ledger_maps (
	id INTEGER NOT NULL AUTO_INCREMENT,
	ledger_name VARCHAR(200) NOT NULL,
	section VARCHAR(10) NOT NULL,
	head_code VARCHAR(36),
	line_code VARCHAR(36),
	tds_code VARCHAR(20),
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (ledger_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS actual_entries (
	id INTEGER NOT NULL AUTO_INCREMENT,
	date VARCHAR(10) NOT NULL,
	fy_start INTEGER NOT NULL,
	month INTEGER NOT NULL,
	section VARCHAR(10) NOT NULL,
	head_code VARCHAR(36),
	line_code VARCHAR(36),
	ledger_name VARCHAR(200) NOT NULL,
	party VARCHAR(200) NOT NULL,
	voucher_type VARCHAR(60) NOT NULL,
	voucher_no VARCHAR(60) NOT NULL,
	narration VARCHAR(500) NOT NULL,
	amount NUMERIC(15, 2) NOT NULL,
	tds_code VARCHAR(20),
	tds_amount NUMERIC(15, 2) NOT NULL,
	source VARCHAR(10) NOT NULL,
	external_id VARCHAR(120),
	created_by_name VARCHAR(120) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_actual_external UNIQUE (external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_actual_entries_fy_start ON actual_entries (fy_start);

CREATE INDEX ix_actual_entries_head_code ON actual_entries (head_code);

CREATE INDEX ix_actual_entries_section ON actual_entries (section);

CREATE INDEX ix_actual_entries_date ON actual_entries (date);

CREATE TABLE IF NOT EXISTS tds_parties (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(200) NOT NULL,
	pan VARCHAR(10) NOT NULL,
	kind VARCHAR(12) NOT NULL,
	tds_code VARCHAR(20),
	lower_rate NUMERIC(6, 3),
	lower_cert VARCHAR(40) NOT NULL,
	lower_valid_to VARCHAR(10) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tds_sections (
	id INTEGER NOT NULL AUTO_INCREMENT,
	code VARCHAR(20) NOT NULL,
	label VARCHAR(160) NOT NULL,
	new_ref VARCHAR(60) NOT NULL,
	old_ref VARCHAR(20) NOT NULL,
	rate_ind NUMERIC(6, 3) NOT NULL,
	rate_other NUMERIC(6, 3) NOT NULL,
	single_limit NUMERIC(15, 2),
	annual_limit NUMERIC(15, 2),
	monthly_limit NUMERIC(15, 2),
	active BOOL NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_tds (
	id INTEGER NOT NULL AUTO_INCREMENT,
	head_code VARCHAR(36) NOT NULL,
	line_code VARCHAR(36) NOT NULL,
	tds_code VARCHAR(20) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_line_tds UNIQUE (head_code, line_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tds_deposits (
	id INTEGER NOT NULL AUTO_INCREMENT,
	fy_start INTEGER NOT NULL,
	month INTEGER NOT NULL,
	amount NUMERIC(15, 2) NOT NULL,
	paid_on VARCHAR(10) NOT NULL,
	challan VARCHAR(40) NOT NULL,
	created_by_name VARCHAR(120) NOT NULL,
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_tds_deposits_fy_start ON tds_deposits (fy_start);

CREATE TABLE IF NOT EXISTS tds_returns (
	id INTEGER NOT NULL AUTO_INCREMENT,
	fy_start INTEGER NOT NULL,
	quarter INTEGER NOT NULL,
	filed_on VARCHAR(10) NOT NULL,
	ack VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_tds_return UNIQUE (fy_start, quarter)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_settings (
	`key` VARCHAR(60) NOT NULL,
	value JSON NOT NULL,
	PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scenarios (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(120) NOT NULL,
	params JSON NOT NULL,
	created_by_name VARCHAR(120) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS alert_dismissals (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	alert_key VARCHAR(160) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_alert_dismissal UNIQUE (user_id, alert_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_alert_dismissals_user_id ON alert_dismissals (user_id);
