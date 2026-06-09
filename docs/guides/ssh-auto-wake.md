# SSH Auto-Wake via WoL-Monkey

Automatically wake a sleeping machine when you `ssh` (or connect via VS Code
Remote-SSH, Windsurf, JetBrains Gateway, etc.) — no manual intervention needed.

## How it works

SSH's `ProxyCommand` directive lets you run an arbitrary command before the
connection is established. We use a small shell script that:

1. Calls `GET /api/machines/{id}/status` — if the machine is already online,
   exits immediately (zero overhead).
2. If offline, calls `POST /api/machines/{id}/wake/direct` with
   `ensure_online=true` — the API sends the magic packet **and polls until
   the machine responds on TCP/SSH**, then returns.
3. SSH then connects normally to the now-awake machine.

The whole thing is transparent: your IDE or terminal just sees a slightly
slower connection on first connect when the machine was sleeping.

---

## Prerequisites

- WoL-Monkey running and reachable from your client machine
- An API token with at least read access (create one via **API Tokens** in the nav)
- `curl` and `jq` installed on the client (`sudo apt install curl jq` /
  `brew install curl jq`)

---

## Step 1 — Create an API token

In the WoL-Monkey UI go to **API Tokens** (nav link) → pick your machine → **+ Add token**.
Copy the token — it looks like `wm_abc123_xxxxxxxxxxxxxxxx`.

Store it in your shell environment or directly in the script (see below).
The safest place is `~/.config/wol-monkey/token` (mode `600`):

```bash
mkdir -p ~/.config/wol-monkey
echo "wm_abc123_xxxxxxxxxxxxxxxx" > ~/.config/wol-monkey/token
chmod 600 ~/.config/wol-monkey/token
```

---

## Step 2 — Find your machine ID

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/wol-monkey/token)" \
  http://<wol-monkey-host>/api/machines | jq '.[].id, .[].name'
```

Note the UUID for the machine you want to auto-wake.

---

## Step 3 — Install the wake script

Save this as `~/.local/bin/wol-wake` and make it executable:

```bash
install -Dm 755 /dev/stdin ~/.local/bin/wol-wake << 'EOF'
#!/usr/bin/env bash
# wol-wake — wake a machine via WoL-Monkey before SSH connects
# Usage: wol-wake <machine-id> <ssh-host> <ssh-port>
set -euo pipefail

MACHINE_ID="${1:?machine-id required}"
SSH_HOST="${2:?ssh-host required}"
SSH_PORT="${3:-22}"

WOL_BASE="${WOL_MONKEY_URL:-http://localhost:8000}"
TOKEN_FILE="${WOL_MONKEY_TOKEN_FILE:-$HOME/.config/wol-monkey/token}"
TOKEN="${WOL_MONKEY_TOKEN:-$(cat "$TOKEN_FILE" 2>/dev/null)}"
POLL_TIMEOUT="${WOL_MONKEY_TIMEOUT:-90}"

if [[ -z "$TOKEN" ]]; then
  echo "wol-wake: no API token — set WOL_MONKEY_TOKEN or create $TOKEN_FILE" >&2
  exit 1
fi

AUTH=(-H "Authorization: Bearer $TOKEN")

# Check if already online
STATE=$(curl -sf "${AUTH[@]}" \
  "$WOL_BASE/api/machines/$MACHINE_ID/status" \
  | jq -r '.state' 2>/dev/null || echo "unknown")

if [[ "$STATE" == "online" ]]; then
  # Already up — connect immediately
  exec nc "$SSH_HOST" "$SSH_PORT"
fi

echo "wol-wake: machine is $STATE — sending wake packet..." >&2

# Wake and wait for online (ensure_online=true polls until TCP/SSH responds)
RESULT=$(curl -sf -X POST "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"ensure_online\": true, \"poll_timeout_s\": $POLL_TIMEOUT}" \
  "$WOL_BASE/api/machines/$MACHINE_ID/wake/direct" 2>&1) || true

echo "wol-wake: machine should be online — connecting" >&2
exec nc "$SSH_HOST" "$SSH_PORT"
EOF
```

---

## Step 4 — Configure `~/.ssh/config`

```ssh-config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand wol-wake <machine-uuid> %h %p
```

Replace `<machine-uuid>` with the UUID from Step 2.

If WoL-Monkey isn't accessible at the default URL, set it explicitly:

```ssh-config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand env WOL_MONKEY_URL=http://<wol-monkey-host> wol-wake <uuid> %h %p
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WOL_MONKEY_URL` | `http://localhost:8000` | Base URL of your WoL-Monkey instance (no trailing slash) |
| `WOL_MONKEY_TOKEN` | — | API token (takes precedence over file) |
| `WOL_MONKEY_TOKEN_FILE` | `~/.config/wol-monkey/token` | Path to token file |
| `WOL_MONKEY_TIMEOUT` | `90` | Seconds to wait for machine to come online |

---

## VS Code / Windsurf / Cursor Remote-SSH

