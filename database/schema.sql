-- Budget planner schema for MySQL 8.0 (utf8mb4).
-- The API also creates missing tables on startup, so running this file is optional.

CREATE DATABASE IF NOT EXISTS budget_planner CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE budget_planner;

CREATE TABLE IF NOT EXISTS `roles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `locked` tinyint(1) NOT NULL,
  `perms` json NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `username` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role_id` int NOT NULL,
  `scope` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_username` (`username`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `user_heads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `section` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `head_code` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `head_name` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_user_heads_user_id` (`user_id`),
  CONSTRAINT `user_heads_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `fiscal_years` (
  `id` int NOT NULL AUTO_INCREMENT,
  `start_year` int NOT NULL,
  `limit_rule` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `total_limit_mode` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `total_limit_value` decimal(15,2) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `start_year` (`start_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `heads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `year_id` int NOT NULL,
  `section` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL,
  `limit_mode` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `limit_value` decimal(15,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_head_code` (`year_id`,`section`,`code`),
  KEY `ix_heads_year_id` (`year_id`),
  CONSTRAINT `heads_ibfk_1` FOREIGN KEY (`year_id`) REFERENCES `fiscal_years` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `head_id` int NOT NULL,
  `code` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL,
  `qty` decimal(15,2) DEFAULT NULL,
  `rate` decimal(15,2) DEFAULT NULL,
  `spread` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `once_month` int NOT NULL,
  `m1` decimal(15,2) NOT NULL,
  `m2` decimal(15,2) NOT NULL,
  `m3` decimal(15,2) NOT NULL,
  `m4` decimal(15,2) NOT NULL,
  `m5` decimal(15,2) NOT NULL,
  `m6` decimal(15,2) NOT NULL,
  `m7` decimal(15,2) NOT NULL,
  `m8` decimal(15,2) NOT NULL,
  `m9` decimal(15,2) NOT NULL,
  `m10` decimal(15,2) NOT NULL,
  `m11` decimal(15,2) NOT NULL,
  `m12` decimal(15,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_lines_head_id` (`head_id`),
  CONSTRAINT `lines_ibfk_1` FOREIGN KEY (`head_id`) REFERENCES `heads` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;

CREATE TABLE IF NOT EXISTS `activity_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ts` datetime NOT NULL,
  `user_id` int DEFAULT NULL,
  `user_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `group_key` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_activity_log_user_id` (`user_id`),
  KEY `ix_activity_log_ts` (`ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
;



-- ---------------------------------------------------------------- version 2: actuals, Tally, TDS, simulations

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
