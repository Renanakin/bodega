"""Test E2E para BUG 11 (layout del bloque cubiertos) + BUG 12 (cobertura).

BUG 11 (2026-07-23): el link de la solicitud en el bloque 'cubiertos por
pendientes' se salia del flex y quedaba abajo a la izquierda. Causa: la
estructura del <li> no tenia `shrink-0` en el <a> y la palabra completa
del nombre del producto forzaba wrap en lineas estrechas.

BUG 12 (2026-07-23): el endpoint /bajo-minimo/cubiertos-por-pendientes
solo consideraba solicitudes en estado PENDING. Esto causaba que al
aprobar la solicitud (PENDING -> APPROVED), el stock SIGUIERA bajo
minimo pero el SKU desaparecia de la UI sin explicacion. La cobertura
correcta incluye todos los estados donde el stock NO ha llegado al
destino: pending, approved, in_transit, partially_received. Solo
received/rejected/cancelled dejan de cubrir.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = "http://localhost:8080"
OUT = Path(r"C:\Users\Tranquilidad\auditoria-fase5\replenishment_bug12")
OUT.mkdir(parents=True, exist_ok=True)


def login(page) -> None:
    page.goto(f"{URL}/login", wait_until="networkidle")
    page.locator("input").nth(0).fill("admin")
    page.locator('input[type="password"]').fill("admin12345")
    page.locator('button[type="submit"]').click()
    page.wait_for_url(f"{URL}/dashboard", timeout=10000)


def goto_replenishment(page) -> None:
    page.goto(f"{URL}/replenishment", wait_until="networkidle")
    time.sleep(1.5)


def main() -> int:
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        print("=== SETUP: login ===")
        login(page)
        print("[OK] login")

        print("\n=== Test BUG 12: cobertura incluye approved ===")
        goto_replenishment(page)

        # El sistema debe mostrar el bloque 'cubiertos por solicitudes
        # ACTIVAS' (no PENDIENTES), incluyendo solicitudes en approved.
        bloque = page.locator("text=SKUs bajo minimo cubiertos por solicitudes activas")
        expect(bloque).to_be_visible(timeout=10000)
        print("[OK] bloque 'cubiertos por solicitudes ACTIVAS' visible")

        # Verificar que el footer dice 'linea activa' (no 'PENDING')
        footer = page.locator("text=linea activa")
        if footer.count() == 0:
            failures.append("footer no dice 'linea activa' (sigue diciendo PENDING)")
        else:
            print("[OK] footer actualizado: 'linea activa'")

        # La descripcion debe mencionar estados multiples
        descripcion = page.locator(
            "text=solicitudes activas (pendiente, aprobada, en transito o recepcion parcial)"
        )
        if descripcion.count() == 0:
            failures.append("descripcion no menciona estados multiples")
        else:
            print("[OK] descripcion menciona estados multiples")

        page.screenshot(path=str(OUT / "01_bloque_activas.png"), full_page=True)

        print("\n=== Test BUG 11: layout del bloque cubiertos ===")
        # Cada item debe tener <a> en la misma linea que la info
        items = page.locator("li").filter(has_text="solicita")
        count = items.count()
        print(f"[INFO] items encontrados: {count}")

        if count == 0:
            failures.append("no hay items cubiertos, no se puede testear layout")
        else:
            all_ok = True
            for i in range(count):
                item = items.nth(i)
                link = item.locator("a").first
                if link.count() == 0:
                    failures.append(f"item {i} sin <a>")
                    continue
                info = item.locator("div").first
                box_info = info.bounding_box()
                box_link = link.bounding_box()
                # El link debe estar verticalmente dentro del rango del info
                # (con tolerancia de 5px para baseline alignment).
                if not (
                    box_link["y"] >= box_info["y"] - 5
                    and box_link["y"] <= box_info["y"] + box_info["height"] + 5
                ):
                    failures.append(
                        f"item {i}: link y={box_link['y']:.0f} fuera de "
                        f"info y={box_info['y']:.0f}-{box_info['y']+box_info['height']:.0f}"
                    )
                    all_ok = False
                else:
                    print(
                        f"  [item {i}] link y={box_link['y']:.0f} "
                        f"info y={box_info['y']:.0f}-{box_info['y']+box_info['height']:.0f} OK"
                    )
            if all_ok:
                print("[OK] todos los items tienen link en la misma linea que info")

        print("\n=== Test BUG 12: estado visible en cada item ===")
        # Cada item debe mostrar el estado de la solicitud
        for i in range(min(count, 4)):
            item_text = items.nth(i).inner_text()
            # Debe contener uno de: pendiente de aprobacion, aprobada esperando
            # despacho, en transito, recepcion parcial
            estados = [
                "pendiente de aprobacion",
                "aprobada, esperando despacho",
                "en transito",
                "recepcion parcial",
            ]
            if not any(e in item_text for e in estados):
                failures.append(f"item {i} no muestra estado de la solicitud")
            else:
                print(f"  [item {i}] estado visible: {[e for e in estados if e in item_text][0]}")

        page.screenshot(path=str(OUT / "02_detalle_items.png"), full_page=True)

        browser.close()

    print("\n=== RESUMEN ===")
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("[OK] todos los tests pasaron")
    return 0


if __name__ == "__main__":
    sys.exit(main())
