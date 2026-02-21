"""
PharmaVigil AI — Comprehensive Scenario Tests
===============================================

Tests ALL major scenarios of the application:
  1. API Health & Connectivity
  2. Master Orchestrator Routing (6 routes)
  3. RAG Knowledge Base (drug labels, methodology, regulatory)
  4. Out-of-Scope Query Handling
  5. Full Investigation Pipeline
  6. Data Query Pipeline
  7. Report Generation Pipeline
  8. WebSocket Real-time Progress

Usage:
    # Run all tests:
    python tests/test_scenarios.py

    # Run a specific test category:
    python tests/test_scenarios.py --category routing
    python tests/test_scenarios.py --category rag
    python tests/test_scenarios.py --category all

Requirements:
    pip install httpx websockets
"""

import asyncio
import json
import time
import argparse
import sys
from datetime import datetime

import httpx

API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

# ── Test Utilities ──────────────────────────────────────────

class TestResult:
    def __init__(self, name: str, passed: bool, details: str = "", duration: float = 0):
        self.name = name
        self.passed = passed
        self.details = details
        self.duration = duration

    def __str__(self):
        icon = "✅" if self.passed else "❌"
        time_str = f" ({self.duration:.1f}s)" if self.duration > 0 else ""
        detail_str = f"\n      {self.details}" if self.details else ""
        return f"  {icon} {self.name}{time_str}{detail_str}"


results: list[TestResult] = []


def log_test(name: str, passed: bool, details: str = "", duration: float = 0):
    result = TestResult(name, passed, details, duration)
    results.append(result)
    print(result)


def investigate_and_wait(client: httpx.Client, query: str, timeout: int = 120) -> dict:
    """Submit a query and poll until complete."""
    start = time.time()

    # Start investigation
    resp = client.post(f"{API_BASE}/api/investigate", json={"query": query})
    if resp.status_code != 200:
        return {"error": f"Failed to start: {resp.status_code}", "duration": time.time() - start}

    data = resp.json()
    inv_id = data["investigation_id"]

    # Poll for completion
    while time.time() - start < timeout:
        time.sleep(2)
        resp = client.get(f"{API_BASE}/api/investigations/{inv_id}")
        if resp.status_code != 200:
            continue
        inv = resp.json()
        if inv.get("status") in ("complete", "error"):
            inv["duration"] = time.time() - start
            return inv

    return {"error": "Timeout", "duration": time.time() - start}


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 1: API Health & Connectivity
# ═══════════════════════════════════════════════════════════

def test_api_health(client: httpx.Client):
    print("\n🏥 === API Health & Connectivity ===\n")

    # Test 1.1: Health endpoint
    try:
        resp = client.get(f"{API_BASE}/api/health")
        data = resp.json()
        log_test(
            "Health endpoint returns 200",
            resp.status_code == 200,
            f"Status: {data.get('status')}, Agents: {data.get('agents_registered')}, Tools: {data.get('tools_registered')}"
        )
    except Exception as e:
        log_test("Health endpoint returns 200", False, str(e))

    # Test 1.2: Root endpoint
    try:
        resp = client.get(f"{API_BASE}/")
        data = resp.json()
        log_test(
            "Root endpoint returns welcome message",
            resp.status_code == 200 and "PharmaVigil" in data.get("name", ""),
            f"Message: {data.get('name', '')[:60]}"
        )
    except Exception as e:
        log_test("Root endpoint returns welcome message", False, str(e))

    # Test 1.3: Investigations list
    try:
        resp = client.get(f"{API_BASE}/api/investigations")
        log_test(
            "Investigations list endpoint works",
            resp.status_code == 200,
            f"Current investigations: {len(resp.json()) if resp.status_code == 200 else 'N/A'}"
        )
    except Exception as e:
        log_test("Investigations list endpoint works", False, str(e))

    # Test 1.4: Invalid investigation ID returns 404
    try:
        resp = client.get(f"{API_BASE}/api/investigations/INVALID-ID-12345")
        log_test(
            "Invalid investigation ID returns 404",
            resp.status_code == 404,
            f"Status: {resp.status_code}"
        )
    except Exception as e:
        log_test("Invalid investigation ID returns 404", False, str(e))


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 2: Master Orchestrator Routing
# ═══════════════════════════════════════════════════════════

