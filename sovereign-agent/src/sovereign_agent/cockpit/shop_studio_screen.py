"""shop_studio_screen.py — the Bot Shop Studio: manage sellable products.

Same clean shape as the Bot Studio: a form (name, blurb, kind, tier, billing,
price, setup fee, Stripe link, role, autonomous/with-Aria) with a save button,
an arrow-carousel to browse/edit/remove, a "📢 publish to shop" button that
posts the storefront to Discord (dry-run), and a "＋ seed starter catalog"
convenience. Prices are entered in dollars and stored as cents.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from sovereign_agent.shop import (
    BILLING_KINDS,
    TIERS,
    Product,
    money,
    validate,
)

# reuse the bot kinds for product 'kind'
try:
    from sovereign_agent.bot_projects import BOT_KINDS
except Exception:  # pragma: no cover
    BOT_KINDS = [("notification-feed", "Notification / feed"), ("other", "Other")]


def cycle_index(idx: int, n: int, delta: int) -> int:
    if n <= 0:
        return 0
    return (idx + delta) % n


def _dollars(cents: int) -> str:
    if not cents:
        return ""
    return f"{cents / 100:.2f}".rstrip("0").rstrip(".")


def _to_cents(text: str) -> int:
    try:
        return int(round(float((text or "0").strip().lstrip("$")) * 100))
    except Exception:  # noqa: BLE001
        return 0


class ShopStudioScreen(ModalScreen):
    """🛒 Shop Studio — manage products, publish the storefront. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def __init__(self, edit: Product | None = None) -> None:
        super().__init__()
        self._products: list[Product] = []
        self._pi = 0
        self._edit = edit

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def _load(self) -> None:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.shop import list_all
            self._products = list_all(SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            self._products = []

    def compose(self):
        self._load()
        e = self._edit
        with VerticalScroll(id="shop-modal"):
            with Horizontal(id="shop-top"):
                yield Button("✕ close", id="shop-exit-btn")
                yield Button("save", id="shop-save-btn", variant="success")
                yield Button("publish", id="shop-publish-btn", variant="primary")
            yield Static("Shop Studio — manage products", id="shop-title")
            yield Static("[dim]Add products, paste Stripe Payment Links, then "
                         "publish the storefront. Prices in dollars. Esc to close.[/dim]",
                         id="shop-help")

            yield Label("Product name")
            yield Input(value=(e.name if e else ""), id="shop-name",
                        placeholder="e.g. Restock Alert Bot")
            yield Label("Blurb (one line)")
            yield Input(value=(e.blurb if e else ""), id="shop-blurb")
            yield Label("Kind")
            yield Select([(lbl, k) for k, lbl in BOT_KINDS],
                         value=(e.kind if e else BOT_KINDS[0][0]),
                         id="shop-kind", allow_blank=False)
            yield Label("Tier")
            yield Select([(lbl, k) for k, lbl in TIERS],
                         value=(e.tier if e else ""), id="shop-tier", allow_blank=False)
            yield Label("Billing")
            yield Select([(lbl, k) for k, lbl in BILLING_KINDS],
                         value=(e.billing if e else "monthly"),
                         id="shop-billing", allow_blank=False)
            yield Label("Price ($)")
            yield Input(value=(_dollars(e.price_cents) if e else ""), id="shop-price",
                        placeholder="8")
            yield Label("One-time setup fee ($, optional)")
            yield Input(value=(_dollars(e.setup_cents) if e else ""), id="shop-setup",
                        placeholder="30")
            yield Label("Stripe Payment Link (optional)")
            yield Input(value=(e.stripe_url if e else ""), id="shop-stripe",
                        placeholder="https://buy.stripe.com/...")
            yield Label("Access role granted (optional)")
            yield Input(value=(e.access_role if e else ""), id="shop-role",
                        placeholder="Subscriber-Pro")
            yield Label("Mode")
            yield Select([("Autonomous — runs without Aria", "false"),
                          ("With-Aria — needs her awake", "true")],
                         value=("true" if (e and e.attended) else "false"),
                         id="shop-attended", allow_blank=False)

            yield Static("[dim]— your products —[/dim]", id="shop-browse-sep")
            with Horizontal(classes="shop-carousel"):
                yield Button("◂", id="shop-prev")
                yield Static("", id="shop-label", classes="shop-carousel-label")
                yield Button("▸", id="shop-next")
            with Horizontal(id="shop-actions"):
                yield Button("edit", id="shop-edit")
                yield Button("+ seed starter", id="shop-seed")
                yield Button("remove", id="shop-remove", variant="error")

    def on_mount(self) -> None:
        self._refresh_browse()

    def _refresh_browse(self) -> None:
        try:
            lbl = self.query_one("#shop-label", Static)
            if self._products:
                p = self._products[self._pi]
                mode = "auto" if p.runs_without_her else "w/Aria"
                lbl.update(f"[b]{p.name}[/b] — {p.price_label()} {mode}  "
                           f"[dim]({self._pi + 1}/{len(self._products)})[/dim]")
            else:
                lbl.update("[dim](no products yet — fill the form or seed the starter set)[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _collect(self) -> Product:
        def v(wid: str) -> str:
            try:
                return self.query_one(f"#{wid}", Input).value.strip()
            except Exception:  # noqa: BLE001
                return ""

        def sel(wid: str, default: str) -> str:
            try:
                return str(self.query_one(f"#{wid}", Select).value or default)
            except Exception:  # noqa: BLE001
                return default

        return Product(
            name=v("shop-name"), blurb=v("shop-blurb"),
            kind=sel("shop-kind", "notification-feed"),
            tier=sel("shop-tier", ""), billing=sel("shop-billing", "monthly"),
            price_cents=_to_cents(v("shop-price")),
            setup_cents=_to_cents(v("shop-setup")),
            stripe_url=v("shop-stripe"), access_role=v("shop-role"),
            attended=(sel("shop-attended", "false") == "true"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "shop-exit-btn":
            self.app.pop_screen(); return
        if bid == "shop-save-btn":
            self._save(); return
        if bid == "shop-publish-btn":
            self._publish(); return
        if bid == "shop-seed":
            self._seed(); return
        if bid == "shop-prev" and self._products:
            self._pi = cycle_index(self._pi, len(self._products), -1); self._refresh_browse()
        elif bid == "shop-next" and self._products:
            self._pi = cycle_index(self._pi, len(self._products), +1); self._refresh_browse()
        elif bid == "shop-edit" and self._products:
            self.app.pop_screen()
            self.app.push_screen(ShopStudioScreen(edit=self._products[self._pi]))
        elif bid == "shop-remove" and self._products:
            self._remove_current()

    def _save(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.shop import save as _save
        prod = self._collect()
        errs = validate(prod)
        if errs:
            self._toast(f"can't save: {errs[0]}"); return
        try:
            _save(prod, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"save failed: {type(exc).__name__}"); return
        self._toast(f"saved '{prod.name}' ({prod.price_label()}) 💛")
        self._load(); self._refresh_browse()

    def _publish(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.shop import publish_storefront
        try:
            r = publish_storefront(SETTINGS.paths.data_dir, live=False)
            self._toast(f"storefront preview built (dry-run, nothing sent) · {r.detail[:50]}")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"publish failed: {type(exc).__name__}")

    def _seed(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.shop import seed_starter_catalog
        try:
            written = seed_starter_catalog(SETTINGS.paths.data_dir)
            self._toast(f"seeded {len(written)} starter product(s)")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"seed failed: {type(exc).__name__}")
        self._load(); self._refresh_browse()

    def _remove_current(self) -> None:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.shop import delete
        name = self._products[self._pi].name
        try:
            delete(name, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._load()
        self._pi = min(self._pi, max(0, len(self._products) - 1))
        self._refresh_browse()
        self._toast(f"removed '{name}'")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#shop-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    ShopStudioScreen { align: center middle; background: $surface 60%; }
    #shop-modal {
        width: 74; height: 92%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #shop-top { height: 3; margin-bottom: 1; }
    #shop-top Button { width: 1fr; margin-right: 1; }
    #shop-title { text-style: bold; margin-bottom: 1; }
    #shop-help { height: 3; color: $text-muted; margin-bottom: 1; }
    ShopStudioScreen Input, ShopStudioScreen Select { width: 100%; margin-bottom: 1; }
    ShopStudioScreen Label { color: $text-muted; }
    #shop-browse-sep { margin-top: 1; }
    .shop-carousel { height: 3; margin-bottom: 1; }
    .shop-carousel Button { width: 6; }
    .shop-carousel-label { width: 1fr; content-align: center middle; }
    #shop-actions { height: 3; }
    #shop-actions Button { width: 1fr; margin-right: 1; }
    """
