from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ScopeKind
from companion_v2.proactive.balance_events import SOURCE_OWNER as BALANCE_OWNER
from companion_v2.proactive.material_pool import read_material_pool
from companion_v2.proactive.news_events import SOURCE_OWNER as NEWS_OWNER


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def record(owner, source_id, payload, *, expires_at=None):
    return NS(
        reference=NS(owner=owner, source_id=source_id,
                     version=NS(lineage_id=source_id + "-lineage", revision=1),
                     issued_at=NOW - timedelta(minutes=5), expires_at=expires_at),
        payload=payload,
        content_hash=digest(payload),
    )


class ProactiveMaterialPoolTests(unittest.TestCase):
    def test_projects_current_sources_and_hides_balance_amount_by_default(self):
        news_payload = json.dumps({"title": "天气提醒", "summary": "下午可能有雨", "source": "天气台"})
        balance_payload = json.dumps({"level": "critical", "amount": 12.5, "currency": "CNY"})
        sources = Mock()
        sources.list_readable_current.return_value = (
            record(NEWS_OWNER, "news-1", news_payload, expires_at=NOW + timedelta(minutes=10)),
            record(BALANCE_OWNER, "balance-1", balance_payload),
        )
        schedule = NS(contacts=NS(sources=sources), runtime=NS(read_one=Mock(return_value=None)),
                      tasks=NS(identity=object()))
        context = NS(scope=NS(kind=ScopeKind.PRIVATE, key="private-a"),
                     audience=NS(recipients=("recipient-a",)), actor=object())

        result = read_material_pool(schedule, context, observed_at=NOW, settings={})

        self.assertEqual(result["count"], 2)
        news = next(item for item in result["items"] if item["source"] == "资讯源")
        self.assertEqual(news["title"], "天气提醒")
        self.assertEqual(news["detail"], "下午可能有雨")
        self.assertEqual(news["expires_at"], (NOW + timedelta(minutes=10)).isoformat())
        balance = next(item for item in result["items"] if item["source"] == "服务余额")
        self.assertNotIn("12.5", balance["detail"])

    def test_group_scope_returns_empty_without_reading_sources(self):
        schedule = object()
        context = NS(scope=NS(kind=ScopeKind.GROUP))

        result = read_material_pool(schedule, context, observed_at=NOW, settings={})

        self.assertEqual(result, {"observed_at": NOW.isoformat(), "items": [], "count": 0})
