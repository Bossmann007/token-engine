"""RTK-inspired bash/tool output filters (docker, cargo, npm, jest, pnpm, vite, webpack, gradle, journalctl, terraform)."""

from __future__ import annotations

import re

from token_engine.compressor.base import CompressResult

# --- detection patterns ---

DETECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("docker", re.compile(r"(^Step \d+/|Successfully (built|tagged)|Sending build context| ---> (Running|Using|Pulling))", re.M)),
    ("cargo", re.compile(r"(^   Compiling |^    Finished |error\[E\d+\]|^warning:)", re.M)),
    ("kubectl", re.compile(r"(^NAME\s+READY|^NAMESPACE\s+|^kubectl |^\S+\s+\d+/\d+\s+Running)", re.M)),
    ("pip", re.compile(r"(^(Collecting|Installing|Successfully installed|Requirement already satisfied) )", re.M)),
    ("yarn", re.compile(r"^(?:yarn (?:install|add|run)|warning |error )", re.M)),
    ("jest", re.compile(r"(Test Suites:|^Tests:\s+\d+|^FAIL \S+\.|^\s*● )", re.M)),
    ("go", re.compile(r"(^=== RUN |^--- FAIL:|^PASS$|^ok\s+\S+\s+[\d.]+s|^FAIL\s+\S+\s+\[)", re.M)),
    ("make", re.compile(r"(^make(\[\d+\])?: (Entering|Leaving) directory|^make(\[\d+\])?: \*\*\* )", re.M)),
    ("curl", re.compile(r"(^[*<>] (Connected|HTTP|GET |POST )|^HTTP/\d\.\d \d{3})", re.M)),
    ("dotnet", re.compile(r"(^Build (FAILED|succeeded)|^    \d+ Error\(s\)|^MSBUILD : error)", re.M)),
    ("webpack", re.compile(r"(webpack compiled|ERROR in |Module not found|asset \S+ \d+ (?:KiB|MiB|bytes)|WARNING in )", re.M)),
    ("gradle", re.compile(r"(^> Task |BUILD SUCCESSFUL|BUILD FAILED|^FAILURE: Build failed)", re.M)),
    ("journalctl", re.compile(r"(^-- Logs begin|^-- Boot \d+|^[A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \S+ \S+\[\d+\]:)", re.M)),
    ("terraform", re.compile(r"(^Terraform |^Plan: \d+ to |^No changes\.|^\s*[~+-]\s+\S+.*= |^  # module\.)", re.M)),
    ("pnpm", re.compile(r"(^Progress: resolved|^Packages: \+|^Done in [\d.]+s|^WARN\s+.*deprecated)", re.M)),
    ("vite", re.compile(r"(^vite v\d|built in [\d.]+s|dist/.*\.(js|css)|error during build)", re.M)),
    ("npm", re.compile(r"(^npm warn |^npm error |added \d+ packages|audited \d+ packages|up to date)", re.M | re.I)),
    ("tsc", re.compile(r"(error TS\d+|Found \d+ error|\.tsx?\(\d+,\d+\):)", re.M)),
    ("eslint", re.compile(r"(\d+:\d+\s+error\s+|✖ \d+ problem|ESLint)", re.M)),
    ("traceback", re.compile(r"^Traceback \(most recent call last\):", re.M)),
    ("playwright", re.compile(r"(playwright|TimeoutError|expect\()", re.M | re.I)),
    ("gh", re.compile(r"(^gh:|GraphQL:|HTTP 4\d\d|pull request #\d+)", re.M)),
]


def detect_rtk_tool(text: str) -> str | None:
    for name, pattern in DETECTORS:
        if pattern.search(text):
            return name
    return None


def compress_rtk_tool(text: str, tool: str, *, aggressiveness: float = 0.5) -> CompressResult:
    fn = _COMPRESSORS.get(tool)
    if not fn:
        return CompressResult(content=text, strategy=f"rtk:{tool}", compressed=False)
    return fn(text, aggressiveness)


