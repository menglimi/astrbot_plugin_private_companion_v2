"""Read-only acquaintance directory for the management page.

The directory is a governance projection over acquaintance cards. It never
exposes private memory bodies, never edits cards and never becomes a
member-facing API; authorization happens in the host API layer.
"""

import json

from .models import KIND, aggregate, directory_display_name


MAX_DIRECTORY = 512


def _route_tuple(route):
    return (route["platform"], route["bot_id"], route["account_id"], route["role_id"])


class PersonAcquaintanceDirectory:
    def __init__(self, runtime):
        self.runtime = runtime

    def directory(self, routes):
        """List cards whose pinned route is one of the authorized routes, plus
        aggregate presence views for the page's two directory types."""
        allowed = {_route_tuple(route) for route in routes}
        rows = self.runtime.read_all(
            """SELECT * FROM memory_views WHERE kind = ? AND state = 'active'
               ORDER BY updated_at DESC, view_id DESC LIMIT ?""", (KIND, MAX_DIRECTORY))
        persons = []
        for row in rows:
            document = json.loads(row["document_json"])
            route = document.get("route")
            if type(route) is not dict or _route_tuple(route) not in allowed:
                continue
            persons.append(self._person(route, document, row["updated_at"], row["revision"]))
        persons.sort(key=lambda item: item["total"]["last_seen"] or "", reverse=True)
        return {"persons": persons, "counts": self._counts(persons)}

    @staticmethod
    def _counts(persons):
        """私聊用户与群友是**两个独立的维度**，不是一道二选一。

        同一个人可以既私聊过、又是某几个群的成员；只按"有没有私聊"切一刀，
        那些"在群里认识、后来也聊过"的人就会从群友视图里消失——而他们确实
        还在那些群里。所以这里给三个数（私聊用户 / 群友 / 两者），
        页面各自的筛选与计数都取自同一份口径。
        """
        private_chat = sum(1 for person in persons if person["private_chat"])
        group_member = sum(1 for person in persons if person["group_member"])
        both = sum(1 for person in persons if person["private_chat"] and person["group_member"])
        return {
            "total": len(persons),
            "private_chat": private_chat,
            "group_member": group_member,
            "both": both,
            # 兼容既有读法：private_only / group_only 是同一个人只出现在一侧的情形。
            "private_only": private_chat - both,
            "group_only": group_member - both,
        }

    def _person(self, route, document, updated_at, revision):
        contexts = document["contexts"]
        private_entry = contexts.get("private")
        groups = {key.removeprefix("group:"): {"msg_count": entry["msg_count"], "active_days": entry["active_days"],
                                               "last_seen": entry["last_seen"]}
                  for key, entry in contexts.items() if key.startswith("group:")}
        name, name_basis = directory_display_name(document)
        total = aggregate(document)
        return {"subject_id": route["subject_id"],
                "native_account_id": document.get("native_account_id"),
                "display_name": name, "name_basis": name_basis,
                "admin_nickname": document.get("admin_nickname"),
                "admin_nickname_updated_at": document.get("admin_nickname_updated_at"),
                "revision": revision,
                "platform": route["platform"], "account_id": route["account_id"],
                "role_id": route["role_id"], "bot_id": route["bot_id"],
                "private_chat": private_entry is not None,
                # 群友 = 在至少一个群里出现过；与 private_chat 互相独立。
                "group_member": bool(groups),
                "private": None if private_entry is None else
                    {"msg_count": private_entry["msg_count"], "active_days": private_entry["active_days"],
                     "last_seen": private_entry["last_seen"]},
                "groups": groups,
                "total": {"msg_count": total["msg_count"], "active_days": total["active_days"],
                          "first_seen": total["first_seen"], "last_seen": total["last_seen"]},
                "updated_at": updated_at}
