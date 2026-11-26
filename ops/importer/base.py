"""Shared import machinery: no duplicates, and a report of every doubtful row."""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.contenttypes.models import ContentType

from core.models import ImportRecord


@dataclass
class Report:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: list = field(default_factory=list)   # (source, reason)
    doubtful: list = field(default_factory=list)   # (source, reason)
    checks: list = field(default_factory=list)     # (label, expected, actual, ok)
    notes: list = field(default_factory=list)

    def reject(self, source, reason):
        self.rejected.append((source, reason))

    def doubt(self, source, reason):
        self.doubtful.append((source, reason))

    def check(self, label, expected, actual):
        ok = Decimal(str(expected)) == Decimal(str(actual))
        self.checks.append((label, expected, actual, ok))
        return ok

    @property
    def all_checks_pass(self):
        return all(c[3] for c in self.checks)

    def as_markdown(self, title="Import report", applied=False):
        out = [f"# {title}", "", f"Mode: **{'applied' if applied else 'trial run, nothing saved'}**", "",
               f"- Records created: {self.created}", f"- Records updated: {self.updated}",
               f"- Records already up to date: {self.unchanged}",
               f"- Rows rejected: {len(self.rejected)}", f"- Rows flagged as doubtful: {len(self.doubtful)}", ""]
        out += ["## Totals check", "", "| Check | Expected | Got | Result |", "|---|---|---|---|"]
        for label, exp, act, ok in self.checks:
            out.append(f"| {label} | {exp} | {act} | {'OK' if ok else '**MISMATCH**'} |")
        out += ["", "## Rejected rows (not imported)", ""]
        out += [f"- {s}: {r}" for s, r in self.rejected] or ["- None"]
        out += ["", "## Doubtful rows (imported, flagged for you to check)", ""]
        out += [f"- {s}: {r}" for s, r in self.doubtful] or ["- None"]
        if self.notes:
            out += ["", "## Notes", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(out) + "\n"


def upsert(report, source_key, model, values, lookup=None):
    """
    Create the record the first time; on later runs update the same record.
    `lookup` finds a matching record that existed before the first import.
    """
    rec = ImportRecord.objects.filter(source_key=source_key).first()
    obj = None
    if rec:
        obj = model.objects.filter(pk=rec.object_id).first()
    if obj is None and lookup:
        obj = model.objects.filter(**lookup).first()
    if obj is None:
        obj = model(**values)
        obj.save()
        report.created += 1
    else:
        changed = False
        for k, v in values.items():
            if v in ("", None) and getattr(obj, k) not in ("", None):
                continue  # never wipe a value with a blank from the files
            if getattr(obj, k) != v:
                setattr(obj, k, v)
                changed = True
        if changed:
            obj.save()
            report.updated += 1
        else:
            report.unchanged += 1
    ImportRecord.objects.update_or_create(
        source_key=source_key,
        defaults={"content_type": ContentType.objects.get_for_model(model), "object_id": str(obj.pk)},
    )
    return obj


def dec(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int,)):
        return Decimal(value)
    if isinstance(value, float):
        # Spreadsheet floats: keep the value as Excel shows it (15 significant digits).
        return Decimal(repr(round(value, 9))).normalize()
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None


def money(value):
    v = dec(value)
    return None if v is None else v.quantize(Decimal("0.01"))


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def text(value):
    return "" if value is None else str(value).strip()