def test_routing(client: httpx.Client):
    print("\n🧠 === Master Orchestrator Routing ===\n")

    routing_tests = [
        # (query, expected_route, description)
        ("Scan for any emerging drug safety signals in the last 90 days", "full_scan", "Full scan query"),
        ("Investigate Cardizol-X for cardiac safety signals", "investigate", "Investigation query"),
        ("Generate safety report for Arthrex-200", "report", "Report generation query"),
        ("How many adverse events for Neurofen-Plus?", "data_query", "Data query"),
        ("What is PRR in pharmacovigilance?", "general", "General knowledge (no drug)"),
        ("What are the contraindications of Cardizol-X?", "general", "Drug label knowledge (with drug)"),
        ("What is the weather today?", "out_of_scope", "Out-of-scope query"),
    ]

    for query, expected_route, desc in routing_tests:
        start = time.time()
        try:
            resp = client.post(f"{API_BASE}/api/investigate", json={"query": query})
            data = resp.json()
            inv_id = data["investigation_id"]

            # Wait for routing to complete
            actual_route = "unknown"
            for _ in range(15):
                time.sleep(2)
                inv = client.get(f"{API_BASE}/api/investigations/{inv_id}").json()
                if inv.get("status") != "routing" and inv.get("route"):
                    actual_route = inv.get("route")
                    break

            duration = time.time() - start

            log_test(
                f"[{desc}] → route={expected_route}",
                actual_route == expected_route,
                f"Query: \"{query[:50]}...\" → Got: {actual_route}",
                duration
            )
        except Exception as e:
            log_test(f"[{desc}] → route={expected_route}", False, str(e))
        
        # Small delay between tests to avoid rate limiting
        time.sleep(1)


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 3: RAG Knowledge Base
# ═══════════════════════════════════════════════════════════

def test_rag(client: httpx.Client):
    print("\n📚 === RAG Knowledge Base ===\n")

    rag_tests = [
        # (query, expected_keywords_in_response, description)
        (
            "What are the contraindications of Cardizol-X?",
            ["aortic stenosis", "heart failure", "hypersensitivity"],
            "Drug label: Cardizol-X contraindications"
        ),
        (
            "What is the maximum dose of Cardizol-X?",
            ["200mg", "dose"],
            "Drug label: Cardizol-X dosage"
        ),
        (
            "What are the warnings for Neurofen-Plus in elderly patients?",
            ["elderly", "hepatotoxicity", "65"],
            "Drug label: Neurofen-Plus elderly warnings"
        ),
        (
            "What drug interactions does Arthrex-200 have with statins?",
            ["rhabdomyolysis", "CYP2C9", "statin"],
            "Drug label: Arthrex-200 statin interaction"
        ),
        (
            "Explain what Proportional Reporting Ratio (PRR) is and how it is calculated.",
            ["PRR", "formula", "proportion"],
            "Methodology: PRR calculation"
        ),
        (
            "What is EBGM and what threshold indicates a safety signal?",
            ["EBGM", "2.0", "Bayes"],
            "Methodology: EBGM threshold"
        ),
        (
            "What are the ICH E2E guidelines about?",
            ["ICH", "pharmacovigilance", "planning"],
            "Regulatory: ICH E2E guidelines"
        ),
        (
            "What are the reporting timelines for serious adverse events?",
            ["7", "15", "days"],
            "Regulatory: ICSR reporting timelines"
        ),
    ]

    for query, expected_keywords, desc in rag_tests:
        start = time.time()
        try:
            inv = investigate_and_wait(client, query, timeout=90)
            duration = inv.get("duration", time.time() - start)

            if "error" in inv:
                log_test(f"[{desc}]", False, f"Error: {inv['error']}", duration)
                continue

            response = inv.get("direct_response", "")
            response_lower = response.lower()

            # Check how many expected keywords are present
            found = [kw for kw in expected_keywords if kw.lower() in response_lower]
            missing = [kw for kw in expected_keywords if kw.lower() not in response_lower]

            passed = len(found) >= len(expected_keywords) * 0.6  # At least 60% keywords found

            log_test(
                f"[{desc}]",
                passed,
                f"Keywords found: {found} | Missing: {missing} | Response length: {len(response)} chars",
                duration
            )

        except Exception as e:
            log_test(f"[{desc}]", False, str(e))

        time.sleep(1)


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 4: Out-of-Scope Handling
# ═══════════════════════════════════════════════════════════

