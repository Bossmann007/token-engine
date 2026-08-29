#Requires -Version 7.0
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Cli = Join-Path $Root ".venv\Scripts\token-engine.exe"

Write-Host "== token-engine health =="
& $Cli serve 2>$null | Out-Null
Start-Sleep -Seconds 1
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8741/health" -TimeoutSec 3
    Write-Host "OK: $($health.status)"
} catch {
    Write-Host "WARN: API not running — start with: token-engine serve"
}

Write-Host "`n== benchmark baseline =="
& $Cli benchmark --check-baseline
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n== optimize-context smoke =="
$fixture = Join-Path $Root "benchmarks\fixtures\large_agent_session.json"
& $VenvPy -c @"
import json, httpx
from pathlib import Path
data = json.loads(Path(r'$fixture').read_text(encoding='utf-8'))
payload = {'items': data['items'], 'task_query': data['items'][1]['content'], 'quality': 'balanced'}
try:
    r = httpx.post('http://127.0.0.1:8741/optimize-context', json=payload, timeout=30)
    r.raise_for_status()
    stats = r.json().get('stats', {})
    ratio = stats.get('compression_ratio', 0)
    print(f'large_agent_session via API: {ratio*100:.1f}% saved')
    assert ratio >= 0.15, f'ratio too low: {ratio}'
except Exception as e:
    from token_engine.harness import HarnessClient
    out = HarnessClient(prefer_api=False).optimize_context(data['items'], task_query=data['items'][1]['content'])
    ratio = out['stats']['compression_ratio']
    print(f'in-process fallback: {ratio*100:.1f}% saved')
    assert ratio >= 0.15
"@

Write-Host "`nSMOKE OK"
