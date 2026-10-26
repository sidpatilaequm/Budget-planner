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

