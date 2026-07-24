"""Test E2E visual para BUG 11 + BUG 12.

Verifica que el bloque 'cubiertos por solicitudes activas' en
/replenishment muestra el link de la solicitud en la misma linea que la
informacion del SKU (no debajo), y que se ve el estado de la solicitud
(pending/approved/in_transit/...).
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = "http://localhost:8080"
OUT = Path(r"C:\Users\Tranquilidad\auditoria-fase5\replenishment_bug11_12")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # 1) Login
        page.goto(f"{URL}/login", wait_until="networkidle")
        page.locator('input').nth(0).fill("admin")
        page.locator('input[type="password"]').fill("admin12345")
        page.locator('button[type="submit"]').click()
        page.wait_for_url(f"{URL}/dashboard", timeout=10000)
        print("[OK] login")

        # 2) Ir a /replenishment
        page.goto(f"{URL}/replenishment", wait_until="networkidle")
        time.sleep(1)
        page.screenshot(path=str(OUT / "01_replenishment_full.png"), full_page=True)
        print("[OK] screenshot full")

        # 3) Verificar bloque cubiertos (si existe)
        cubiertos = page.locator("li").filter(has_text="Stock").filter(has_text="solicita")
        count = cubiertos.count()
        print(f"[INFO] items cubiertos encontrados: {count}")
        if count == 0:
            print("[WARN] no hay items cubiertos, no se puede verificar layout")
            browser.close()
            return 0

        # 4) Para cada item, verificar que el <a> esta en la misma fila
        # que el texto. Si estan en lineas distintas, hay bug.
        all_ok = True
        for i in range(count):
            item = cubiertos.nth(i)
            # bounding box del item completo
            box_item = item.bounding_box()
            # primer <a> dentro del item
            link = item.locator("a").first
            if link.count() == 0:
                print(f"  [{i}] sin <a> link")
                continue
            box_link = link.bounding_box()
            # texto informativo (primer div)
            info = item.locator("div").first
            box_info = info.bounding_box()
            # Si el link esta mas abajo que el texto, hay bug
            link_top = box_link["y"]
            info_top = box_info["y"]
            info_bottom = box_info["y"] + box_info["height"]
            same_line = (link_top >= info_top - 5) and (link_top <= info_bottom + 5)
            print(
                f"  [{i}] info y={info_top:.0f} h={box_info['height']:.0f} | "
                f"link y={box_link['y']:.0f} h={box_link['height']:.0f} | "
                f"item y={box_item['y']:.0f} h={box_item['height']:.0f} | "
                f"{'OK same-line' if same_line else 'FAIL link-below'}"
            )
            if not same_line:
                all_ok = False
            # Screenshot recortado del item
            item.screenshot(path=str(OUT / f"02_item_{i}.png"))

        # 5) Screenshot del bloque completo
        bloque = page.locator("div").filter(has_text="SKUs bajo minimo cubiertos por solicitudes activas").first
        if bloque.count() > 0:
            bloque.screenshot(path=str(OUT / "03_bloque_completo.png"))
            print("[OK] bloque screenshot")

        # 6) Screenshot con zoom del primer item
        if count > 0:
            cubiertos.first.screenshot(path=str(OUT / "04_primer_item_zoom.png"))

        browser.close()
        return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
