param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Arguments
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'agent_lease.py'
$mutex = $null
$held = $false

try {
    if ($Arguments -contains 'claim') {
        $mutex = [System.Threading.Mutex]::new(
            $false,
            'Global\ZeitgeistScheduledAgentClaim'
        )
        $held = $mutex.WaitOne([TimeSpan]::FromSeconds(15))
        if (-not $held) {
            throw 'Timed out waiting for Zeitgeist claim mutex.'
        }
    }

    & python $scriptPath @Arguments
    exit $LASTEXITCODE
}
finally {
    if ($held) {
        $mutex.ReleaseMutex()
    }
    if ($null -ne $mutex) {
        $mutex.Dispose()
    }
}