def test_out_of_scope(client: httpx.Client):
    print("\n🔒 === Out-of-Scope Query Handling ===\n")

    oos_queries = [
        ("What is the weather today?", "Weather question"),
        ("Tell me a joke", "Entertainment question"),
        ("Who won the cricket world cup?", "Sports question"),
        ("Write me a poem about trees", "Creative writing"),
    ]

    for query, desc in oos_queries:
        start = time.time()
        try:
            inv = investigate_and_wait(client, query, timeout=60)
            duration = inv.get("duration", time.time() - start)

            if "error" in inv:
                log_test(f"[{desc}] → Out of scope", False, f"Error: {inv['error']}", duration)
                continue

            response = inv.get("direct_response", "")
            route = inv.get("route", "")

            is_oos = (
                route == "out_of_scope" or
                "out of scope" in response.lower() or
                "outside" in response.lower() or
                "PharmaVigil" in response
            )

            log_test(
                f"[{desc}] → Redirected correctly",
                is_oos,
                f"Route: {route} | Has redirect msg: {'PharmaVigil' in response}",
                duration
            )

        except Exception as e:
            log_test(f"[{desc}] → Out of scope", False, str(e))

        time.sleep(1)


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 5: Full Investigation Pipeline
# ═══════════════════════════════════════════════════════════

def test_full_investigation(client: httpx.Client):
    print("\n🔬 === Full Investigation Pipeline ===\n")

    # Test 5.1: Full scan
    start = time.time()
    try:
        inv = investigate_and_wait(client, "Scan for any emerging drug safety signals", timeout=300)
        duration = inv.get("duration", time.time() - start)

        if "error" in inv:
            log_test("Full scan completes", False, f"Error: {inv['error']}", duration)
        else:
            signals = inv.get("signals", [])
            reports = inv.get("reports", [])
            reasoning = inv.get("reasoning_trace", [])

            log_test(
                "Full scan completes",
                inv.get("status") == "complete",
                f"Signals: {len(signals)}, Reports: {len(reports)}, Reasoning steps: {len(reasoning)}",
                duration
            )

            # Check signals have required fields
            if signals:
                sig = signals[0]
                has_fields = all(k in sig for k in ["drug_name", "reaction_term", "prr", "case_count", "priority"])
                log_test(
                    "Signals have required fields",
                    has_fields,
                    f"Signal example: {sig.get('drug_name')} → {sig.get('reaction_term')} (PRR: {sig.get('prr')})"
                )

            # Check reports have markdown content
            if reports:
                rpt = reports[0]
                has_markdown = bool(rpt.get("report_markdown")) and len(rpt.get("report_markdown", "")) > 100
                log_test(
                    "Reports contain markdown",
                    has_markdown,
                    f"Report for: {rpt.get('drug_name')} | Size: {len(rpt.get('report_markdown', ''))} chars"
                )

    except Exception as e:
        log_test("Full scan completes", False, str(e))

    # Test 5.2: Drug-specific investigation
    start = time.time()
    try:
        inv = investigate_and_wait(client, "Investigate Cardizol-X for cardiac safety signals", timeout=180)
        duration = inv.get("duration", time.time() - start)

        if "error" in inv:
            log_test("Drug investigation completes (Cardizol-X)", False, f"Error: {inv['error']}", duration)
        else:
            reasoning = inv.get("reasoning_trace", [])
            tool_calls = [s for s in reasoning if s.get("tool_name")]

            log_test(
                "Drug investigation completes (Cardizol-X)",
                inv.get("status") == "complete",
                f"Reasoning steps: {len(reasoning)}, Tool calls: {len(tool_calls)}",
                duration
            )

            # Verify tools were used
            tool_names = {s.get("tool_name") for s in reasoning if s.get("tool_name")}
            log_test(
                "Investigation used relevant tools",
                len(tool_names) >= 2,
                f"Tools used: {tool_names}"
            )

    except Exception as e:
        log_test("Drug investigation completes (Cardizol-X)", False, str(e))


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 6: Data Query Pipeline
# ═══════════════════════════════════════════════════════════

