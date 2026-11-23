# Two-factor authentication

Users can protect their account with a time-based one-time code (TOTP) from an
authenticator app, in addition to their password. It is built on
[django-otp](https://django-otp-official.readthedocs.io/).

It is optional by default. Setting `TWO_FACTOR_REQUIRED_FROM` gives everyone,
staff included, a deadline after which it is mandatory.

Security keys and passkeys are not supported yet. django-otp was chosen so
they can be added later without reworking the login flow.

## Data model

There are no models of our own; everything is stored in django-otp's tables.

| Model | Purpose |
| --- | --- |
| `otp_totp.TOTPDevice` | The authenticator app. Holds the shared secret. |
| `otp_static.StaticDevice` / `StaticToken` | The user's single-use recovery codes. |

A user **has two-factor authentication enabled when they own a confirmed
`TOTPDevice`**. `accounts.two_factor.has_two_factor()` is the one place that
encodes this rule; use it rather than querying the models directly.

An *unconfirmed* `TOTPDevice` is a setup in progress. It is created when the
user opens the setup page and only confirmed once they enter a valid code, so an
abandoned setup never affects the account. Its secret is replaced after an hour
(`PENDING_DEVICE_MAX_AGE`).

## User flows

All pages live under `/accounts/two-factor/` and are linked from the "Security"
section of the profile page.

| URL name | What it does |
| --- | --- |
| `two_factor` | Overview: current status and links to the actions below. |
| `two_factor_setup` | Shows a QR code and setup key, then confirms the app with a code. Displays the recovery codes once on success. |
| `two_factor_recovery_codes` | Replaces the recovery codes with a new set of 10 and displays them once. |
| `two_factor_disable` | Removes the authenticator app and recovery codes. |
| `two_factor_recover` | Resets two-factor authentication from an emailed recovery link. See "Recovering a locked-out account". |

Safeguards that apply to every change:

- **Password re-entry.** Enabling, disabling and regenerating codes all require
  the current password, so an unattended logged-in session can't be used to
  change them.
- **Notification email.** The `two_factor_changed` email is sent to the user
  after each change, telling them what to do if it wasn't them.
- **Throttling.** django-otp enforces an exponentially growing delay after each
  incorrect code (1s, 2s, 4s, ...).
- **No caching.** Pages that show the secret or recovery codes are served with
  `Cache-Control: no-store`.

## Logging in

Login is two steps for users with two-factor authentication, and unchanged for
everyone else.

1. **Password** (`login`, `TwoFactorLoginView`). If the user has two-factor
   authentication, they are *not* logged in. The accepted password is recorded
   in the session as a pending login and they are redirected to step 2.
2. **Code** (`two_factor_verify`, `TwoFactorVerifyView`). The user enters an
   authenticator code or a recovery code. Only then are they logged in and sent
   on to the page they originally asked for.

Details worth knowing:

- The pending login expires after 10 minutes (`PENDING_LOGIN_MAX_AGE`), and is
  discarded if the account is deactivated or loses two-factor authentication
  in the meantime.
- Recovery codes are single-use. Logging in with one shows how many are left.
- An authenticator code can't be replayed within its time window.
- A code is checked against one device only (authenticator *or* recovery codes,
  decided by its shape), and each has its own growing delay after wrong guesses.

### Routes that must not bypass the code step

`TwoFactorLoginView` has to stay the only way to become logged in with a
password. Anything else that signs a user in needs the same treatment:

| Route | How it is handled |
| --- | --- |
| Email activation link (`activate_account`) | Confirms the email but does not log in users who have two-factor authentication. |
| Password reset | Never logs the user in or removes two-factor authentication. |
| Recovery link (`two_factor_recover`) | The one deliberate exception: it logs the user in without a code, but only with a superuser-issued link *and* the password, and only after removing the old devices. |
| Wagtail admin login (`/admin/login/`) and Django admin login (`/django-admin/login/`) | Shadowed in `indymeet/urls.py` by `AdminLoginRedirectView`, which redirects to the main login. They no longer accept credentials. |

A signed-in user without admin access who opens an admin URL lands on the main
login with `?switch_account=1`, which shows the form so they can log in as a
different account instead of being redirected in a loop.

**When adding a new way to log in** (for example social login or magic links),
route it through the code step and add a test to
`accounts/tests/test_two_factor_login.py`.

## Making it mandatory

Set the `TWO_FACTOR_REQUIRED_FROM` environment variable to a date
(`YYYY-MM-DD`) and restart the app. The date is compared against today's date
in the server's time zone (`TIME_ZONE`).

| When | What users without two-factor authentication experience |
| --- | --- |
| Variable unset | Nothing. It is optional and not advertised beyond the profile page. |
| Before the date | A reminder banner on every page with the date and a setup link. It can be dismissed for the browser session. |
| On and after the date | `RequireTwoFactorMiddleware` redirects every request to the setup page until they enrol. Only setup, logout and the background timezone update stay reachable. |

Because the middleware checks every request, the requirement also applies to
users who were already logged in when the date arrived.

Once mandatory, "Turn off" on the overview page becomes "Replace authenticator
app": the old app is removed and the user is taken straight back to setup.

There are no reminder emails. Announce the date through the usual channels
before setting it. To undo the requirement, unset the variable and restart.

## Recovering a locked-out account

A user who has lost both their authenticator app and their recovery codes
cannot recover on their own; a superuser has to start it.

1. Confirm the request really comes from the account owner.
2. In the Django admin, open **Users**, select the user, and run the action
   **Send two-factor recovery email to selected users**. Only superusers see
   this action, and using it is recorded in the user's admin history.
3. The user receives an email with a link that works once and expires after 24
   hours (`RECOVERY_TOKEN_MAX_AGE`).
4. They open the link and enter their password. Their authenticator app and
   recovery codes are removed, they are logged in, and they land on the setup
   page to enrol a new app. They get a confirmation email.

The link alone is not enough: the password is still required, so access to the
user's inbox does not remove the second factor. If the user has also forgotten
their password, they should reset it first with the normal password reset.

When the link is opened, the token is moved into the session and the browser
is redirected to a URL without it (as Django's password reset does), so it
does not stay in the address bar or reach analytics as a page URL.

The link is tied to the authenticator device it was issued for, which is what
makes it single-use: once two-factor authentication is reset, turned off or
set up again, older links stop working.

## Settings

| Setting | Value | Why |
| --- | --- | --- |
| `OTP_TOTP_ISSUER` | `Djangonaut Space`, suffixed with the environment outside production | The label shown in authenticator apps; the suffix keeps staging and production entries apart. |
| `TWO_FACTOR_REQUIRED_FROM` | Unset by default; read from the environment variable of the same name | The date two-factor authentication becomes mandatory. See above. |
| `OTP_ADMIN_HIDE_SENSITIVE_DATA` | `True` | Keeps TOTP secrets and QR codes out of the Django admin. |

## Code map

- `accounts/two_factor.py`: helper functions (the only code that touches django-otp models).
- `accounts/two_factor_views.py`: the settings views, the two login views, `TwoFactorRecoverView` and `AdminLoginRedirectView`.
- `accounts/middleware.py`: `RequireTwoFactorMiddleware`.
- `accounts/context_processors.py`: supplies the deadline for the reminder banner in `includes/messages.html`.
- `accounts/admin.py`: the recovery email action on `CustomUserAdmin`.
- `accounts/forms.py`: `PasswordConfirmationForm`, `TwoFactorSetupForm` and `TwoFactorVerifyForm`.
- `indymeet/templates/registration/two_factor*.html`: page templates.
- `home/templates/email/two_factor_changed/` and `two_factor_recovery/`: emails.
- `accounts/tests/test_two_factor.py`: enrolment tests.
- `accounts/tests/test_two_factor_login.py`: login and bypass tests.
- `accounts/tests/test_two_factor_required.py`: deadline tests.
- `accounts/tests/test_two_factor_recovery.py`: recovery tests.
- `tests/test_two_factor_flow.py`: Playwright test of enrolling and logging in.
