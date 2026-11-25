"""Модель данных трекера: операции (доходы/расходы), баланс, экспорт.

Не зависит от Kivy, поэтому логику можно тестировать отдельно.
"""
import csv
import json
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date

INCOME = "income"
EXPENSE = "expense"

CATEGORIES = {
    INCOME: ["Продажи", "Услуги", "Инвестиции", "Прочее"],
    EXPENSE: ["Офис", "Зарплаты", "Маркетинг", "Логистика", "Налоги", "Прочее"],
}


@dataclass
class Transaction:
    kind: str
    category: str
    description: str
    amount: float
    date: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    updated: float = field(default_factory=time.time)
    deleted: bool = False


def money(value):
    """12345.5 -> '12 345.50 руб.'"""
    return f"{value:,.2f}".replace(",", " ") + " руб."


class Ledger:
    """Список операций с сохранением в JSON и слиянием с облаком."""

    def __init__(self, path):
        self.path = path
        self._items = {}
        self._lock = threading.RLock()
        self.load()

    # --- хранение -----------------------------------------------------
    def load(self):
        with self._lock:
            self._items = {}
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as f:
                    for row in json.load(f):
                        tx = Transaction(**row)
                        self._items[tx.id] = tx

    def save(self):
        with self._lock:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([asdict(t) for t in self._items.values()], f,
                          ensure_ascii=False, indent=1)

    # --- операции -----------------------------------------------------
    def add(self, kind, category, description, amount, day=None):
        if kind not in CATEGORIES:
            raise ValueError("Неизвестный тип операции")
        if category not in CATEGORIES[kind]:
            raise ValueError("Выберите категорию")
        try:
            amount = float(str(amount).replace(" ", "").replace(",", "."))
        except ValueError:
            raise ValueError("Сумма должна быть числом")
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        tx = Transaction(kind, category, description.strip(), round(amount, 2),
                         day or date.today().isoformat())
        with self._lock:
            self._items[tx.id] = tx
            self.save()
        return tx

    def delete(self, tx_id):
        """Мягкое удаление: запись помечается, чтобы удаление дошло до облака."""
        with self._lock:
            tx = self._items.get(tx_id)
            if tx:
                tx.deleted = True
                tx.updated = time.time()
                self.save()

    def all(self):
        with self._lock:
            return list(self._items.values())

    def active(self):
        return sorted((t for t in self.all() if not t.deleted),
                      key=lambda t: (t.date, t.updated), reverse=True)

    # --- аналитика ----------------------------------------------------
    def total(self, kind):
        return round(sum(t.amount for t in self.active() if t.kind == kind), 2)

    def balance(self):
        return round(self.total(INCOME) - self.total(EXPENSE), 2)

    def by_category(self, kind):
        data = defaultdict(float)
        for t in self.active():
            if t.kind == kind:
                data[t.category] += t.amount
        return dict(sorted(data.items(), key=lambda kv: kv[1], reverse=True))

    # --- облако -------------------------------------------------------
    def merge(self, remote):
        """remote: {id: dict}. Побеждает запись с более поздним updated.
        Возвращает число изменённых локальных записей."""
        changed = 0
        with self._lock:
            for tx_id, row in (remote or {}).items():
                row = dict(row)
                row["id"] = tx_id
                local = self._items.get(tx_id)
                if local is None or row["updated"] > local.updated:
                    self._items[tx_id] = Transaction(**row)
                    changed += 1
            if changed:
                self.save()
        return changed

    def as_payload(self):
        with self._lock:
            return {t.id: asdict(t) for t in self._items.values()}

    # --- экспорт ------------------------------------------------------
    def export_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Дата", "Тип", "Категория", "Описание", "Сумма"])
            for t in self.active():
                w.writerow([t.date, "Доход" if t.kind == INCOME else "Расход",
                            t.category, t.description, f"{t.amount:.2f}"])
        return path