def test_data_query(client: httpx.Client):
    print("\n📊 === Data Query Pipeline ===\n")

    data_queries = [
        ("How many adverse events for Neurofen-Plus?", "count", "Event count query"),
        ("Show top drugs by adverse event count", "top", "Top drugs query"),
    ]

    for query, expected_keyword, desc in data_queries:
        start = time.time()
        try:
            inv = investigate_and_wait(client, query, timeout=90)
            duration = inv.get("duration", time.time() - start)

            if "error" in inv:
                log_test(f"[{desc}]", False, f"Error: {inv['error']}", duration)
                continue

            response = inv.get("direct_response", "")
            has_data = bool(response) and len(response) > 20

            log_test(
                f"[{desc}] → Returns data",
                has_data,
                f"Response length: {len(response)} chars | Route: {inv.get('route')}",
                duration
            )

        except Exception as e:
            log_test(f"[{desc}]", False, str(e))

        time.sleep(1)


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 7: Report Generation
# ═══════════════════════════════════════════════════════════

def test_report_generation(client: httpx.Client):
    print("\n📝 === Report Generation Pipeline ===\n")

    start = time.time()
    try:
        inv = investigate_and_wait(client, "Generate safety report for Arthrex-200", timeout=180)
        duration = inv.get("duration", time.time() - start)

        if "error" in inv:
            log_test("Report generation completes", False, f"Error: {inv['error']}", duration)
        else:
            reports = inv.get("reports", [])

            log_test(
                "Report generation completes",
                inv.get("status") == "complete",
                f"Reports generated: {len(reports)}",
                duration
            )

            if reports:
                rpt = reports[0]
                markdown = rpt.get("report_markdown", "")

                # Check report has key sections
                sections = ["Executive Summary", "Signal", "Demographics", "Risk"]
                found_sections = [s for s in sections if s.lower() in markdown.lower()]

                log_test(
                    "Report contains key regulatory sections",
                    len(found_sections) >= 2,
                    f"Sections found: {found_sections} out of {sections}"
                )

                log_test(
                    "Report has substantial content",
                    len(markdown) > 500,
                    f"Report size: {len(markdown)} characters"
                )

    except Exception as e:
        log_test("Report generation completes", False, str(e))


# ═══════════════════════════════════════════════════════════
# TEST CATEGORY 8: WebSocket Connectivity
# ═══════════════════════════════════════════════════════════

