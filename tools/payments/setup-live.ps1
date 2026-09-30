# Sarsa's owner-selected merchant only. No provider request or live-key rotation.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Initialize','CopyAccounts','CopyWebhookSetting','CopyWebhookSecret','VerifyOnly')]
    [string]$Action
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Security
$sarsaMerchant = 'ThvGDrQ1FuyLI8'
$sarsaVersion = 'sarsa-live-20260930'
$sarsaEntropy = [Text.Encoding]::UTF8.GetBytes('Sarsa Project 004 payment configuration v1/' + $sarsaMerchant)
$sarsaScope = [Security.Cryptography.DataProtectionScope]::CurrentUser
$sarsaDirectory = Join-Path $PSScriptRoot 'private'
$sarsaDestination = Join-Path $sarsaDirectory 'sarsa-live.dpapi'

function Get-SarsaPrivateText([string]$Prompt) {
    # Read-Host hides both inputs. Secrets never enter command arguments or history.
    $sarsaSecure = Read-Host -Prompt $Prompt -AsSecureString
    $sarsaPointer = [IntPtr]::Zero
    try {
        $sarsaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sarsaSecure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($sarsaPointer)
    }
    finally {
        if ($sarsaPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($sarsaPointer) }
        $sarsaSecure.Dispose()
    }
}

function New-SarsaWebhookSecret {
    $sarsaRandom = New-Object byte[] 32
    $sarsaGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $sarsaGenerator.GetBytes($sarsaRandom)
        return [Convert]::ToBase64String($sarsaRandom).Replace('+','-').Replace('/','_')
    }
    finally { $sarsaGenerator.Dispose(); [Array]::Clear($sarsaRandom,0,$sarsaRandom.Length) }
}

function Test-SarsaBundle($Bundle) {
    # Match the production parsers, binding both settings to the same live merchant/version.
    if (($Bundle.PSObject.Properties.Name | Sort-Object) -join ',' -cne 'accounts,webhook') { throw 'invalid_bundle' }
    $sarsaAccounts = $Bundle.accounts
    $sarsaWebhook = $Bundle.webhook
    if (($sarsaAccounts.PSObject.Properties.Name | Sort-Object) -join ',' -cne 'current_version,merchant_id,mode,versions' -or
        ($sarsaWebhook.PSObject.Properties.Name | Sort-Object) -join ',' -cne 'merchant_id,mode,signing_secrets' -or
        $sarsaAccounts.merchant_id -cne $sarsaMerchant -or $sarsaWebhook.merchant_id -cne $sarsaMerchant -or
        $sarsaAccounts.mode -cne 'live' -or $sarsaWebhook.mode -cne 'live' -or
        $sarsaAccounts.current_version -cne $sarsaVersion -or @($sarsaAccounts.versions).Count -ne 1 -or
        @($sarsaWebhook.signing_secrets).Count -ne 1) { throw 'invalid_bundle' }
    $sarsaCredential = $sarsaAccounts.versions[0]
    if (($sarsaCredential.PSObject.Properties.Name | Sort-Object) -join ',' -cne 'key_id,key_secret,version' -or
        $sarsaCredential.version -cne $sarsaVersion -or $sarsaCredential.key_id -cnotmatch '^rzp_live_[A-Za-z0-9]{1,119}$' -or
        $sarsaCredential.key_secret -cnotmatch '^[!-~]{16,256}$' -or
        $sarsaWebhook.signing_secrets[0] -cnotmatch '^[A-Za-z0-9_-]{43}=$' -or
        $sarsaWebhook.signing_secrets[0] -ceq $sarsaCredential.key_secret) { throw 'invalid_bundle' }
    $sarsaDecoded = [Convert]::FromBase64String($sarsaWebhook.signing_secrets[0].Replace('-','+').Replace('_','/'))
    try {
        if ($sarsaDecoded.Length -ne 32 -or
            [Convert]::ToBase64String($sarsaDecoded).Replace('+','-').Replace('/','_') -cne $sarsaWebhook.signing_secrets[0]) { throw 'invalid_bundle' }
    }
    finally { [Array]::Clear($sarsaDecoded,0,$sarsaDecoded.Length) }
}