def _finish(
    text: str,
    out: str,
    tool: str,
    *,
    min_saved_ratio: float = 0.05,
) -> CompressResult:
    if not out or len(out) >= len(text) * (1 - min_saved_ratio):
        return CompressResult(content=text, strategy=f"rtk:{tool}", compressed=False)
    return CompressResult(content=out, strategy=f"rtk:{tool}", lossless=False, compressed=True)


def _keep_errors_and_summary(lines: list[str], *, error_re: re.Pattern[str], summary_re: re.Pattern[str]) -> list[str]:
    kept: list[str] = []
    for line in lines:
        if error_re.search(line) or summary_re.search(line):
            kept.append(line.rstrip())
    return kept


def _compress_docker(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"(error|failed|denied|Cannot |no such|Error response)", l, re.I)]
    steps = [
        l for l in lines
        if (l.strip().startswith("Step ") or " --->" in l)
        and not re.search(r"---> (Using cache|Running in [a-f0-9]+)\s*$", l.strip())
    ]
    summary = [l for l in lines if re.search(r"Successfully (built|tagged|pushed)|exited with code", l, re.I)]

    max_steps = max(0, int(4 * (1 - aggressiveness)))
    parts: list[str] = []
    if steps:
        if max_steps <= 0:
            parts.append(f"docker: {len(steps)} steps")
        else:
            parts.append(f"docker: {len(steps)} steps, last {min(max_steps, len(steps))}")
            parts.extend(l.strip() for l in steps[-max_steps:])
    if errors:
        parts.append(f"ERR ({len(errors)}):")
        parts.extend(l.strip() for l in errors[:10])
    if summary:
        if aggressiveness >= 0.7:
            built = tagged = None
            for l in summary:
                mb = re.search(r"Successfully built (\S+)", l, re.I)
                mt = re.search(r"Successfully tagged (\S+)", l, re.I)
                if mb:
                    h = mb.group(1)
                    built = h[:12] if len(h) > 12 else h
                if mt:
                    tagged = mt.group(1)
            bits = []
            if built:
                bits.append(f"built {built}")
            if tagged:
                bits.append(f"tagged {tagged}")
            if bits:
                parts.append(" · ".join(bits))
            else:
                parts.extend(l.strip() for l in summary[:3])
        else:
            parts.extend(l.strip() for l in summary[:5])

    return _finish(text, "\n".join(parts), "docker")


def _compress_cargo(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"^error\[E\d+\]|^error:", l)]
    warnings = [l for l in lines if l.startswith("warning:")]
    compiling = [l for l in lines if l.strip().startswith("Compiling ")]
    finished = [l for l in lines if "Finished" in l]

    max_crates = max(0, int(3 * (1 - aggressiveness)))
    parts: list[str] = []
    if finished:
        fin = [l.strip() for l in finished[:1]]
        if aggressiveness >= 0.7 and compiling and not errors:
            # One line: Finished … · N crates
            parts.append(f"{fin[0]} · {len(compiling)} crates")
        else:
            parts.extend(fin if aggressiveness >= 0.7 else [l.strip() for l in finished[:3]])
            if compiling and not errors:
                if max_crates <= 0:
                    parts.append(f"cargo: {len(compiling)} crates")
                else:
                    parts.append(f"cargo: {len(compiling)} crates, last {max_crates}")
                    parts.extend(l.strip() for l in compiling[-max_crates:])
    elif compiling:
        if max_crates <= 0:
            parts.append(f"cargo: {len(compiling)} crates")
        else:
            parts.append(f"cargo: {len(compiling)} crates, last {max_crates}")
            parts.extend(l.strip() for l in compiling[-max_crates:])
    if errors:
        parts.append(f"ERR ({len(errors)}):")
        parts.extend(l.strip() for l in errors[:15])
    if warnings and aggressiveness < 0.7:
        parts.append(f"WARN ({len(warnings)}):")
        parts.extend(l.strip() for l in warnings[:5])

    return _finish(text, "\n".join(parts), "cargo")


