# Capture an EXISTING owner-selected key. No generation, rotation or provider change.
# Windows DPAPI encrypts the local copy for the current Windows user.
[CmdletBinding(DefaultParameterSetName = 'Capture')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Capture')]
    [ValidateSet('SARSA_GOOGLE_WORKER_KEY','SARSA_EMAIL_WORKER_KEY','SARSA_RECOVERY_WORKER_KEY','SARSA_WAKE_KEY')]
    [string]$Name,
    [Parameter(ParameterSetName = 'Capture')]
    [ValidateRange(1,900)]
    [int]$WaitSeconds = 900,
    [Parameter(ParameterSetName = 'Capture')]
    [switch]$ConfirmedCurrentClipboard,
    [Parameter(Mandatory = $true, ParameterSetName = 'Verify')]
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Security
$sarsaScope = [Security.Cryptography.DataProtectionScope]::CurrentUser
$sarsaNames = @('SARSA_GOOGLE_WORKER_KEY','SARSA_EMAIL_WORKER_KEY','SARSA_RECOVERY_WORKER_KEY','SARSA_WAKE_KEY')

function Get-SarsaEntropy([string]$SettingName) {
    return [Text.Encoding]::UTF8.GetBytes('Sarsa Project 004 worker key v1/' + $SettingName)
}

function Get-SarsaKeyBytes([string]$Value) {
    if ($Value -cnotmatch '^[A-Za-z0-9_-]{43}=$') { throw 'invalid_key' }
    $sarsaBytes = [Convert]::FromBase64String($Value.Replace('-','+').Replace('_','/'))
    $sarsaCanonical = [Convert]::ToBase64String($sarsaBytes).Replace('+','-').Replace('/','_')
    if ($sarsaBytes.Length -ne 32 -or $sarsaCanonical -cne $Value) {
        [Array]::Clear($sarsaBytes,0,$sarsaBytes.Length)
        throw 'invalid_key'
    }
    return ,$sarsaBytes
}

try {
    if ($VerifyOnly) {
        # All test bytes are synthetic and stay in memory; clipboard is untouched.
        $sarsaSample = [Convert]::ToBase64String([byte[]](0..31)).Replace('+','-').Replace('/','_')
        $sarsaBytes = Get-SarsaKeyBytes $sarsaSample
        $sarsaCipher = [Security.Cryptography.ProtectedData]::Protect($sarsaBytes,(Get-SarsaEntropy $sarsaNames[0]),$sarsaScope)
        $sarsaRestored = [Security.Cryptography.ProtectedData]::Unprotect($sarsaCipher,(Get-SarsaEntropy $sarsaNames[0]),$sarsaScope)
        if ([Convert]::ToBase64String($sarsaRestored) -cne [Convert]::ToBase64String($sarsaBytes)) { throw 'round_trip_failed' }
        $sarsaWrongNameRejected = $false
        try { [void][Security.Cryptography.ProtectedData]::Unprotect($sarsaCipher,(Get-SarsaEntropy $sarsaNames[1]),$sarsaScope) }
        catch { $sarsaWrongNameRejected = $true }
        if (-not $sarsaWrongNameRejected) { throw 'name_binding_failed' }
        foreach ($sarsaInvalid in @('', 'not-a-key', $sarsaSample.TrimEnd('='), $sarsaSample.Substring(0,42)+'x=')) {
            $sarsaRejected = $false
            try { [void](Get-SarsaKeyBytes $sarsaInvalid) } catch { $sarsaRejected = $true }
            if (-not $sarsaRejected) { throw 'invalid_format_accepted' }
        }
        Write-Output 'Synthetic key format, Windows encryption, round trip and name-binding checks passed. No clipboard or file changes.'
        exit 0
    }

    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class SarsaWorkerClipboard {
    [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();
}
'@
    $sarsaDirectory = Join-Path $PSScriptRoot 'private'
    $sarsaDestination = Join-Path $sarsaDirectory ($Name + '.dpapi')
    if (Test-Path -LiteralPath $sarsaDestination) {
        $sarsaRestored = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($sarsaDestination),(Get-SarsaEntropy $Name),$sarsaScope)
        if ($sarsaRestored.Length -ne 32) { throw 'existing_copy_invalid' }
        Write-Output ('Existing protected copy verified and retained for ' + $Name + '. No replacement performed.')
        exit 2
    }
    # Ignore earlier copies by default. The explicit flag is only for the owner
    # who has just confirmed copying this exact named key after a reader expired.
    $sarsaInitialSequence = [SarsaWorkerClipboard]::GetClipboardSequenceNumber()
    $sarsaDeadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    Write-Output ('Reader ready for ' + $Name + '. Copy that saved value now; no value will be displayed.')
    while ([DateTime]::UtcNow -lt $sarsaDeadline) {
        if (-not $ConfirmedCurrentClipboard -and [SarsaWorkerClipboard]::GetClipboardSequenceNumber() -eq $sarsaInitialSequence) {
            Start-Sleep -Milliseconds 200
            continue
        }
        $sarsaValue = $null
        try { $sarsaValue = Get-Clipboard -Raw } catch { }
        if ($null -eq $sarsaValue -or $sarsaValue -cnotmatch '^[A-Za-z0-9_-]{43}=$') {
            Start-Sleep -Milliseconds 200
            continue
        }
        $sarsaBytes = Get-SarsaKeyBytes $sarsaValue
        # A copied key cannot accidentally become two different lane keys.
        $sarsaDuplicate = $false
        foreach ($sarsaOther in $sarsaNames) {
            $sarsaOtherPath = Join-Path $sarsaDirectory ($sarsaOther + '.dpapi')
            if (-not (Test-Path -LiteralPath $sarsaOtherPath)) { continue }
            $sarsaPrevious = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($sarsaOtherPath),(Get-SarsaEntropy $sarsaOther),$sarsaScope)
            try {
                if ([Convert]::ToBase64String($sarsaPrevious) -ceq [Convert]::ToBase64String($sarsaBytes)) { $sarsaDuplicate = $true }
            }
            finally { [Array]::Clear($sarsaPrevious,0,$sarsaPrevious.Length) }
        }
        if ($sarsaDuplicate) {
            if ($ConfirmedCurrentClipboard) { throw 'duplicate_key' }
            # Clipboard managers can change the sequence before replacing the
            # old value. Ignore that old lane value rather than ending the reader.
            [Array]::Clear($sarsaBytes,0,$sarsaBytes.Length)
            $sarsaValue = $null
            Start-Sleep -Milliseconds 200
            continue
        }
        $sarsaCipher = [Security.Cryptography.ProtectedData]::Protect($sarsaBytes,(Get-SarsaEntropy $Name),$sarsaScope)
        [void][IO.Directory]::CreateDirectory($sarsaDirectory)
        # Flush and verify a uniquely owned encrypted temporary file before an
        # atomic same-directory move. Interrupted writes cannot occupy the final name.
        $sarsaTemporary = Join-Path $sarsaDirectory ($Name + '.' + [Guid]::NewGuid().ToString('N') + '.pending')
        $sarsaFile = [IO.File]::Open($sarsaTemporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $sarsaFile.Write($sarsaCipher,0,$sarsaCipher.Length); $sarsaFile.Flush($true) }
        finally { $sarsaFile.Dispose() }
        $sarsaRestored = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($sarsaTemporary),(Get-SarsaEntropy $Name),$sarsaScope)
        if ([Convert]::ToBase64String($sarsaRestored) -cne [Convert]::ToBase64String($sarsaBytes)) { throw 'readback_failed' }
        # Move refuses replacement if another capture won the race.
        [IO.File]::Move($sarsaTemporary,$sarsaDestination)
        Write-Output ('Protected copy saved and verified for ' + $Name + '. No provider value changed.')
        exit 0
    }
    Write-Output 'Reader expired without capturing a valid new clipboard value. No setting saved.'
    exit 3
}
catch {
    # Never return the original exception: it may carry a path or clipboard data.
    $sarsaFailure = 'local_capture_error'
    if ($_.Exception.Message -cin @('invalid_key','duplicate_key','round_trip_failed','name_binding_failed','invalid_format_accepted','existing_copy_invalid','readback_failed')) {
        $sarsaFailure = $_.Exception.Message
    }
    Write-Output ('Private key handoff failed safely: ' + $sarsaFailure + '. No provider setting changed.')
    exit 1
}
finally {
    if ($sarsaTemporary -and (Test-Path -LiteralPath $sarsaTemporary)) {
        Remove-Item -LiteralPath $sarsaTemporary -Force -ErrorAction SilentlyContinue
    }
    if ($sarsaBytes) { [Array]::Clear($sarsaBytes,0,$sarsaBytes.Length) }
    if ($sarsaRestored) { [Array]::Clear($sarsaRestored,0,$sarsaRestored.Length) }
    $sarsaValue = $null
}