function New-SarsaBundle([string]$KeyId,[string]$KeySecret,[string]$WebhookSecret) {
    $sarsaJson = @{
        accounts = @{merchant_id=$sarsaMerchant; mode='live'; current_version=$sarsaVersion;
            versions=@(@{version=$sarsaVersion; key_id=$KeyId; key_secret=$KeySecret})}
        webhook = @{merchant_id=$sarsaMerchant; mode='live'; signing_secrets=@($WebhookSecret)}
    } | ConvertTo-Json -Depth 8 -Compress
    $sarsaBundle = ConvertFrom-Json $sarsaJson
    Test-SarsaBundle $sarsaBundle
    return $sarsaBundle
}

try {
    if ($Action -eq 'VerifyOnly') {
        # Synthetic bytes and credentials only; no clipboard, file or provider changes.
        $sarsaSample = [Convert]::ToBase64String([byte[]](0..31)).Replace('+','-').Replace('/','_')
        $sarsaBundle = New-SarsaBundle 'rzp_live_synthetic' 'synthetic-secret-for-checks' $sarsaSample
        foreach ($sarsaBad in @('rzp_test_synthetic','rzp_live_bad key','')) {
            $sarsaRejected = $false
            try { [void](New-SarsaBundle $sarsaBad 'synthetic-secret-for-checks' $sarsaSample) }
            catch { $sarsaRejected = $true }
            if (-not $sarsaRejected) { throw 'invalid_format_accepted' }
        }
        $sarsaBadBundle = ConvertFrom-Json ($sarsaBundle | ConvertTo-Json -Depth 8 -Compress)
        $sarsaBadBundle.webhook.merchant_id = 'anotherSyntheticMerchant'
        $sarsaRejected = $false
        try { Test-SarsaBundle $sarsaBadBundle } catch { $sarsaRejected = $true }
        if (-not $sarsaRejected) { throw 'wrong_merchant_accepted' }
        $sarsaBytes = [Text.Encoding]::UTF8.GetBytes(($sarsaBundle | ConvertTo-Json -Depth 8 -Compress))
        $sarsaCipher = [Security.Cryptography.ProtectedData]::Protect($sarsaBytes,$sarsaEntropy,$sarsaScope)
        $sarsaRestored = [Security.Cryptography.ProtectedData]::Unprotect($sarsaCipher,$sarsaEntropy,$sarsaScope)
        if ([Convert]::ToBase64String($sarsaRestored) -cne [Convert]::ToBase64String($sarsaBytes)) { throw 'readback_failed' }
        $sarsaRejected = $false
        try { [void][Security.Cryptography.ProtectedData]::Unprotect($sarsaCipher,[Text.Encoding]::UTF8.GetBytes('other binding'),$sarsaScope) }
        catch { $sarsaRejected = $true }
        if (-not $sarsaRejected) { throw 'wrong_binding_accepted' }
        Write-Output 'Synthetic settings, live-mode rejection, merchant binding and Windows encryption checks passed. No operational setting created.'
        exit 0
    }

    if ($Action -eq 'Initialize') {
        if (Test-Path -LiteralPath $sarsaDestination) { throw 'existing_copy_retained' }
        Write-Host ('Use only the Sarsa client dashboard showing Merchant ID ' + $sarsaMerchant + '.')
        $sarsaConfirmation = Read-Host -Prompt 'Type that Merchant ID after checking the selected Razorpay client'
        if ($sarsaConfirmation -cne $sarsaMerchant) { throw 'merchant_confirmation_failed' }
        $sarsaKeyId = Get-SarsaPrivateText 'Paste the Sarsa live Key ID (hidden)'
        $sarsaKeySecret = Get-SarsaPrivateText 'Paste the Sarsa live Key Secret (hidden)'
        $sarsaBundle = New-SarsaBundle $sarsaKeyId $sarsaKeySecret (New-SarsaWebhookSecret)
        $sarsaJson = $sarsaBundle | ConvertTo-Json -Depth 8 -Compress
        $sarsaBytes = [Text.Encoding]::UTF8.GetBytes($sarsaJson)
        $sarsaCipher = [Security.Cryptography.ProtectedData]::Protect($sarsaBytes,$sarsaEntropy,$sarsaScope)
        [void][IO.Directory]::CreateDirectory($sarsaDirectory)
        $sarsaTemporary = Join-Path $sarsaDirectory ([Guid]::NewGuid().ToString('N') + '.pending')
        $sarsaFile = [IO.File]::Open($sarsaTemporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $sarsaFile.Write($sarsaCipher,0,$sarsaCipher.Length); $sarsaFile.Flush($true) }
        finally { $sarsaFile.Dispose() }
        $sarsaRestored = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($sarsaTemporary),$sarsaEntropy,$sarsaScope)
        if ([Convert]::ToBase64String($sarsaRestored) -cne [Convert]::ToBase64String($sarsaBytes)) { throw 'readback_failed' }
        [IO.File]::Move($sarsaTemporary,$sarsaDestination)
        Write-Host 'Protected local payment settings saved. No Razorpay or Vercel setting has been changed.'
    }
    else {
        $sarsaBytes = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($sarsaDestination),$sarsaEntropy,$sarsaScope)
        $sarsaBundle = ConvertFrom-Json ([Text.Encoding]::UTF8.GetString($sarsaBytes))
        Test-SarsaBundle $sarsaBundle
    }
    if ($Action -eq 'CopyWebhookSecret') {
        $sarsaClipboard = $sarsaBundle.webhook.signing_secrets[0]
        $sarsaLabel = 'Sarsa Razorpay webhook signing secret'
    }
    elseif ($Action -eq 'CopyWebhookSetting') {
        $sarsaClipboard = $sarsaBundle.webhook | ConvertTo-Json -Depth 8 -Compress
        $sarsaLabel = 'SARSA_RAZORPAY_WEBHOOK'
    }
    else {
        $sarsaClipboard = $sarsaBundle.accounts | ConvertTo-Json -Depth 8 -Compress
        $sarsaLabel = 'SARSA_RAZORPAY_ACCOUNTS'
    }
    Set-Clipboard -Value $sarsaClipboard
    Write-Host ('Copied ' + $sarsaLabel + ' to the Windows clipboard without displaying it.')
    Write-Host 'Save recovery copies in your password manager. Local Windows encryption is not a portable recovery copy.'
}
catch {
    $sarsaFailure = 'local_setup_failed'
    if ($_.Exception.Message -cin @('invalid_bundle','invalid_format_accepted','wrong_merchant_accepted','readback_failed','wrong_binding_accepted','existing_copy_retained','merchant_confirmation_failed')) { $sarsaFailure = $_.Exception.Message }
    Write-Output ('Payment setup stopped safely: ' + $sarsaFailure + '. No provider setting changed; existing protected copies are retained.')
    exit 1
}
finally {
    if ($sarsaTemporary -and (Test-Path -LiteralPath $sarsaTemporary)) { Remove-Item -LiteralPath $sarsaTemporary -Force -ErrorAction SilentlyContinue }
    if ($sarsaBytes) { [Array]::Clear($sarsaBytes,0,$sarsaBytes.Length) }
    if ($sarsaRestored) { [Array]::Clear($sarsaRestored,0,$sarsaRestored.Length) }
    $sarsaKeyId=$null; $sarsaKeySecret=$null; $sarsaJson=$null; $sarsaClipboard=$null; $sarsaBundle=$null
}