def _compress_kubectl(text: str, aggressiveness: float) -> CompressResult:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    header = lines[0] if lines and re.search(r"NAME\s+READY|NAMESPACE", lines[0]) else None
    data_lines = lines[1:] if header else lines
    max_rows = max(1, int(20 * (1 - aggressiveness)))

    not_ready = [l for l in data_lines if re.search(r"\b0/\d+\b|Error|CrashLoop|Pending|Failed", l)]
    parts: list[str] = []
    if header:
        parts.append(header)
    if not_ready:
        parts.append(f"=== NOT READY / PROBLEMS ({len(not_ready)}) ===")
        parts.extend(not_ready[:max_rows])
    parts.extend(data_lines[:max_rows])
    if len(data_lines) > max_rows:
        parts.append(f"... {len(data_lines) - max_rows} more resources")

    return _finish(text, "\n".join(parts), "kubectl")


def _compress_pip(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"ERROR:|Could not|No matching distribution", l, re.I)]
    installed = [l for l in lines if l.startswith("Successfully installed")]
    satisfied = [l for l in lines if l.startswith("Requirement already satisfied")]
    collecting = [l for l in lines if l.startswith("Collecting ")]

    max_collect = max(1, int(10 * (1 - aggressiveness)))
    parts: list[str] = []
    if installed:
        parts.extend(installed[:3])
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:10])
    if satisfied and aggressiveness < 0.6:
        parts.append(f"=== SATISFIED ({len(satisfied)}) ===")
        parts.extend(l.strip() for l in satisfied[:max_collect])
    elif collecting:
        parts.append(f"=== COLLECTING ({len(collecting)}, last {max_collect}) ===")
        parts.extend(l.strip() for l in collecting[-max_collect:])

    return _finish(text, "\n".join(parts), "pip")


def _compress_yarn(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if l.startswith("error ")]
    warnings = [l for l in lines if "warning" in l.lower()]
    summary = [l for l in lines if re.search(r"Done in |success|Saved lockfile|added \d+ packages", l, re.I)]

    parts = summary[:3]
    if errors:
        parts.append(f"errors: {len(errors)}")
        parts.extend(errors[:10])
    if warnings and aggressiveness < 0.7:
        parts.append(f"warnings: {len(warnings)}")
        parts.extend(warnings[:5])

    return _finish(text, "\n".join(parts), "yarn")


def _compress_go(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    fails = [l for l in lines if l.startswith("--- FAIL:") or l.startswith("FAIL\t")]
    errors = [l for l in lines if l.strip().startswith("    ") and ("Error" in l or "error:" in l)]
    ok_lines = [l for l in lines if l.startswith("ok  ") or l == "PASS"]
    run_lines = [l for l in lines if l.startswith("=== RUN ")]

    max_ok = max(1, int(8 * (1 - aggressiveness)))
    parts: list[str] = []
    if ok_lines:
        parts.append(f"=== PASS ({len(ok_lines)}) ===")
        parts.extend(ok_lines[:max_ok])
        if len(ok_lines) > max_ok:
            parts.append(f"... {len(ok_lines) - max_ok} more passed")
    if fails:
        parts.append(f"=== FAIL ({len(fails)}) ===")
        parts.extend(fails[:10])
    if errors:
        parts.extend(errors[:10])
    elif run_lines and not fails:
        parts.append(f"=== RUN ({len(run_lines)} tests) ===")
        parts.extend(run_lines[:max_ok])

    return _finish(text, "\n".join(parts), "go")


def _compress_make(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"\*\*\* |error:|Error \d+|make: \*\*\*", l, re.I)]
    entering = [l for l in lines if "Entering directory" in l or "Leaving directory" in l]
    targets = [l for l in lines if l.startswith("make[") and "warning" not in l.lower()]

    max_dirs = max(2, int(5 * (1 - aggressiveness)))
    parts: list[str] = []
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    if entering:
        parts.append(f"=== DIRS ({len(entering)}, last {max_dirs}) ===")
        parts.extend(l.strip() for l in entering[-max_dirs:])
    if targets and not errors:
        parts.extend(l.strip() for l in targets[:10])

    return _finish(text, "\n".join(parts), "make")


