"""Трекер доходов и расходов на Kivy (практическое задание к лекции 6).

Что добавлено к примеру из лекции:
  1. графики Matplotlib (Kivy Garden) — экран «Аналитика»;
  2. синхронизация с облаком по REST API (Firebase Realtime Database);
  3. категории доходов и расходов и баланс.
"""
import io
import os
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (ListProperty, NumericProperty, StringProperty)
from kivy.uix.boxlayout import BoxLayout
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager

try:  # новые версии пакета
    from kivy_garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
except Exception:  # старый путь через garden
    try:
        from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
    except Exception:
        FigureCanvasKivyAgg = None

import charts
from cloud import CloudError, CloudSync
from models import CATEGORIES, EXPENSE, INCOME, Ledger, money

import json

GREEN = [0.1, 0.55, 0.2, 1]
RED = [0.8, 0.15, 0.15, 1]


class TransactionRow(BoxLayout):
    """Строка списка операций (RecycleView подставляет значения по ключам data)."""
    tx_id = StringProperty("")
    category_text = StringProperty("")
    desc_text = StringProperty("")
    amount_text = StringProperty("")
    amount_color = ListProperty([0, 0, 0, 1])


class AddTransactionPopup(Popup):
    kind = StringProperty(EXPENSE)

    def __init__(self, on_save, **kwargs):
        super().__init__(**kwargs)
        self.on_save = on_save
        self.set_kind(EXPENSE)

    def set_kind(self, kind):
        self.kind = kind
        spinner = self.ids.category_spinner
        spinner.values = CATEGORIES[kind]
        spinner.text = "Выберите категорию"
        self.ids.error_label.text = ""

    def save(self):
        try:
            self.on_save(self.kind, self.ids.category_spinner.text,
                         self.ids.description_input.text,
                         self.ids.amount_input.text)
        except ValueError as e:
            self.ids.error_label.text = str(e)
            return
        self.dismiss()


class MainScreen(Screen):
    balance_text = StringProperty("")
    income_text = StringProperty("")
    expense_text = StringProperty("")
    balance_color = ListProperty(GREEN)
    status_text = StringProperty("")

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        ledger = App.get_running_app().ledger
        balance = ledger.balance()
        self.balance_text = money(balance)
        self.balance_color = GREEN if balance >= 0 else RED
        self.income_text = money(ledger.total(INCOME))
        self.expense_text = money(ledger.total(EXPENSE))
        rows = []
        for t in ledger.active():
            sign, color = ("+", GREEN) if t.kind == INCOME else ("−", RED)
            rows.append({
                "tx_id": t.id,
                "category_text": f"{t.category}  ·  {t.date}",
                "desc_text": t.description or "—",
                "amount_text": f"{sign}{money(t.amount)}",
                "amount_color": color,
            })
        self.ids.rv.data = rows


class ChartsScreen(Screen):
    mode = StringProperty("expense")

    def on_pre_enter(self, *args):
        self.show(self.mode)

    @staticmethod
    def _chart_widget(fig):
        """Kivy Garden, если установлен; иначе картинка из Matplotlib."""
        if FigureCanvasKivyAgg is not None:
            return FigureCanvasKivyAgg(fig)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        return Image(texture=CoreImage(buf, ext="png").texture, fit_mode="contain")

    def show(self, mode):
        self.mode = mode
        box = self.ids.chart_box
        box.clear_widgets()
        ledger = App.get_running_app().ledger
        if mode == "expense":
            fig = charts.pie_by_category(ledger, EXPENSE)
        elif mode == "income":
            fig = charts.pie_by_category(ledger, INCOME)
        else:
            fig = charts.income_vs_expense(ledger)
        box.add_widget(self._chart_widget(fig))


class SettingsScreen(Screen):
    def on_pre_enter(self, *args):
        cfg = App.get_running_app().settings_data
        self.ids.url_input.text = cfg.get("url", "")
        self.ids.token_input.text = cfg.get("token", "")


class TrackerApp(App):
    title = "Бизнес-трекер"

    def build(self):
        Window.clearcolor = (0.97, 0.97, 0.98, 1)
        # tracker.kv подгружается Kivy автоматически (по имени класса TrackerApp)
        self.ledger = Ledger(os.path.join(self.user_data_dir, "transactions.json"))
        self.settings_path = os.path.join(self.user_data_dir, "settings.json")
        self.settings_data = self._load_settings()
        sm = ScreenManager()
        sm.add_widget(MainScreen(name="main"))
        sm.add_widget(ChartsScreen(name="charts"))
        sm.add_widget(SettingsScreen(name="settings"))
        return sm

    # --- настройки ----------------------------------------------------
    def _load_settings(self):
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_settings(self, url, token):
        self.settings_data = {"url": url.strip(), "token": token.strip()}
        os.makedirs(self.user_data_dir, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings_data, f)
        self.root.current = "main"
        self.set_status("Настройки сохранены")

    # --- действия -----------------------------------------------------
    def go(self, name):
        self.root.current = name

    def open_add_popup(self):
        AddTransactionPopup(on_save=self.add_transaction).open()

    def add_transaction(self, kind, category, description, amount):
        self.ledger.add(kind, category, description, amount)  # ValueError покажет попап
        self.root.get_screen("main").refresh()
        self.set_status("Операция добавлена")

    def delete_transaction(self, tx_id):
        self.ledger.delete(tx_id)
        self.root.get_screen("main").refresh()
        self.set_status("Операция удалена")

    def export_csv(self):
        path = self.ledger.export_csv(os.path.join(self.user_data_dir, "export.csv"))
        self.set_status(f"Экспорт: {path}")

    def add_demo_data(self):
        demo = [(INCOME, "Продажи", "Заказ №101", 120000), (INCOME, "Услуги", "Консультация", 35000),
                (INCOME, "Инвестиции", "Дивиденды", 15000), (EXPENSE, "Зарплаты", "Аванс", 70000),
                (EXPENSE, "Офис", "Аренда", 30000), (EXPENSE, "Маркетинг", "Реклама", 18000),
                (EXPENSE, "Логистика", "Доставка", 9500), (EXPENSE, "Налоги", "НДС", 12000)]
        for kind, cat, desc, amount in demo:
            self.ledger.add(kind, cat, desc, amount)
        self.go("main")
        self.root.get_screen("main").refresh()
        self.set_status("Демо-данные добавлены")

    def set_status(self, text):
        self.root.get_screen("main").status_text = text

    # --- облако -------------------------------------------------------
    def sync(self):
        cfg = self.settings_data
        self.set_status("Синхронизация...")
        threading.Thread(target=self._sync_worker, args=(cfg.get("url", ""), cfg.get("token", "")),
                         daemon=True).start()

    def _sync_worker(self, url, token):
        try:
            received, total = CloudSync(url, token).sync(self.ledger)
            msg = f"Готово: получено {received}, в облаке {total}"
        except CloudError as e:
            msg = f"Ошибка: {e}"
        Clock.schedule_once(lambda dt: self._after_sync(msg))

    def _after_sync(self, msg):
        self.root.get_screen("main").refresh()
        self.set_status(msg)


if __name__ == "__main__":
    TrackerApp().run()
