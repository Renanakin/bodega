"""Toma screenshots de las pantallas principales para el manual de usuario."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://localhost:8080"
OUT = Path(r"C:\Users\Tranquilidad\auditoria-fase5\manual_screens")
OUT.mkdir(parents=True, exist_ok=True)

PANTALLAS = [
    ("dashboard", "/dashboard"),
    ("warehouses", "/warehouses"),
    ("products", "/products"),
    ("inventory", "/inventory"),
    ("solicitudes", "/solicitudes"),
    ("consolidador", "/consolidador"),
    ("multibodega", "/multibodega"),
    ("replenishment", "/replenishment"),
    ("ordenes-compra", "/ordenes-compra"),
    ("receipts", "/receipts"),
    ("reports", "/reports"),
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # Login
        page.goto(f"{URL}/login", wait_until="networkidle")
        page.locator("input").nth(0).fill("admin")
        page.locator('input[type="password"]').fill("admin12345")
        page.locator('button[type="submit"]').click()
        page.wait_for_url(f"{URL}/dashboard", timeout=10000)
        print("[OK] login")

        for name, path in PANTALLAS:
            try:
                page.goto(f"{URL}{path}", wait_until="domcontentloaded", timeout=15000)
                time.sleep(3.0)  # mas tiempo para JS
                # Esperar a que haya al menos un h1 o tabla renderizada
                try:
                    page.wait_for_selector("h1, table, .grid", timeout=5000)
                except Exception:
                    pass
                out_path = OUT / f"{name}.png"
                page.screenshot(path=str(out_path), full_page=False)
                print(f"[OK] {name} -> {out_path}")
            except Exception as e:
                print(f"[FAIL] {name}: {e}")

        browser.close()


if __name__ == "__main__":
    main()