def _compress_curl(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    headers = [l for l in lines if l.startswith("HTTP/") or l.startswith("< ") or l.startswith("> ")]
    body = [l for l in lines if l not in headers and l.strip()]

    max_headers = max(1, int(12 * (1 - aggressiveness)))
    max_body = max(1, int(15 * (1 - aggressiveness)))
    parts = headers[:max_headers]
    if body:
        parts.append(f"=== BODY ({len(body)} lines) ===")
        parts.extend(body[:max_body])
        if len(body) > max_body:
            parts.append(f"... {len(body) - max_body} more lines")

    return _finish(text, "\n".join(parts), "curl")


def _compress_dotnet(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error (CS|MSB|NU)|Build FAILED", l, re.I)]
    summary = [l for l in lines if re.search(r"Build succeeded|Error\(s\)|Warning\(s\)", l, re.I)]
    warnings = [l for l in lines if "warning " in l.lower()]

    parts = summary[:5]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    if warnings and aggressiveness < 0.7:
        parts.append(f"warnings: {len(warnings)}")
        parts.extend(l.strip() for l in warnings[:5])

    return _finish(text, "\n".join(parts), "dotnet")


def _compress_webpack(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"ERROR in |Module not found|Failed to compile", l, re.I)]
    warnings = [l for l in lines if re.search(r"WARNING in |warning ", l, re.I)]
    assets = [l for l in lines if re.search(r"asset \S+ \d+ (?:KiB|MiB|bytes)", l, re.I)]
    summary = [l for l in lines if re.search(r"webpack compiled|compiled (?:with|successfully)", l, re.I)]

    max_assets = max(1, int(8 * (1 - aggressiveness)))
    parts: list[str] = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    if warnings and aggressiveness < 0.7:
        parts.append(f"=== WARNINGS ({len(warnings)}) ===")
        parts.extend(l.strip() for l in warnings[:8])
    if assets:
        parts.append(f"=== ASSETS ({len(assets)}, last {max_assets}) ===")
        parts.extend(l.strip() for l in assets[-max_assets:])

    return _finish(text, "\n".join(parts), "webpack")


def _compress_gradle(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"FAILURE:|BUILD FAILED|Execution failed|error:", l, re.I)]
    summary = [l for l in lines if re.search(r"BUILD SUCCESSFUL|BUILD FAILED|\d+ actionable task", l, re.I)]
    tasks = [l for l in lines if l.strip().startswith("> Task ")]

    max_tasks = max(1, int(12 * (1 - aggressiveness)))
    parts: list[str] = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    elif tasks:
        parts.append(f"=== TASKS ({len(tasks)}, last {max_tasks}) ===")
        parts.extend(l.strip() for l in tasks[-max_tasks:])

    return _finish(text, "\n".join(parts), "gradle")


def _compress_journalctl(text: str, aggressiveness: float) -> CompressResult:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    errors = [
        l for l in lines
        if re.search(r"\b(error|failed|fatal|panic|segfault|denied|unavailable)\b", l, re.I)
        and not l.startswith("--")
    ]
    markers = [l for l in lines if l.startswith("--")]
    entries = [l for l in lines if l not in markers and l not in errors]

    max_entries = max(1, int(25 * (1 - aggressiveness)))
    parts: list[str] = markers[:2]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(errors[:max_entries])
    parts.append(f"=== RECENT ({min(max_entries, len(entries))} of {len(entries)}) ===")
    parts.extend(entries[-max_entries:])
    if len(entries) > max_entries:
        parts.append(f"... {len(entries) - max_entries} older log lines omitted")

    return _finish(text, "\n".join(parts), "journalctl")