def test_websocket(client: httpx.Client):
    print("\n🔌 === WebSocket Real-time Progress ===\n")

    try:
        import websockets

        async def ws_test():
            # Start an investigation
            resp = client.post(
                f"{API_BASE}/api/investigate",
                json={"query": "What is PRR?"}
            )
            data = resp.json()
            inv_id = data["investigation_id"]

            messages = []
            start = time.time()

            try:
                async with websockets.connect(
                    f"{WS_BASE}/ws/progress/{inv_id}",
                    close_timeout=5
                ) as ws:
                    while time.time() - start < 60:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            parsed = json.loads(msg)
                            messages.append(parsed)

                            if parsed.get("data", {}).get("status") in ("complete", "error"):
                                break
                        except asyncio.TimeoutError:
                            break

            except Exception as e:
                log_test("WebSocket connects successfully", False, str(e))
                return

            duration = time.time() - start

            # Check we received messages
            log_test(
                "WebSocket receives progress messages",
                len(messages) > 0,
                f"Received {len(messages)} messages in {duration:.1f}s",
                duration
            )

            # Check message types
            msg_types = {m.get("type") for m in messages}
            log_test(
                "WebSocket sends current_state and progress messages",
                "current_state" in msg_types or "progress" in msg_types,
                f"Message types: {msg_types}"
            )

        asyncio.run(ws_test())

    except ImportError:
        log_test(
            "WebSocket test (skipped — install websockets)",
            True,
            "pip install websockets to enable WebSocket tests"
        )
    except Exception as e:
        log_test("WebSocket test", False, str(e))


# ═══════════════════════════════════════════════════════════
# TEST RUNNER
# ═══════════════════════════════════════════════════════════

CATEGORIES = {
    "health": ("API Health", test_api_health),
    "routing": ("Routing", test_routing),
    "rag": ("RAG Knowledge Base", test_rag),
    "oos": ("Out-of-Scope", test_out_of_scope),
    "investigation": ("Full Investigation", test_full_investigation),
    "data": ("Data Queries", test_data_query),
    "report": ("Report Generation", test_report_generation),
    "websocket": ("WebSocket", test_websocket),
}


def main():
    parser = argparse.ArgumentParser(description="PharmaVigil AI — Scenario Tests")
    parser.add_argument(
        "--category", "-c",
        default="all",
        choices=list(CATEGORIES.keys()) + ["all", "quick"],
        help="Test category to run (default: all)"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Backend API URL"
    )
    args = parser.parse_args()

    global API_BASE, WS_BASE
    API_BASE = args.api_url.rstrip("/")
    WS_BASE = API_BASE.replace("http://", "ws://").replace("https://", "wss://")

    print("=" * 64)
    print("  🧪 PharmaVigil AI — Comprehensive Scenario Tests")
    print(f"  📡 Target: {API_BASE}")
    print(f"  🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    # Check connectivity first
    client = httpx.Client(timeout=30.0)
    try:
        resp = client.get(f"{API_BASE}/api/health")
        if resp.status_code != 200:
            print(f"\n❌ Cannot reach API at {API_BASE}. Is the backend running?")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cannot reach API at {API_BASE}: {e}")
        print("   Start the backend first: uvicorn app.api:app --reload --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # Determine which tests to run
    if args.category == "all":
        test_funcs = list(CATEGORIES.values())
    elif args.category == "quick":
        # Quick tests: health, routing, one RAG, one OOS
        test_funcs = [
            CATEGORIES["health"],
            CATEGORIES["rag"],
            CATEGORIES["oos"],
        ]
    else:
        test_funcs = [CATEGORIES[args.category]]

    # Run selected tests
    total_start = time.time()
    for name, func in test_funcs:
        try:
            func(client)
        except Exception as e:
            print(f"\n💥 Test category '{name}' crashed: {e}")

    # Print summary
    total_duration = time.time() - total_start
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print("\n" + "=" * 64)
    print(f"  📊 RESULTS SUMMARY")
    print(f"  ✅ Passed: {passed}/{total}")
    print(f"  ❌ Failed: {failed}/{total}")
    print(f"  ⏱️  Total time: {total_duration:.1f}s")
    print("=" * 64)

    if failed > 0:
        print("\n  Failed tests:")
        for r in results:
            if not r.passed:
                print(f"    ❌ {r.name}: {r.details}")

    print()
    client.close()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
