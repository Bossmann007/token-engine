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
    ("terraform", re.compile(r"(^Terraform |^Plan: \d+ to |^No changes\.|^Error:|^\s*[~+-]\s+\S+.*= |^  # module\.)", re.M)),
    ("pnpm", re.compile(r"(^Progress: resolved|^Packages: \+|^Done in [\d.]+s|^WARN\s+.*deprecated)", re.M)),
    ("vite", re.compile(r"(^vite v\d|built in [\d.]+s|dist/.*\.(js|css)|error during build)", re.M)),
    ("npm", re.compile(r"(^npm warn |^npm error |added \d+ packages|audited \d+ packages|up to date)", re.M | re.I)),
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

    max_steps = max(3, int(8 * (1 - aggressiveness)))
    parts: list[str] = []
    if steps:
        parts.append(f"=== DOCKER STEPS ({len(steps)} total, last {min(max_steps, len(steps))}) ===")
        parts.extend(l.strip() for l in steps[-max_steps:])
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:10])
    if summary:
        parts.extend(l.strip() for l in summary[:5])

    return _finish(text, "\n".join(parts), "docker")


def _compress_cargo(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"^error\[E\d+\]|^error:", l)]
    warnings = [l for l in lines if l.startswith("warning:")]
    compiling = [l for l in lines if l.strip().startswith("Compiling ")]
    finished = [l for l in lines if "Finished" in l]

    max_crates = max(3, int(8 * (1 - aggressiveness)))
    parts: list[str] = []
    if finished:
        parts.extend(l.strip() for l in finished[:3])
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:15])
    elif compiling:
        parts.append(f"=== COMPILED ({len(compiling)} crates, showing last {max_crates}) ===")
        parts.extend(l.strip() for l in compiling[-max_crates:])
    if warnings and aggressiveness < 0.7:
        parts.append(f"=== WARNINGS ({len(warnings)}) ===")
        parts.extend(l.strip() for l in warnings[:5])

    return _finish(text, "\n".join(parts), "cargo")


def _compress_kubectl(text: str, aggressiveness: float) -> CompressResult:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    header = lines[0] if lines and re.search(r"NAME\s+READY|NAMESPACE", lines[0]) else None
    data_lines = lines[1:] if header else lines
    max_rows = max(5, int(20 * (1 - aggressiveness)))

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

    max_collect = max(3, int(10 * (1 - aggressiveness)))
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

    max_ok = max(3, int(8 * (1 - aggressiveness)))
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

    max_headers = max(5, int(12 * (1 - aggressiveness)))
    max_body = max(3, int(15 * (1 - aggressiveness)))
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

    max_assets = max(3, int(8 * (1 - aggressiveness)))
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

    max_tasks = max(4, int(12 * (1 - aggressiveness)))
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

    max_entries = max(5, int(25 * (1 - aggressiveness)))
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

    max_changes = max(5, int(20 * (1 - aggressiveness)))
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

    max_lines = max(3, int(10 * (1 - aggressiveness)))
    parts: list[str] = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:12])
    if warnings and aggressiveness < 0.7:
        parts.append(f"=== WARNINGS ({len(warnings)}) ===")
        parts.extend(l.strip() for l in warnings[:max_lines])
    elif installing:
        parts.append(f"=== INSTALL ({len(installing)}, last {max_lines}) ===")
        parts.extend(l.strip() for l in installing[-max_lines:])

    return _finish(text, "\n".join(parts), "npm")


def _compress_jest(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    summary = [l for l in lines if re.search(r"Test Suites:|^Tests:|^Snapshots:|^Time:", l)]
    fails = [l for l in lines if l.startswith("FAIL ") or l.strip().startswith("●")]
    errors = [l for l in lines if re.search(r"Expected|Received|at Object\.|^\s+at ", l)]
    passes = [l for l in lines if l.startswith("PASS ")]

    max_pass = max(1, int(3 * (1 - aggressiveness)))
    parts: list[str] = summary[:5]
    if fails:
        parts.append(f"=== FAIL ({len(fails)}) ===")
        parts.extend(l.strip() for l in fails[:10])
    if errors:
        parts.extend(l.strip() for l in errors[:12])
    if passes:
        if fails or len(passes) > max_pass:
            parts.append(f"PASS: {len(passes)} suites omitted")
        else:
            parts.extend(l.strip() for l in passes[:max_pass])

    return _finish(text, "\n".join(parts), "jest")


def _compress_pnpm(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"ERR_| ELIFECYCLE |ERROR", l)]
    warnings = [l for l in lines if re.search(r"WARN|deprecated", l, re.I)]
    summary = [l for l in lines if re.search(r"Done in [\d.]+s|^Packages:", l)]
    progress = [l for l in lines if l.startswith("Progress:") and l not in summary]

    max_lines = max(3, int(8 * (1 - aggressiveness)))
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
    elif progress and summary:
        parts.append(f"Progress: {len(progress)} resolution steps omitted")

    return _finish(text, "\n".join(parts), "pnpm")


def _compress_vite(text: str, aggressiveness: float) -> CompressResult:
    lines = text.splitlines()
    errors = [l for l in lines if re.search(r"error during build|✘ \[ERROR\]|Failed to compile", l, re.I)]
    summary = [l for l in lines if re.search(r"^vite v|built in [\d.]+s|✓ built in", l, re.I)]
    assets = [l for l in lines if re.search(r"dist/.*\.(js|css|html)", l, re.I)]
    warnings = [l for l in lines if "warning" in l.lower()]

    max_assets = max(3, int(8 * (1 - aggressiveness)))
    parts: list[str] = summary[:3]
    if errors:
        parts.append(f"=== ERRORS ({len(errors)}) ===")
        parts.extend(l.strip() for l in errors[:12])
    if assets:
        parts.append(f"=== OUTPUT ({len(assets)}, last {max_assets}) ===")
        parts.extend(l.strip() for l in assets[-max_assets:])
    if warnings and aggressiveness < 0.7:
        parts.append(f"warnings: {len(warnings)}")
        parts.extend(l.strip() for l in warnings[:5])

    return _finish(text, "\n".join(parts), "vite")


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
}
