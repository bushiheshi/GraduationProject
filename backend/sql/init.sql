CREATE DATABASE IF NOT EXISTS aigc_platform
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE aigc_platform;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT NOT NULL AUTO_INCREMENT,
  account VARCHAR(64) NOT NULL,
  name VARCHAR(64) NOT NULL,
  role ENUM('student', 'teacher') NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_account (account),
  KEY idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_conversations (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  title VARCHAR(120) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_chat_conversations_user_id (user_id),
  KEY idx_chat_conversations_updated_at (updated_at),
  CONSTRAINT fk_chat_conversations_user_id FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_records (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  conversation_id BIGINT NULL,
  model_name VARCHAR(64) NOT NULL,
  generated_at DATETIME NOT NULL,
  prompt TEXT NOT NULL,
  content LONGTEXT NOT NULL,
  citations JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_chat_user_id (user_id),
  KEY idx_chat_conversation_id (conversation_id),
  KEY idx_chat_generated_at (generated_at),
  CONSTRAINT fk_chat_records_user_id FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_chat_records_conversation_id FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS homework_submissions (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  conversation_id BIGINT NOT NULL,
  conversation_title VARCHAR(120) NOT NULL,
  model_name VARCHAR(64) NOT NULL,
  source_generated_at DATETIME NOT NULL,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  prompt TEXT NOT NULL,
  content LONGTEXT NOT NULL,
  citations JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_homework_submissions_user_id (user_id),
  KEY idx_homework_submissions_conversation_id (conversation_id),
  KEY idx_homework_submissions_submitted_at (submitted_at),
  CONSTRAINT fk_homework_submissions_user_id FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_homework_submissions_conversation_id FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
