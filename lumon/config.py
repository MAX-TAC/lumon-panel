"""
LUMON Configuration Manager
Loads settings from /etc/lumon/lumon_config.json
"""

import json
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path("/etc/lumon/lumon_config.json")

class Config:
    """Application configuration loaded from JSON file"""

    def __init__(self):
        self._config: dict = {}
        self.load()

    def load(self) -> bool:
        """Load configuration from JSON file"""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, 'r') as f:
                    self._config = json.load(f)
                return True
        except json.JSONDecodeError as e:
            print(f"⚠️  Error parsing config JSON: {e}")
        except PermissionError:
            print(f"⚠️  Permission denied reading {CONFIG_PATH}")
        except Exception as e:
            print(f"⚠️  Error loading config: {e}")
        return False

    def save(self) -> bool:
        """Save configuration to JSON file"""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self._config, f, indent=4, default=str)
            CONFIG_PATH.chmod(0o600)  # Only root can read
            return True
        except Exception as e:
            print(f"⚠️  Error saving config: {e}")
        return False

    def get(self, key: str, default=None):
        """Get configuration value by key"""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """Set configuration value"""
        self._config[key] = value

    # === Properties for common settings ===

    @property
    def subscription_domain(self) -> str:
        """Domain for subscription endpoint"""
        return self.get("subscription_domain", "panel.example.com")

    @property
    def decoy_domain(self) -> str:
        """Domain for decoy website"""
        return self.get("decoy_domain", "docs.example.com")

    @property
    def subscription_path_template(self) -> str:
        """URL template: /sub/{uuid}/{token}"""
        return self.get("subscription_path_template", "/sub/{uuid}/{token}")

    @property
    def decoy_path(self) -> str:
        """Path to decoy website files"""
        return self.get("decoy_path", "/var/www/decoy")

    @property
    def db_password(self) -> str:
        """PostgreSQL password for 'lumon' user"""
        return self.get("db_password", "")

    @property
    def log_path(self) -> str:
        """Path to log files directory"""
        return self.get("log_path", "/var/log/lumon")

    @property
    def backup_path(self) -> str:
        """Path to backup files directory"""
        return self.get("backup_path", "/var/backups/lumon")

    @property
    def backup_retention_days(self) -> int:
        """Days to keep backups before deletion"""
        return self.get("backup_retention_days", 7)

    @property
    def telegram_bot_token(self) -> Optional[str]:
        """Telegram bot token for notifications"""
        return self.get("telegram_bot_token")

    @property
    def telegram_chat_id(self) -> Optional[str]:
        """Telegram chat ID for notifications"""
        return self.get("telegram_chat_id")

    @property
    def enable_ip_logging(self) -> bool:
        """Log IP addresses of subscription requests"""
        return self.get("enable_ip_logging", True)

    @property
    def enable_rate_limiting(self) -> bool:
        """Enable rate limiting on subscription endpoint"""
        return self.get("enable_rate_limiting", False)


# Global config instance (singleton pattern)
config = Config()
