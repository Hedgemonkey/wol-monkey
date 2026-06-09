"""Live security audit script — run directly with the test DB."""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import create_app

DEMO_MAC = "aa:bb:cc:dd:ee:01"
DEMO_IP = "10.0.0.10"

passed: list[str] = []
failed: list[str] = []


def ok(msg: str) -> None:
    passed.append(msg)
    print(f"  + {msg}", flush=True)


def fail(msg: str) -> None:
    failed.append(msg)
    print(f"  FAIL {msg}", flush=True)


def check(cond: bool, msg: str) -> None:
    ok(msg) if cond else fail(msg)


def section(s: str) -> None:
    print(f"\n--- {s} ---", flush=True)


async def do_setup(c: AsyncClient) -> str:
    await c.post("/api/setup/admin", json={"username": "admin", "password": "SuperSecret123!"})
    await c.post(
        "/api/setup/network",
        json={
            "wake_interface": "enP4p65s0",
            "default_wake_strategy": "etherwake",
            "default_poll_timeout_s": 60,
        },
    )
    await c.post("/api/setup/complete")
    r = await c.post("/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"})
    return r.json()["csrf_token"]


async def main() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        csrf = await do_setup(c)
        r = await c.post(
            "/api/machines",
            json={"name": "Desktop PC", "ip_address": DEMO_IP, "mac_address": DEMO_MAC},
            headers={"X-CSRF-Token": csrf},
        )
        mid = r.json()["id"]

        # ================================================================
        section("1. UNAUTHENTICATED ACCESS — every protected endpoint")
        # ================================================================
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
            anon_checks = [
                ("GET", "/api/machines", None),
                ("GET", f"/api/machines/{mid}", None),
                (
                    "POST",
                    "/api/machines",
                    {"name": "x", "ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
                ),
                ("PATCH", f"/api/machines/{mid}", {"name": "x"}),
                ("DELETE", f"/api/machines/{mid}", None),
                ("GET", f"/api/machines/{mid}/status", None),
                ("POST", f"/api/machines/{mid}/wake", {"strategy": "etherwake"}),
                ("GET", "/api/auth/me", None),
                ("POST", "/api/auth/tokens", {"name": "x"}),
                ("GET", "/api/auth/tokens", None),
                ("POST", "/api/auth/logout", None),
            ]
            for method, path, body in anon_checks:
                fn = getattr(anon, method.lower())
                r = await (fn(path, json=body) if body else fn(path))
                check(r.status_code in (401, 403, 422), f"anon {method} {path} → {r.status_code}")

        # ================================================================
        section("2. CSRF BYPASS ATTEMPTS")
        # ================================================================
        mutating = [
            (
                "post",
                "/api/machines",
                {"name": "x", "ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
            ),
            ("patch", f"/api/machines/{mid}", {"name": "hacked"}),
            ("delete", f"/api/machines/{mid}", None),
            ("post", f"/api/machines/{mid}/wake", {"strategy": "etherwake"}),
            ("post", "/api/auth/tokens", {"name": "evil"}),
        ]
        for method, path, body in mutating:
            fn = getattr(c, method)
            r = await (fn(path, json=body) if body else fn(path))
            check(r.status_code == 403, f"no-CSRF {method.upper()} {path} → 403")
            r = await (
                fn(path, json=body, headers={"X-CSRF-Token": "forged"})
                if body
                else fn(path, headers={"X-CSRF-Token": "forged"})
            )
            check(r.status_code == 403, f"bad-CSRF {method.upper()} {path} → 403")

        # ================================================================
        section("3. INPUT VALIDATION — MAC / IP / name")
        # ================================================================
        bad_macs = [
            "not-a-mac",
            "00:00:00:00:00",
            "gg:hh:ii:jj:kk:ll",
            "AA:BB:CC:DD:EE:FF:00",
            "",
            "x" * 256,
        ]
        for mac in bad_macs:
            r = await c.post(
                "/api/machines",
                json={"name": "x", "ip_address": "1.1.1.1", "mac_address": mac},
                headers={"X-CSRF-Token": csrf},
            )
            check(r.status_code == 422, f"bad MAC {mac!r:.20} → 422")

        bad_ips = [
            "not-an-ip",
            "999.999.999.999",
            "",
            "x" * 256,
            "127.0.0.1; DROP TABLE machines;--",
        ]
        for ip in bad_ips:
            r = await c.post(
                "/api/machines",
                json={"name": "x", "ip_address": ip, "mac_address": "aa:bb:cc:dd:ee:ff"},
                headers={"X-CSRF-Token": csrf},
            )
            check(r.status_code == 422, f"bad IP {ip!r:.30} → 422")

        r = await c.post(
            "/api/machines",
            json={"name": "A" * 300, "ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
            headers={"X-CSRF-Token": csrf},
        )
        check(r.status_code == 422, "oversized name (300 chars) → 422")

        # ORM parameterisation should store SQL injection strings safely
        sqli = "' OR '1'='1'; DROP TABLE machines;--"
        r = await c.post(
            "/api/machines",
            json={"name": sqli, "ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
            headers={"X-CSRF-Token": csrf},
        )
        check(r.status_code == 201, "SQLi string in name stored safely → 201")
        sqli_id = r.json()["id"]
        check(len((await c.get("/api/machines")).json()) >= 2, "machine list intact after SQLi")
        await c.delete(f"/api/machines/{sqli_id}", headers={"X-CSRF-Token": csrf})

        # JSON API — XSS strings are stored/returned as-is, never rendered server-side
        xss = "<script>alert(1)</script>"
        r = await c.post(
            "/api/machines",
            json={"name": xss, "ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
            headers={"X-CSRF-Token": csrf},
        )
        xss_id = r.json()["id"]
        check(
            (await c.get(f"/api/machines/{xss_id}")).json()["name"] == xss,
            "XSS string round-trips unchanged in JSON",
        )
        await c.delete(f"/api/machines/{xss_id}", headers={"X-CSRF-Token": csrf})

        # ================================================================
        section("4. SESSION REVOCATION")
        # ================================================================
        await c.post("/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"})
        saved_cookie = c.cookies.get("wm_session")
        await c.post("/api/auth/logout")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stale:
            stale.cookies.set("wm_session", saved_cookie or "bad")
            check(
                (await stale.get("/api/auth/me")).status_code == 401,
                "revoked session cookie rejected → 401",
            )

        # ================================================================
        section("5. NONEXISTENT / MALFORMED IDs")
        # ================================================================
        r = await c.post(
            "/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"}
        )
        csrf2 = r.json()["csrf_token"]

        for fid in ["00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff"]:
            check(
                (await c.get(f"/api/machines/{fid}")).status_code == 404,
                "GET nonexistent UUID → 404",
            )
            check(
                (
                    await c.delete(f"/api/machines/{fid}", headers={"X-CSRF-Token": csrf2})
                ).status_code
                == 404,
                "DELETE nonexistent UUID → 404",
            )
            check(
                (
                    await c.patch(
                        f"/api/machines/{fid}", json={"name": "x"}, headers={"X-CSRF-Token": csrf2}
                    )
                ).status_code
                == 404,
                "PATCH nonexistent UUID → 404",
            )

        for bad_id in ["../etc/passwd", "not-a-uuid", "<script>", "1 OR 1=1", ";" * 50]:
            check(
                (await c.get(f"/api/machines/{bad_id}")).status_code == 404,
                f"malformed id {bad_id!r:.20} → 404 (no crash)",
            )

        # ================================================================
        section("6. WAKE STRATEGY ENUM VALIDATION")
        # ================================================================
        for bad in ["../../etc/passwd", "; rm -rf /", "x" * 300, "__import__", "null", "undefined"]:
            r = await c.post(
                f"/api/machines/{mid}/wake", json={"strategy": bad}, headers={"X-CSRF-Token": csrf2}
            )
            check(r.status_code == 422, f"bad strategy {bad!r:.20} → 422")

        for good in ["etherwake", "udp_broadcast"]:
            r = await c.post(
                f"/api/machines/{mid}/wake",
                json={"strategy": good},
                headers={"X-CSRF-Token": csrf2},
            )
            check(r.status_code in (200, 202), f"valid strategy {good!r} → {r.status_code}")

        # ================================================================
        section("7. CONTENT-TYPE CONFUSION")
        # ================================================================
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cx:
            cx.cookies.update(c.cookies)
            r = await cx.post(
                "/api/auth/login",
                content=b"username=admin&password=SuperSecret123!",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            check(r.status_code == 422, "form-data to JSON endpoint → 422")
            r = await cx.post(
                "/api/auth/login",
                content=b"\xff\xfe garbage \x00\x01",
                headers={"Content-Type": "application/json"},
            )
            check(r.status_code in (400, 422), f"binary garbage body → {r.status_code} (rejected)")
            r = await cx.post(
                "/api/auth/login", content=b"", headers={"Content-Type": "application/json"}
            )
            check(r.status_code == 422, "empty body → 422")

        # ================================================================
        section("8. API TOKEN ISOLATION")
        # ================================================================
        r = await c.post(
            "/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"}
        )
        csrf3 = r.json()["csrf_token"]
        r = await c.post(
            "/api/auth/tokens", json={"name": "tok-a"}, headers={"X-CSRF-Token": csrf3}
        )
        tok_a, tok_a_id = r.json()["raw_token"], r.json()["id"]
        r = await c.post(
            "/api/auth/tokens", json={"name": "tok-b"}, headers={"X-CSRF-Token": csrf3}
        )
        tok_b, tok_b_id = r.json()["raw_token"], r.json()["id"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ct:
            check(
                (
                    await ct.get("/api/machines", headers={"Authorization": f"Bearer {tok_a}"})
                ).status_code
                == 200,
                "token-A reads machines",
            )
            # Token-only client has no session cookie → CSRF dep needs session → 401
            r = await ct.delete(
                f"/api/machines/{mid}",
                headers={"Authorization": f"Bearer {tok_a}", "X-CSRF-Token": "anything"},
            )
            check(
                r.status_code in (401, 403),
                f"token-only DELETE bypasses session+CSRF? → {r.status_code} (blocked)",
            )

        await c.delete(f"/api/auth/tokens/{tok_a_id}", headers={"X-CSRF-Token": csrf3})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ct:
            check(
                (
                    await ct.get("/api/machines", headers={"Authorization": f"Bearer {tok_a}"})
                ).status_code
                == 401,
                "revoked tok-A → 401",
            )
            check(
                (
                    await ct.get("/api/machines", headers={"Authorization": f"Bearer {tok_b}"})
                ).status_code
                == 200,
                "tok-B unaffected by A revocation",
            )
        await c.delete(f"/api/auth/tokens/{tok_b_id}", headers={"X-CSRF-Token": csrf3})

        # ================================================================
        section("9. CSRF STATELESS HMAC REUSE")
        # ================================================================
        r = await c.post(
            "/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"}
        )
        csrf4 = r.json()["csrf_token"]
        for i in range(3):
            r = await c.post(
                "/api/machines",
                json={
                    "name": f"Tmp-{i}",
                    "ip_address": "10.0.0.1",
                    "mac_address": "11:22:33:44:55:66",
                },
                headers={"X-CSRF-Token": csrf4},
            )
            check(r.status_code == 201, f"CSRF reusable same session (req {i + 1}/3)")
            await c.delete(f"/api/machines/{r.json()['id']}", headers={"X-CSRF-Token": csrf4})

        # ================================================================
        section("10. LIVE PROBE — Desktop PC")
        # ================================================================
        r = await c.get(f"/api/machines/{mid}/status")
        p = r.json()
        check(r.status_code == 200, "probe → 200")
        check(p["tcp_ssh_ok"] is True, f"TCP-SSH open (state={p['state']})")
        check(p["state"] == "online", "machine state=online")

        # ================================================================
        section("11. WAKE PACKET DISPATCH — monitor without sleeping host")
        # ================================================================
        r = await c.post(
            "/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"}
        )
        csrf5 = r.json()["csrf_token"]

        # Trigger etherwake — machine is online so wake is a no-op, but packet should still be sent
        r = await c.post(
            f"/api/machines/{mid}/wake",
            json={"strategy": "etherwake", "ensure_online": False},
            headers={"X-CSRF-Token": csrf5},
        )
        check(r.status_code in (200, 202), f"wake dispatch → {r.status_code}")
        attempt_id = r.json().get("attempt_id") or r.json().get("id")
        check(attempt_id is not None, "attempt_id returned")

        # Poll attempt status
        if attempt_id:
            r2 = await c.get(f"/api/machines/{mid}/attempts/{attempt_id}")
            check(r2.status_code == 200, "attempt status → 200")
            check(
                r2.json()["status"] in ("pending", "sent", "done", "waking"),
                f"attempt status is valid: {r2.json()['status']}",
            )

        # UDP broadcast (no raw socket needed)
        r = await c.post(
            f"/api/machines/{mid}/wake",
            json={"strategy": "udp_broadcast", "ensure_online": False},
            headers={"X-CSRF-Token": csrf5},
        )
        check(r.status_code in (200, 202), f"udp_broadcast wake → {r.status_code}")

        print()
        print(f"PASSED: {len(passed)}  FAILED: {len(failed)}")
        if failed:
            print("FAILURES:")
            for f2 in failed:
                print(f"  - {f2}")
        else:
            print("ALL SECURITY + FUNCTIONAL CHECKS PASSED")


asyncio.run(main())
