"""Persistent settings for services owned by the single V2 plugin."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4


def merged(defaults, saved):
    result = copy.deepcopy(defaults)
    for key, value in saved.items():
        result[key] = merged(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


class ExtensionSettings(dict):
    def __init__(self, root, extension_id):
        self.root = Path(root) / "extensions" / extension_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "config.json"
        packaged = Path(__file__).parent / extension_id
        self.schema = json.loads((packaged / "settings-schema.json").read_text(encoding="utf-8"))
        defaults = json.loads((packaged / "settings-defaults.json").read_text(encoding="utf-8"))
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            saved = {}
        if type(saved) is not dict:
            raise ValueError("extension settings must be an object")
        super().__init__(merged(defaults, saved))

    def save_config(self):
        payload = json.dumps(self, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        temporary = self.path.with_name(".config-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def revision(self):
        return hashlib.sha256(json.dumps(self, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def secret(name):
        key = name.casefold()
        return any(part in key for part in ("token", "secret", "password", "cookie", "api_key", "access_key",
                                           "sessdata", "auth_code", "authorization"))

    def public(self):
        def redact(value):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    result[key] = "" if self.secret(key) else redact(item)
                    if self.secret(key):
                        result[key + "_configured"] = bool(item)
                return result
            if type(value) is list:
                return [redact(item) for item in value]
            return value
        return redact(self)

    def update_fields(self, updates):
        def validate(changes, schema):
            result = {}
            for key, value in changes.items():
                field = schema.get(key)
                if not isinstance(field, dict):
                    raise ValueError("unknown extension setting: " + key)
                kind = field.get("type")
                if kind == "object":
                    if type(value) is not dict:
                        raise ValueError("setting must be an object: " + key)
                    result[key] = validate(value, field.get("items", {}))
                else:
                    types = {"bool": (bool,), "int": (int,), "float": (int, float),
                             "string": (str,), "text": (str,), "list": (list,),
                             "template_list": (list,)}
                    if type(value) not in types.get(kind, (str,)):
                        raise ValueError("invalid setting type: " + key)
                    if "options" in field and value not in field["options"]:
                        raise ValueError("invalid setting option: " + key)
                    if kind in ("int", "float"):
                        bounds = field.get("slider", {})
                        minimum = bounds.get("min", field.get("minimum"))
                        maximum = bounds.get("max", field.get("maximum"))
                        if key == "port" or key.endswith("_port"):
                            minimum, maximum = 1, 65535
                        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                            raise ValueError("setting is outside its allowed range: " + key)
                    if kind == "list" and any(type(item) is not str for item in value):
                        raise ValueError("setting must contain text values: " + key)
                    if kind == "template_list":
                        templates = field.get("templates", {})
                        rows = []
                        for item in value:
                            if type(item) is not dict:
                                raise ValueError("setting must contain template objects: " + key)
                            template = item.get("__template_key", "default")
                            if template not in templates:
                                raise ValueError("unknown settings template: " + key)
                            values = validate({name: part for name, part in item.items() if name != "__template_key"},
                                              templates[template].get("items", {}))
                            if "__template_key" in item:
                                values["__template_key"] = template
                            rows.append(values)
                        value = rows
                    if self.secret(key) and value == "":
                        continue
                    result[key] = value
            return result
        checked = validate(updates, self.schema)
        json.dumps(checked, allow_nan=False)
        new = merged(self, checked)
        previous = copy.deepcopy(self)
        self.clear()
        self.update(new)
        try:
            self.save_config()
        except Exception:
            self.clear()
            self.update(previous)
            raise
