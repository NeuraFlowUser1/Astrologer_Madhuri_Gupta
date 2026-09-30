# Matching existing Sarsa worker keys

The owner keeps the four original values in a password manager. Sarsa's Vercel Production settings already contain those values according to the owner. This helper captures a matching operational copy; it does not create a new key, rotate a setting or deploy a Worker.

`capture-key.ps1 -Name SARSA_GOOGLE_WORKER_KEY -WaitSeconds 900` starts a15-minute reader. Start the reader **before** asking the owner to copy the named saved value. It ignores the earlier clipboard sequence, accepts only a canonical32-byte base64url value, and rejects reuse of another already-captured lane key. Never request values in chat or command arguments.

If that reader expires and the owner has just confirmed copying the exact named key, `-ConfirmedCurrentClipboard -WaitSeconds 1` may privately capture that explicitly confirmed current copy. It changes neither the clipboard nor provider settings. Do not use that option speculatively or for the next key before its copy is confirmed. If the password manager has cleared the clipboard, start another ordinary reader and request one fresh copy.

An ordinary waiting reader ignores values equal to an already captured lane key and continues waiting: clipboard managers can change sequence metadata before replacing an old value. Explicit confirmed-current mode rejects that duplicate immediately. Failures expose only fixed allowlisted categories, never original exception text. A previous generic failed attempt does not establish its cause; verify the current copy before proceeding.

The copy in `private/<setting-name>.dpapi` is encrypted with built-in Windows DPAPI for the current Windows user and bound to the setting name. Only encrypted bytes are written. A unique temporary encrypted file is flushed and readback-verified before a same-directory move that refuses replacement. Interrupted writes therefore cannot occupy the final setting name. Existing copies are decrypted and size-checked before being retained; they are not silently overwritten. Error output is fixed, with no original exception or key data.

The whole private directory is excluded by the client's .gitignore, and Vercel excludes tools from the function bundle. Do not add these files to a release manifest, GitHub, an attachment or another client's resources. The password-manager originals remain the recovery copies; these Windows-bound operational copies are not portable backups. No automatic clipboard modification is performed.

Run `-VerifyOnly` for an in-memory synthetic check of format/canonical encoding, encryption/readback and wrong-name rejection. It does not touch the clipboard, create files or change provider configuration. Actual owner capture is a separate acceptance step. Successfully capturing a value does not prove it matches Vercel; authenticated canonical-host checks must establish that after deployment.

Cloudflare's account identity, existing queue and heartbeat namespace must be rechecked before any deployment. Capture all four independent values, finish the canonical backend connection, then configure the existing dedicated Worker through private process input. Do not publish the scheduled monitor before its service is ready, regenerate values to obtain a second copy, or reuse Project003 credentials.

Source: [Microsoft's built-in Windows encryption behavior](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/convertfrom-securestring?view=powershell-7.5).
