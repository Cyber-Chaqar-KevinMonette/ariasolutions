# Aria Solutions — business email setup (Northwest)

Your mail server settings, saved so you never have to dig for them again.
**No password is stored here** — you type it into the client yourself.

## Quickest access — webmail
Go to **https://mail.ariasolutions.org** → log in with `admin@ariasolutions.org`
+ your mailbox password. Roundcube webmail, no dashboard needed. (Confirmed working
2026-07-18 — inbox reads "empty" because it's brand new.)

## The account
| | |
|---|---|
| **Login username** | `admin@ariasolutions.org` |
| **Password** | the mailbox password you set for this account (never write it here) |
| **Domain** | ariasolutions.org |
| **Host (all servers)** | `mailserver.businessidentity.llc` |

## Server settings (SSL)
| Purpose | Protocol | Host | Port | Security |
|---|---|---|---|---|
| **Receive** (keep on server) | IMAP | `mailserver.businessidentity.llc` | **993** | SSL/TLS |
| **Receive** (download) | POP3 | `mailserver.businessidentity.llc` | **995** | SSL/TLS |
| **Send** | SMTP | `mailserver.businessidentity.llc` | **465** | SSL/TLS |

> Use **IMAP (993)** if you'll read mail on more than one device (phone + laptop).
> Use **POP3 (995)** only if you want Gmail to pull it in (see Option A).

---

## ⚠ First: `admin@` vs `info@`
The mailbox is **admin@ariasolutions.org**. The website + legal pages advertise
**info@ariasolutions.org**. Pick one so customer mail doesn't bounce:
- **Best:** in Northwest → Email settings, add **info@ariasolutions.org** as an
  alias (or a second address) that delivers into this same mailbox. Then both work.
- **Or:** tell me to switch the site + legal pages to **admin@ariasolutions.org**
  (one find-and-replace) and we just use admin@.

---

## Option A — run it all inside Gmail (recommended — one inbox)
You already live in Gmail (mssinternetmarketing@gmail.com), so add the business
address there.

### 1. Receive business mail in Gmail
Gmail → ⚙ **See all settings** → **Accounts and Import** →
**Check mail from other accounts** → **Add a mail account** →
- Email: `admin@ariasolutions.org` → **Next** → *Import emails from my other account (POP3)*
- Username: `admin@ariasolutions.org`
- Password: your mailbox password
- POP Server: `mailserver.businessidentity.llc` · Port: **995**
- ✅ **Always use a secure connection (SSL)** → **Add Account**

### 2. Send *as* the business address
Same **Accounts and Import** page → **Send mail as** → **Add another email address** →
- Name: `Aria Solutions` (or BigKev's Bot Shop) · Email: `admin@ariasolutions.org` → **Next**
- SMTP Server: `mailserver.businessidentity.llc` · Port: **465**
- Username: `admin@ariasolutions.org` · Password: your mailbox password
- ● **Secured connection using SSL** → **Add Account**
- Gmail emails a **confirmation code** to admin@ariasolutions.org — do step 1 first
  (or read it in Northwest webmail), grab the code, paste it in. Done.

Now you read *and* send from the business address without leaving Gmail.

## Option B — a desktop mail app (Thunderbird / Evolution / phone)
Add a new account with the address `admin@ariasolutions.org`, the password, and the
IMAP (993) + SMTP (465) rows from the table above, both **SSL/TLS**. Most apps
autodetect once you give the host `mailserver.businessidentity.llc`.
