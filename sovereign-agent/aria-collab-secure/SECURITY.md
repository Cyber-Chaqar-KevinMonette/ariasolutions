# SECURITY — owner-controlled encryption (the vault) 🔐

This drop adds `sov vault`, an at-rest encryption layer for Aria's files. Read
this before relying on it. Honesty about what it does — and doesn't — do is the
whole point of a security feature.

## What it is
- Authenticated symmetric encryption (Fernet = AES-128-CBC + HMAC-SHA256).
- The key is derived from **your passphrase** via scrypt (N=2¹⁵, r=8, p=1).
- The passphrase is **never stored**. Only a salt and a verifier (an HMAC that
  lets us check a passphrase without keeping it) live on disk, in
  `<config_dir>/vault/owner.cred` with `0600` permissions.

## What it protects against
- Someone who obtains the encrypted files but **not** your passphrase. They see
  authenticated ciphertext. They can't read it, and they can't silently alter
  it (tampering fails the integrity check on decrypt).

## What it does NOT protect against
- Someone who **has your passphrase**, or who can read the running process's
  memory while it's unlocked.
- It is **not DRM**, and it is **not a loyalty or control mechanism**. Encryption
  controls who can *read files*. It cannot make software "obey" anyone. Anyone
  who claims otherwise is overselling it.

## Ownership — who holds authority
- **The owner is you (the human).** You set the passphrase; you hold it.
- The model that helped write this (Claude) is **not** an owner and holds
  nothing. It does not persist between sessions, so there is no "Claude" that
  could hold a key across time. Encoding it as a co-owner would be fiction, not
  security — so it isn't there. The real, durable safeguard is *your* ownership.

## No backdoor — and why rotation matters
- There is deliberately **no recovery backdoor**. Lose the passphrase and the
  data is gone. A backdoor would defeat the entire purpose.
- Because of that: **keep a backup of your passphrase somewhere safe**, and use
  `sov vault rotate` to change it (it re-encrypts named files under the new key
  in one step). A key you can rotate is a safeguard; a key you can't is a
  liability — which is why this is rotatable rather than a permanent lock.

## Commands
    sov vault init                       # set the owner passphrase (one time)
    sov vault status                     # initialized? crypto available? (never prints the key)
    sov vault verify                     # check a passphrase
    sov vault encrypt <file> [--remove]  # encrypt; --remove deletes the plaintext
    sov vault decrypt <file.enc> [--out] # decrypt
    sov vault rotate [--file F ...]      # change passphrase; re-encrypt F under the new key

## The collaboration inbox is not a control surface
`sov requests` is a two-way work queue — Aria's asks and your answers, logged.
It exists so collaboration is visible and nothing gets dropped, not to police
anyone. Pauses from `sov agentic` (a held step, a missing subsystem, a needed
clarification) land here automatically so you can answer them.