def _compress_terraform(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"^Error:|Error: |^\s*│ Error:", l)]
    plan_summary = [l for l in lines if re.search(r"^Plan: \d+ to |^No changes\.|^Apply complete!|^Destroy complete!", l)]
    changes = [
        l for l in lines
        if re.search(r"^\s*[~+-]\s+\S+|^  # module\.|^  \+ resource|^  ~ resource|^  - resource", l)
    ]

    max_changes = max(1, int(20 * (1 - aggressiveness)))
    parts: list[str] = plan_summary[:5]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    if changes:
        parts.append(f"=== CHANGES ({len(changes)}, first {max_changes}) ===")
        parts.extend(l.rstrip() for l in changes[:max_changes])
        if len(changes) > max_changes:
            parts.append(f"... {len(changes) - max_changes} more resource changes")

    return _finish(text, "\n".join(parts), "terraform")


def _compress_npm(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"npm ERR|npm error", l, re.I)]
    warnings = [l for l in lines if re.search(r"npm WARN", l, re.I)]
    summary = [
        l for l in lines
        if re.search(r"added \d+ packages|up to date|audited \d+ packages|found \d+ vulnerabilities", l, re.I)
    ]
    installing = [l for l in lines if re.search(r"^npm http fetch|^reify:|^idealTree:", l)]

    max_lines = max(1, int(10 * (1 - aggressiveness)))
    parts: list[str] = []
    for s in summary[:3]:
        if aggressiveness >= 0.7:
            s = re.sub(
                r"added (\d+) packages,\s*and\s+audited (\d+) packages in ([\d.]+s)",
                r"added \1 packages, audited \2 in \3",
                s,
                flags=re.I,
            )
            s = re.sub(
                r"added (\d+) packages(?:, and)? audited (\d+) packages in ([\d.]+s)",
                r"added \1 packages, audited \2 in \3",
                s,
                flags=re.I,
            )
            s = re.sub(r"added (\d+) packages$", r"added \1 packages", s, flags=re.I)
            # Keep the word packages on the added line for floor/hook checks
            s = re.sub(r"^audited (\d+) packages", r"audited \1", s, flags=re.I)
            s = re.sub(r"found (\d+) vulnerabilities \(", r"\1 vulnerabilities (", s, flags=re.I)
        parts.append(s.strip())
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:12])
    if not summary:
        if warnings and aggressiveness < 0.7:
            parts.append(f"=== WARNINGS ({len(warnings)}) ===")
            parts.extend(l.strip() for l in warnings[:max_lines])
        elif installing:
            parts.append(f"=== INSTALL ({len(installing)}, last {max_lines}) ===")
            parts.extend(l.strip() for l in installing[-max_lines:])
    elif (warnings or installing) and aggressiveness < 0.7:
        omitted = len(warnings) + len(installing)
        parts.append(f"npm: {omitted} warn/install lines omitted")

    return _finish(text, "\n".join(parts), "npm")


def _dense_jest_summary(line: str, aggressiveness: float) -> str:
    """Keep 'Test Suites' token; drop passed count when failed present at balanced+."""
    if aggressiveness < 0.5 or "Test Suites:" not in line:
        return line
    # Test Suites: 1 failed, 3 passed, 4 total → Test Suites: 1 failed/4
    line = re.sub(
        r"(Test Suites:\s*\d+\s+failed),\s*\d+\s+passed,\s*(\d+)\s+total",
        r"\1/\2",
        line,
        flags=re.I,
    )
    line = re.sub(
        r"(Test Suites:\s*\d+\s+failed),\s*(\d+)\s+total",
        r"\1/\2",
        line,
        flags=re.I,
    )
    return line


