# Generates one Sarsa-only protected setting locally. No key is printed or saved.
# Paste from the clipboard directly into the matching protected Vercel setting.
[CmdletBinding(DefaultParameterSetName = 'Copy')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Copy')]
    [ValidateSet('SARSA_GOOGLE_TOKEN_KEYS', 'SARSA_STUDIO_SIGNING_KEY', 'SARSA_BOOKING_KEYS', 'SARSA_CONTACT_KEYS', 'SARSA_GOOGLE_WORKER_KEY', 'SARSA_EMAIL_WORKER_KEY', 'SARSA_RECOVERY_WORKER_KEY', 'SARSA_WAKE_KEY')]
    [string]$Name,
    [Parameter(Mandatory = $true, ParameterSetName = 'Check')]
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'

function New-SarsaRandomKey {
    $sarsaBytes = New-Object byte[] 32
    $sarsaGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $sarsaGenerator.GetBytes($sarsaBytes)
        return [Convert]::ToBase64String($sarsaBytes).Replace('+', '-').Replace('/', '_')
    }
    finally {
        $sarsaGenerator.Dispose()
        [Array]::Clear($sarsaBytes, 0, $sarsaBytes.Length)
    }
}

function Format-SarsaSetting([string]$SettingName, [string]$Key) {
    if ($SettingName -eq 'SARSA_BOOKING_KEYS') {
        return (@{receipt = $Key; context = (New-SarsaRandomKey); risk = (New-SarsaRandomKey)} | ConvertTo-Json -Compress)
    }
    if ($SettingName -eq 'SARSA_CONTACT_KEYS') {
        return (@{digest = $Key; encryption = @((New-SarsaRandomKey))} | ConvertTo-Json -Compress)
    }
    if ($SettingName -eq 'SARSA_GOOGLE_TOKEN_KEYS') { return '["' + $Key + '"]' }
    return $Key
}

if ($VerifyOnly) {
    $sarsaCheckKey = New-SarsaRandomKey
    if ($sarsaCheckKey -cnotmatch '^[A-Za-z0-9_-]{43}=$') { throw 'Key format check failed.' }
    $sarsaDecoded = [Convert]::FromBase64String($sarsaCheckKey.Replace('-', '+').Replace('_', '/'))
    if ($sarsaDecoded.Length -ne 32) { throw 'Key size check failed.' }
    $sarsaArray = @(ConvertFrom-Json (Format-SarsaSetting 'SARSA_GOOGLE_TOKEN_KEYS' $sarsaCheckKey))
    if ($sarsaArray.Count -ne 1 -or $sarsaArray[0] -cne $sarsaCheckKey) { throw 'Key list check failed.' }
    if ((Format-SarsaSetting 'SARSA_STUDIO_SIGNING_KEY' $sarsaCheckKey) -cne $sarsaCheckKey) { throw 'Signing format check failed.' }
    foreach ($sarsaWorkerName in @('SARSA_GOOGLE_WORKER_KEY', 'SARSA_EMAIL_WORKER_KEY', 'SARSA_RECOVERY_WORKER_KEY', 'SARSA_WAKE_KEY')) {
        if ((Format-SarsaSetting $sarsaWorkerName $sarsaCheckKey) -cne $sarsaCheckKey) { throw 'Worker format check failed.' }
    }
    $sarsaBooking = ConvertFrom-Json (Format-SarsaSetting 'SARSA_BOOKING_KEYS' $sarsaCheckKey)
    $sarsaParts = @($sarsaBooking.receipt, $sarsaBooking.context, $sarsaBooking.risk)
    if (@($sarsaParts | Select-Object -Unique).Count -ne 3) { throw 'Independent keys check failed.' }
    foreach ($sarsaPart in $sarsaParts) {
        if ($sarsaPart -cnotmatch '^[A-Za-z0-9_-]{43}=$') { throw 'Booking key format check failed.' }
    }
    $sarsaContact = ConvertFrom-Json (Format-SarsaSetting 'SARSA_CONTACT_KEYS' $sarsaCheckKey)
    if ($sarsaContact.digest -cne $sarsaCheckKey -or @($sarsaContact.encryption).Count -ne 1 -or
        $sarsaContact.encryption[0] -ceq $sarsaContact.digest -or
        $sarsaContact.encryption[0] -cnotmatch '^[A-Za-z0-9_-]{43}=$') { throw 'Contact key structure check failed.' }
    [Array]::Clear($sarsaDecoded, 0, $sarsaDecoded.Length)
    $sarsaCheckKey = $null
    $sarsaArray = $null
    Write-Host 'Checks passed. No clipboard changes, files or configured credentials were created.'
    exit 0
}

$sarsaValue = Format-SarsaSetting $Name (New-SarsaRandomKey)
try {
    Set-Clipboard -Value $sarsaValue
    Write-Host "Copied a new value for $Name. Paste it directly into the matching protected setting."
    Write-Host 'Use Production only and mark it Sensitive. Keep a copy in your password manager.'
    Write-Host 'Do not rerun this command to replace an existing live key; key rotation needs a planned change.'
}
finally { $sarsaValue = $null }
