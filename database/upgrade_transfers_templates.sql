-- Budget Planner: budget transfer audit table.
-- Safe to apply to an existing MySQL 8.0 database.
-- Does not modify existing budget lines, users, roles, or fiscal years.

CREATE TABLE IF NOT EXISTS `budget_transfers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `year_id` int NOT NULL,
  `section` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` int NOT NULL COMMENT '0 = April, 11 = March',
  `from_line_id` int DEFAULT NULL,
  `to_line_id` int DEFAULT NULL,
  `from_head_code` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `from_head_name` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  `from_line_name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_head_code` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_head_name` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_line_name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(15,2) NOT NULL,
  `reason` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'done',
  `reverses_id` int DEFAULT NULL,
  `created_by_id` int DEFAULT NULL,
  `created_by_name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_budget_transfers_year_id` (`year_id`),
  KEY `ix_budget_transfers_from_line_id` (`from_line_id`),
  KEY `ix_budget_transfers_to_line_id` (`to_line_id`),
  KEY `ix_budget_transfers_reverses_id` (`reverses_id`),
  CONSTRAINT `fk_budget_transfers_year`
    FOREIGN KEY (`year_id`) REFERENCES `fiscal_years` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_budget_transfers_from_line`
    FOREIGN KEY (`from_line_id`) REFERENCES `lines` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_budget_transfers_to_line`
    FOREIGN KEY (`to_line_id`) REFERENCES `lines` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_budget_transfers_reverses`
    FOREIGN KEY (`reverses_id`) REFERENCES `budget_transfers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
