# Sarsa live payment handoff

The owner identified Sarsa's merchant as `ThvGDrQ1FuyLI8`. This tool prepares the two settings accepted by the existing backend; it does not create keys, rotate an existing key, change Razorpay/Vercel, open intake, or charge a customer. The installed Razorpay connector exposes read-only transaction tools and does not establish which merchant it belongs to.

In the Razorpay partner dashboard select this exact Sarsa client, then **Account & Settings → API Keys**. Use its Live Mode keys; the Key ID must start with `rzp_live_`. Save the Key ID and Key Secret in a password manager. If keys already exist, use the saved secret rather than regenerating them. Never paste a secret into chat.

Run in Windows PowerShell:

```powershell
$SarsaPaymentHelper = 'D:\coding\business\neuraflow-website-factory\03-client-projects\004-sarsa-jyotish-sansthan\tools\payments\setup-live.ps1'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SarsaPaymentHelper -Action Initialize
```

It asks you to confirm the merchant ID, then hides the two key inputs. It creates an independent random webhook signing secret and stores only Windows-user/merchant-bound encrypted bytes in the ignored `private/sarsa-live.dpapi`. Existing copies cannot be overwritten. The copied value is the entire `SARSA_RAZORPAY_ACCOUNTS` JSON, ready for Sarsa's Vercel **Production** sensitive setting. Save a recovery copy in your password manager before replacing the clipboard. This Windows-bound file alone is not a portable backup.

Subsequent actions copy the existing setting without rotation or display:

| Action | Clipboard contents | Destination |
| --- | --- | --- |
| `CopyAccounts` | Account/version JSON | Vercel `SARSA_RAZORPAY_ACCOUNTS` |
| `CopyWebhookSetting` | Merchant/signing-secret JSON | Vercel `SARSA_RAZORPAY_WEBHOOK` |
| `CopyWebhookSecret` | Same raw signing secret | Razorpay's Live webhook Secret field |
| `VerifyOnly` | Nothing | Synthetic format/encryption checks only |

Use the same helper command with `-Action CopyWebhookSetting` or `-Action CopyWebhookSecret`. Never put the API Key Secret in the webhook Secret field. The callback URL is `https://www.sarsajyotishsansthan.com/api/webhooks/razorpay`; select `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, and `refund.processed`. Preserve other clients' webhooks. Confirm the selected dashboard and webhook are in Live Mode.

This setup pins credential version `sarsa-live-20260930`. Database merchant/mode/version configuration must agree before payment admission. Keep automatic capture enabled as required by the final payment flow. A browser checkout success is not appointment confirmation: the backend checks the actual captured payment and its order, amount, currency, account and refund state. The owner-selected merchant label is an attestation, not cryptographic proof that the API keys belong to it; signed merchant-bound events and controlled live acceptance remain necessary.

After saving the two Production settings, deploy the existing Sarsa project from `main` to apply them. Hosted routes, authenticated callbacks, capture, safe retry/duplicate handling, confirmation, Google Meet, both record copies and delivery need actual acceptance before claiming the whole payment service works. No payment, refund, provider configuration or intake activation occurs during the helper's checks.

The helper's synthetic JSON was checked with the production Python account/webhook parsers, Windows encryption/readback, wrong-merchant rejection and wrong encryption binding. `VerifyOnly` touches neither clipboard nor files. The private directory is Git-ignored and excluded from the Vercel function bundle. No real payment setting has yet been captured at this checkpoint.

Source: [Razorpay's official API-key guide](https://raw.githubusercontent.com/razorpay/markdown-docs/master/payments/dashboard/account-settings/api-keys.md).