def _compress_jest(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    passes = [l for l in lines if l.startswith("PASS ")]

    # Small output: drop PASS lines, stack frames, collapse duplicate summaries
    if len(lines) <= 15 and passes:
        kept = [
            l
            for l in lines
            if not l.startswith("PASS ")
            and "at Object." not in l
            and not re.match(r"^\s+at\s+", l)
        ]
        summaries = [l for l in kept if re.search(r"Test Suites:|^Tests:", l)]
        body = [l for l in kept if l not in summaries]
        # Collapse Expected/Received onto one line; drop ● chrome when FAIL present
        compact_body: list[str] = []
        expected = received = None
        for l in body:
            s = l.strip()
            if s.startswith("●"):
                continue
            if s.startswith("Expected:"):
                expected = s.split(":", 1)[1].strip()
                continue
            if s.startswith("Received:"):
                received = s.split(":", 1)[1].strip()
                continue
            compact_body.append(l)
        if expected is not None or received is not None:
            compact_body.append(f"Expected {expected} got {received}")
        if len(summaries) > 1:
            # Keep one summary line only
            parts = compact_body + [_dense_jest_summary(summaries[0].strip(), aggressiveness)]
        else:
            parts = compact_body + [_dense_jest_summary(s.strip(), aggressiveness) for s in summaries[:1]]
        return _finish(text, "\n".join(parts), "jest")

    summary = [l for l in lines if re.search(r"Test Suites:|^Tests:|^Snapshots:|^Time:", l)]
    fails = [l for l in lines if l.startswith("FAIL ") or l.strip().startswith("●")]
    # Keep Expected/Received; drop stack frames (path already on FAIL line)
    errors = [l for l in lines if re.search(r"Expected|Received", l)]
    passes = [l for l in lines if l.startswith("PASS ")]

    max_pass = max(1, int(3 * (1 - aggressiveness)))
    parts: list[str] = [_dense_jest_summary(s.strip(), aggressiveness) for s in summary[:5]]
    if fails:
        parts.append(f"=== FAIL ({len(fails)}) ===")
        parts.extend(l.strip() for l in fails[:10])
    if errors:
        parts.extend(l.strip() for l in errors[:12])
    if passes:
        if (fails and len(passes) > 3) or (not fails and len(passes) > max_pass):
            parts.append(f"PASS: {len(passes)} suites omitted")
        else:
            parts.extend(l.strip() for l in passes)

    return _finish(text, "\n".join(parts), "jest")


def _compress_pnpm(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"ERR_| ELIFECYCLE |ERROR", l)]
    warnings = [l for l in lines if re.search(r"WARN|deprecated", l, re.I)]
    summary = [l for l in lines if re.search(r"Done in [\d.]+s|^Packages:", l)]
    progress = [l for l in lines if l.startswith("Progress:") and l not in summary]

    max_lines = max(1, int(8 * (1 - aggressiveness)))
    parts: list[str] = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:12])
    if warnings and aggressiveness < 0.7:
        parts.append(f"=== WARNINGS ({len(warnings)}) ===")
        parts.extend(l.strip() for l in warnings[:max_lines])
    elif progress and not summary:
        parts.append(f"=== PROGRESS ({len(progress)}, last {max_lines}) ===")
        parts.extend(l.strip() for l in progress[-max_lines:])
    elif progress and summary and aggressiveness < 0.7:
        parts.append(f"Progress: {len(progress)} resolution steps omitted")

    return _finish(text, "\n".join(parts), "pnpm")


