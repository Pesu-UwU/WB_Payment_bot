from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from src.config import SUBSCRIPTION_ENABLED, SUBSCRIPTION_GRACE_DAYS

@dataclass
class SubscriptionInfo:
    enabled: bool
    valid_until: Optional[datetime] = None
    note: str = ""

class SubscriptionManager:
    def __init__(self):
        self.grace_days = SUBSCRIPTION_GRACE_DAYS

    def check_access(self, user_id: int) -> SubscriptionInfo:
        if not SUBSCRIPTION_ENABLED:
            return SubscriptionInfo(enabled=True, note="Подписки выключены, доступ открыт для всех.")
        valid_until = datetime.now(timezone.utc) + timedelta(days=self.grace_days)
        return SubscriptionInfo(enabled=True, valid_until=valid_until, note="Грейс-период по умолчанию.")

    def set_user_status(self, user_id: int, enabled: bool, valid_until: Optional[datetime] = None):
        pass