These IDEs use `~/.ssh/config` directly, so Step 4 is all you need.
The `ProxyCommand` runs before every connection attempt, and since the script
fast-paths if the machine is already online, reconnects are instant.

**Windsurf / VS Code**: open the Remote Explorer, add the host — it picks up
`~/.ssh/config` automatically.

**Tip:** set `ServerAliveInterval 30` and `ServerAliveCountMax 3` on the host
entry so the IDE doesn't drop the connection if the machine becomes briefly
unreachable after waking:

```ssh-config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand wol-wake <machine-uuid> %h %p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

---

## Tailscale / remote access

If WoL-Monkey is only accessible via Tailscale, set `WOL_MONKEY_URL` to your
Tailscale address:

```ssh-config
Host my-machine
    HostName <machine-tailscale-ip>
    User <your-username>
    ProxyCommand env WOL_MONKEY_URL=http://<wol-monkey-tailscale-ip> wol-wake <uuid> %h %p
```

---

## Troubleshooting

**`wol-wake: command not found`** — ensure `~/.local/bin` is on your `PATH`:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

**Connection times out after wake** — increase `WOL_MONKEY_TIMEOUT` (default
90 s). Some machines take longer to boot to SSH.

**`jq: command not found`** — install `jq`, or remove the status check at the
top of the script (it'll always send a wake packet, which is harmless if the
machine is already on).

**API returns 401** — check your token hasn't been revoked in **API Tokens** (nav link).

---

## Windows

On Windows, `ProxyCommand` works inside [Git for Windows](https://gitforwindows.org/) bash,
[WSL2](https://learn.microsoft.com/en-us/windows/wsl/), or with [OpenSSH for Windows](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse).

### Option A — WSL2 (recommended)

Install the script inside your WSL2 distro exactly as above — WSL's `ssh` and `ProxyCommand`
behave identically to Linux. Your Windows SSH client can delegate to WSL via:

```ssh-config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand wsl wol-wake <machine-uuid> %h %p
```

### Option B — Native PowerShell script

If you use Windows OpenSSH without WSL, save this as
`%USERPROFILE%\wol-wake.ps1` and store your token in
`%APPDATA%\wol-monkey\token`:

```powershell
# wol-wake.ps1 — wake a machine via WoL-Monkey before SSH connects
# Usage: powershell -File wol-wake.ps1 <machine-id> <ssh-host> <ssh-port>
param(
    [Parameter(Mandatory)][string]$MachineId,
    [Parameter(Mandatory)][string]$SshHost,
    [string]$SshPort = "22"
)

$WolBase  = if ($env:WOL_MONKEY_URL)       { $env:WOL_MONKEY_URL }       else { "http://localhost:8000" }
$TokenFile= if ($env:WOL_MONKEY_TOKEN_FILE){ $env:WOL_MONKEY_TOKEN_FILE } else { "$env:APPDATA\wol-monkey\token" }
$Token    = if ($env:WOL_MONKEY_TOKEN)     { $env:WOL_MONKEY_TOKEN }     else { (Get-Content $TokenFile -ErrorAction SilentlyContinue) }
$Timeout  = if ($env:WOL_MONKEY_TIMEOUT)   { $env:WOL_MONKEY_TIMEOUT }   else { 90 }

if (-not $Token) {
    Write-Error "wol-wake: no API token — set WOL_MONKEY_TOKEN or create $TokenFile"
    exit 1
}

$Headers = @{ Authorization = "Bearer $Token" }

try {
    $Status = Invoke-RestMethod -Uri "$WolBase/api/machines/$MachineId/status" `
        -Headers $Headers -Method Get
    if ($Status.state -eq "online") {
        Write-Host "wol-wake: already online — connecting" -ForegroundColor Green
    } else {
        Write-Host "wol-wake: $($Status.state) — sending wake packet..." -ForegroundColor Yellow
        $Body = "{`"ensure_online`":true,`"poll_timeout_s`":$Timeout}"
        Invoke-RestMethod -Uri "$WolBase/api/machines/$MachineId/wake/direct" `
            -Headers $Headers -Method Post `
            -ContentType "application/json" -Body $Body | Out-Null
        Write-Host "wol-wake: machine online — connecting" -ForegroundColor Green
    }
} catch {
    Write-Warning "wol-wake: API call failed ($_) — attempting connection anyway"
}

# Hand off to OpenSSH's built-in nc equivalent
& "$env:SystemRoot\System32\OpenSSH\ssh.exe" -W "${SshHost}:${SshPort}" localhost
```

Store your token:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\wol-monkey" | Out-Null
"wm_your_token_here" | Set-Content "$env:APPDATA\wol-monkey\token" -NoNewline
```

Add to `%USERPROFILE%\.ssh\config`:

```ssh-config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand powershell -File %USERPROFILE%\wol-wake.ps1 <machine-uuid> %h %p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

> **Note:** Windows OpenSSH's `ProxyCommand` runs `.exe` or scripts via `cmd.exe`.
> If `powershell` is not on `PATH`, use the full path:
> `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