def _compress_vite(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error during build|✘ \[ERROR\]|Failed to compile", l, re.I)]
    summary = [l for l in lines if re.search(r"^vite v|built in [\d.]+s|✓ built in", l, re.I)]
    assets = [l for l in lines if re.search(r"dist/.*\.(js|css|html)", l, re.I)]
    warnings = [l for l in lines if "warning" in l.lower()]

    max_assets = max(0, int(3 * (1 - aggressiveness)))
    # Prefer built-time line; drop "vite vX building..." when built present at balanced+
    built = [l for l in summary if re.search(r"built in", l, re.I)]
    if aggressiveness >= 0.7 and built:
        parts: list[str] = [built[0].strip()]
    else:
        parts = summary[:2]
    if errors:
        parts.append(f"ERR ({len(errors)}):")
        parts.extend(l.strip() for l in errors[:12])
    if assets:
        if max_assets <= 0:
            parts.append(f"vite: {len(assets)} assets")
        else:
            parts.append(f"vite: {len(assets)} assets, last {max_assets}")
            parts.extend(l.strip() for l in assets[-max_assets:])
            if len(assets) > max_assets:
                parts.append(f"... {len(assets) - max_assets} more assets")
    if warnings and aggressiveness < 0.7:
        parts.append(f"warnings: {len(warnings)}")
        parts.extend(l.strip() for l in warnings[:5])

    return _finish(text, "\n".join(parts), "vite")


def _compress_tsc(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error TS\d+|Found \d+ error", l)]
    details = [l for l in lines if re.search(r"\.tsx?\(\d+,\d+\):", l)]
    max_lines = max(1, int(15 * (1 - aggressiveness)))
    parts = errors[:3]
    if details:
        parts.append(f"=== TS ERRORS ({len(details)}) ===")
        parts.extend(l.strip() for l in details[:max_lines])
    return _finish(text, "\n".join(parts), "tsc")


def _compress_eslint(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error|✖ \d+ problem", l, re.I)]
    max_lines = max(1, int(12 * (1 - aggressiveness)))
    parts = [l.strip() for l in errors[:max_lines]]
    if len(errors) > max_lines:
        parts.append(f"... {len(errors) - max_lines} more eslint issues")
    return _finish(text, "\n".join(parts), "eslint")


def _compress_gh(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error|GraphQL:|HTTP 4\d\d", l, re.I)]
    summary = [l for l in lines if re.search(r"pull request|merged|created|#\\d+", l, re.I)]
    parts = summary[:5] + [l.strip() for l in errors[:8]]
    return _finish(text, "\n".join(parts), "gh")


def _compress_traceback(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    keep: list[str] = []
    in_tb = False
    for line in lines:
        if line.startswith("Traceback"):
            in_tb = True
            if aggressiveness < 0.6:
                keep.append(line)
            continue
        if in_tb:
            if line.startswith("  ") or line.startswith("File ") or line.strip().startswith("^"):
                if aggressiveness < 0.6:
                    keep.append(line)
            elif line.strip() and not line.startswith(" "):
                keep.append(line)
                in_tb = False
            elif aggressiveness < 0.6:
                keep.append(line)
        elif re.search(r"Error:|Exception:|SyntaxError:", line):
            keep.append(line)
    max_lines = max(2, int(25 * (1 - aggressiveness * 0.5)))
    out = "\n".join(keep[:max_lines])
    return _finish(text, out, "traceback")


def _compress_playwright(text: str, aggressiveness: float) -> CompressResult:
    # Lazy import: test_output imports this module for jest.
    from token_engine.compressor.test_output import _compress_playwright as _pw

    return _pw(text, aggressiveness)


_COMPRESSORS = {
    "docker": _compress_docker,
    "cargo": _compress_cargo,
    "kubectl": _compress_kubectl,
    "pip": _compress_pip,
    "yarn": _compress_yarn,
    "go": _compress_go,
    "make": _compress_make,
    "curl": _compress_curl,
    "dotnet": _compress_dotnet,
    "webpack": _compress_webpack,
    "gradle": _compress_gradle,
    "journalctl": _compress_journalctl,
    "terraform": _compress_terraform,
    "npm": _compress_npm,
    "jest": _compress_jest,
    "pnpm": _compress_pnpm,
    "vite": _compress_vite,
    "tsc": _compress_tsc,
    "eslint": _compress_eslint,
    "gh": _compress_gh,
    "playwright": _compress_playwright,
    "traceback": _compress_traceback,
}
