"""Графики Matplotlib для экрана аналитики (без pyplot: безопасно для потоков)."""
from matplotlib.figure import Figure

from models import INCOME, EXPENSE

COLORS = ["#2E86AB", "#E4572E", "#76B041", "#F3A712", "#A23B72", "#5C6B73"]


def _empty(fig, title):
    ax = fig.subplots()
    ax.set_title(title)
    ax.axis("off")
    ax.text(0.5, 0.5, "Нет данных", ha="center", va="center", fontsize=16, color="gray")
    return fig


def pie_by_category(ledger, kind):
    title = "Расходы по категориям" if kind == EXPENSE else "Доходы по категориям"
    fig = Figure(figsize=(5, 4), dpi=100)
    data = ledger.by_category(kind)
    if not data:
        return _empty(fig, title)
    ax = fig.subplots()
    ax.pie(list(data.values()), labels=list(data.keys()), colors=COLORS,
           autopct="%1.0f%%", startangle=90, wedgeprops={"edgecolor": "white"})
    ax.set_title(title)
    return fig


def income_vs_expense(ledger):
    fig = Figure(figsize=(5, 4), dpi=100)
    inc, exp = ledger.total(INCOME), ledger.total(EXPENSE)
    if inc == 0 and exp == 0:
        return _empty(fig, "Доходы и расходы")
    ax = fig.subplots()
    bars = ax.bar(["Доходы", "Расходы", "Баланс"], [inc, exp, inc - exp],
                  color=["#76B041", "#E4572E", "#2E86AB"])
    ax.bar_label(bars, labels=[f"{v:,.0f}".replace(",", " ") for v in (inc, exp, inc - exp)])
    ax.set_title("Доходы и расходы, руб.")
    ax.spines[["top", "right"]].set_visible(False)
    return fig
