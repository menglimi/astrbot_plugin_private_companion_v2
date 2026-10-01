"""Host supplied solar-term table used by the private conversation calendar.

The conversation layer only accepts an injected lookup object and never derives
terms itself (see ``companion_v2/conversation/solar_terms.py``). Until now no
host ever constructed one, so ``automatic_solar_terms`` was permanently
``unavailable``. This module provides the missing producer.

The table is the standard mean-value approximation also used by the common
Chinese calendar libraries: each term's civil day is ``int(Y * 0.2422 + C) -
int((Y - 1) / 4)`` for the two-digit year ``Y``, plus the documented
corrections for the few exceptional years. It is accurate for the years the
formula was fitted to and can drift by a day at the edges, which is why the
value is only ever injected as non-evidentiary atmosphere material: date
context marks it ``host_solar_term_port`` and the calendar instruction tells
the model not to treat it as fact.
"""

from datetime import date


TERM_NAMES = (
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑",
    "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
)

# (month, date coefficient, {exceptional year: day correction}) per term, in the
# order of TERM_NAMES.
_TERM_COEFFICIENTS = (
    (1, 6.11, {1982: 1, 2019: -1}), (1, 20.84, {2082: 1}),
    (2, 4.6295, {}), (2, 19.4599, {}),
    (3, 6.3826, {}), (3, 21.4155, {}),
    (4, 5.59, {}), (4, 20.888, {}),
    (5, 6.318, {}), (5, 21.86, {}),
    (6, 6.5, {}), (6, 22.20, {}),
    (7, 7.928, {}), (7, 23.65, {1922: 1}),
    (8, 8.35, {}), (8, 23.95, {}),
    (9, 8.44, {}), (9, 23.822, {}),
    (10, 9.098, {}), (10, 24.218, {}),
    (11, 8.218, {}), (11, 23.08, {}),
    (12, 7.9, {}), (12, 22.60, {}),
)

MINIMUM_YEAR = 1901
MAXIMUM_YEAR = 2099


class SolarTermTablePort:
    """Synchronous year lookup returning every term of that civil year."""

    kind = "host_table"

    def __init__(self, *, minimum_year=MINIMUM_YEAR, maximum_year=MAXIMUM_YEAR):
        if type(minimum_year) is not int or type(maximum_year) is not int or minimum_year > maximum_year:
            raise ValueError("solar term year range is invalid")
        self.minimum_year = minimum_year
        self.maximum_year = maximum_year
        self._cache = {}

    def terms(self, year):
        """Return this year's terms as ``((date, name), ...)`` in calendar order."""
        if type(year) is not int or not self.minimum_year <= year <= self.maximum_year:
            raise ValueError("solar term year is outside the supported range")
        cached = self._cache.get(year)
        if cached is not None:
            return cached
        two_digit = year % 100
        rows = []
        for index, (month, coefficient, exceptions) in enumerate(_TERM_COEFFICIENTS):
            day = int(two_digit * 0.2422 + coefficient) - int((two_digit - 1) / 4) + exceptions.get(year, 0)
            rows.append((date(year, month, day), TERM_NAMES[index]))
        result = tuple(sorted(rows))
        self._cache[year] = result
        return result

    def lookup(self, year):
        """The port contract: return ``(date, name)`` pairs, or raise for unknown.

        ``lookup_solar_terms`` reads each row as a ``(day, name)`` pair, so the
        names must be flat strings here; nesting them would be rejected as
        ``unknown`` before the table is ever consulted.
        """
        return self.terms(year)


def configured_solar_term_port(settings=None):
    """Build the port, optionally narrowed by explicit host settings.

    There is no credential or network call behind this table, so it needs no
    enable flag of its own: the single operator switch is the private-window
    field ``conversation.perception.automatic_solar_terms_enabled`` (default
    off), which decides whether an injected table is consulted at all. Host
    settings may only narrow the supported year range.
    """
    if settings is None:
        return SolarTermTablePort()
    if type(settings) is not dict:
        raise ValueError("solar term host settings must be an object")
    minimum = settings.get("minimum_year", MINIMUM_YEAR)
    maximum = settings.get("maximum_year", MAXIMUM_YEAR)
    return SolarTermTablePort(minimum_year=minimum, maximum_year=maximum)


__all__ = ["SolarTermTablePort", "configured_solar_term_port", "TERM_NAMES",
           "MINIMUM_YEAR", "MAXIMUM_YEAR"]
