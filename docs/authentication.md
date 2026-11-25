# Authentication

Logging in, two-factor authentication and GitHub sign-in are handled by
[django-allauth](https://docs.allauth.org/). Signup, email confirmation and
password reset are this project's own views and were left as they were.

| Feature | Handled by |
| --- | --- |
| Login form, the two-factor code step | `allauth.account`, `allauth.mfa` |
| Setting up and turning off two-factor authentication, recovery codes | `allauth.mfa` |
| Sign in with GitHub, connecting GitHub to an account | `allauth.socialaccount` |
| Signup form, email confirmation, password reset, profile | `accounts` (this project) |
| The date two-factor authentication becomes mandatory | `accounts` (this project) |

The aim is that security-sensitive logic lives in allauth. The project code
around it is configuration, templates and the glue described below.

## How allauth is wired in

**URLs.** `accounts/urls.py` routes allauth's views one at a time instead of
including `allauth.urls`. Including everything would also expose allauth's own
signup, password reset and email management pages next to ours. allauth looks
some pages up by its own URL names, so our signup, logout and password reset are
registered a second time under `account_signup`, `account_logout` and
`account_reset_password`.

| URL | Name | Page |
| --- | --- | --- |
| `/accounts/login/` | `login`, `account_login` | Login |
| `/accounts/two-factor/` | `mfa_index` | Two-factor overview |
| `/accounts/two-factor/totp/activate/` | `mfa_activate_totp` | Set up an authenticator app |
| `/accounts/two-factor/authenticate/` | `mfa_authenticate` | Code step when logging in |
| `/accounts/two-factor/recovery-codes/` | `mfa_view_recovery_codes` | Recovery codes |
| `/accounts/reauthenticate/` | `account_reauthenticate` | Password check before a sensitive change |
| `/accounts/social/` | `socialaccount_connections` | Connect or disconnect GitHub |
| `/accounts/social/signup/` | `socialaccount_signup` | Finish signing up with GitHub |
| `/accounts/github/login/` | `github_login` | Start a GitHub sign-in |
| `/accounts/github/login/callback/` | `github_callback` | Where GitHub sends the user back |

**Templates.** allauth's pages are used as they ship. They are restyled in two
places rather than page by page:

- `indymeet/templates/allauth/layouts/base.html` puts every allauth page inside
  the site's `base.html`.
- `indymeet/templates/allauth/elements/` styles the building blocks those
  pages are made of (headings, buttons, forms, panels).

Only the login page (`account/login.html`) is written out in full, to keep the
look it had before. `account/messages/logged_in.txt` is empty so that logging
in doesn't start showing a message.

The "Continue with GitHub" button (`allauth/elements/provider.html`) is a form
that posts straight to GitHub. allauth's confirmation page
(`socialaccount/login.html`) therefore only appears when a GitHub login URL is
opened directly, or after the password check when connecting GitHub from the
profile. The GitHub logo is an inline SVG in
`socialaccount/snippets/provider_icon.html`.

**Adapters** (`accounts/adapters.py`) are allauth's extension points:

- `AccountAdapter.send_mail` applies the same rule as `home.email.send`:
  outside production, only `ALLOWED_EMAILS_FOR_TESTING` receive email.
- `SocialAccountAdapter.get_app` answers 404 instead of an error when GitHub
  credentials aren't configured.

**Email addresses.** `UserProfile.email_confirmed` remains the source of truth.
allauth keeps its own `EmailAddress` table, which it reads to refuse two-factor
setup on an unconfirmed address and to know where it may send a confirmation
code. `mirror_email_confirmation_to_allauth` in `accounts/receivers.py` copies
our value into that table whenever a profile is saved, and migration
`accounts/0022` did the same for existing users. If a user's email is changed
without their profile being saved (for example in an admin), allauth's copy is
out of date until the profile is next saved; security notifications are sent to
the address on the user record regardless.

**Admin logins.** The Wagtail admin (`/admin/login/`) and the Django admin
(`/django-admin/login/`) each have a login form that only checks a password.
`indymeet/urls.py` points both at `AdminLoginRedirectView`, which sends
anonymous visitors to the main login. They no longer accept credentials.

## Two-factor authentication

Users can add a time-based code (TOTP) from an authenticator app. It is
optional unless a deadline is set (see below). Security keys and passkeys are
not enabled; allauth supports them (`MFA_SUPPORTED_TYPES`), so they can be
added later without changing the login flow.

What allauth does, and where to find it in its documentation:

- Setting up shows a QR code and the secret, and asks for a code to confirm.
  Ten single-use recovery codes are generated at the same time.
- Setting up, turning off and replacing recovery codes first ask for the
  password again. Someone who signed up with GitHub and has no password is
  emailed a confirmation code instead.
- Setting up is refused until the email address is confirmed. Otherwise someone
  could register another person's address and lock them out of it for good.
- Logging in becomes two steps: password (or GitHub), then a code. The user is
  not logged in until the code is accepted.
- An authenticator code can't be reused, and repeated wrong passwords or codes
  are rate limited.
- The user is emailed when two-factor authentication is turned on or off, or
  the recovery codes are replaced.

`accounts.two_factor.has_two_factor(user)` is the project's check for "this
user is asked for a code when logging in".

### Routes that must not skip the code step

The login form and GitHub sign-in both go through allauth, which asks for the
code. Anything else that signs a user in has to be handled deliberately:

| Route | How it is handled |
| --- | --- |
| Email confirmation link (`activate_account`) | Confirms the email but does not log in a user who has two-factor authentication. |
| Password reset | Never logs the user in and leaves two-factor authentication in place. |
| Wagtail and Django admin logins | Redirected to the main login, as described above. |

When adding another way to log in, send it through allauth's login (so the
code step applies) and add a test to `accounts/tests/test_two_factor.py`.

### Making it mandatory

Set the `TWO_FACTOR_REQUIRED_FROM` environment variable to a date
(`YYYY-MM-DD`) and restart the app. The date is compared against today's date
in the server's time zone (`TIME_ZONE`). This part is project code, because
allauth has no equivalent.

| When | What users without two-factor authentication experience |
| --- | --- |
| Variable unset | Nothing. It is optional and only mentioned on the profile page. |
| Before the date | A reminder banner on every page with the date and a setup link. It can be dismissed for the browser session. |
| On and after the date | `RequireTwoFactorMiddleware` redirects every request to the setup page until they enrol. |

The requirement applies to everyone, staff included, and also to users who
were already logged in when the date arrived. The pages needed to finish setup
stay reachable: the setup page, the password check, confirming an email
address and logging out (`EXEMPT_VIEW_NAMES` in `accounts/middleware.py`).

A user can still turn two-factor authentication off after the date, which is
how they replace their authenticator app: they are taken straight back to
setup. There are no reminder emails, so announce the date through the usual
channels before setting it. To undo the requirement, unset the variable and
restart.

### Recovering a locked-out account

A user who has lost both their authenticator app and their recovery codes
can't get back in on their own. A superuser resets it:

1. Confirm the request really comes from the account owner.
2. In the Django admin, open **Mfa > Authenticators** and search for the user.
3. Delete their authenticator. Their recovery codes are removed with it.
4. The user logs in with their password alone and sets up two-factor
   authentication again. If it is mandatory, they are taken to setup straight
   away.

Only superusers can see or delete authenticators, the stored secrets are not
displayed, and each deletion is recorded in the admin's history. Between the
reset and the user enrolling again the account is protected by its password
only, so do step 1 properly.

## Signing in with GitHub

Offered only when `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET` are
set. Without them the button, the connections page link and the GitHub URLs are
all absent or answer 404.

- **Existing users** connect GitHub from their profile ("Manage GitHub
  sign-in") and can then log in with it. Connecting or removing GitHub asks for
  the password again and emails the user. Accounts are matched by GitHub's
  numeric user ID, never by email address, so having the same email on GitHub
  does not give access to an existing account.
- **New users** who choose "Continue with GitHub" get a short signup form
  (`accounts.forms.GitHubSignupForm`) pre-filled from GitHub. They must accept
  the Code of Conduct and email consent, as on the regular signup form. There
  is no captcha, because a GitHub account is already required.
- **Email confirmation.** If GitHub reports the email as verified, the account
  starts with a confirmed email. Otherwise the usual confirmation email is
  sent. The email supplied by GitHub can't be edited during signup; it can be
  changed on the profile afterwards.
- **Two-factor authentication** still applies: a user who has it is asked for
  their code after returning from GitHub.
- Accounts created through GitHub have no password. Wherever the site would
  ask for the current password, these users confirm it is them with a code
  sent to their email instead (`accounts.views.lacks_password` switches this
  on). That covers two-factor and GitHub changes, deleting the account, and
  setting a password: "Change password" in the menu leads them to allauth's
  set-password page (`/accounts/password/set/`). The code can only go to a
  confirmed email, so a GitHub user whose email is still unconfirmed has to
  confirm it first; until then those pages return a 403. The password reset
  form also works for them.

### Setting up the GitHub OAuth app

Create one OAuth app per environment at
<https://github.com/settings/developers> (or under the organisation's
settings), with this callback URL:

```
https://<site domain>/accounts/github/login/callback/
```

Then set the app's client ID and secret as `GITHUB_OAUTH_CLIENT_ID` and
`GITHUB_OAUTH_CLIENT_SECRET` in that environment and restart. For local
development use `http://localhost:8000/accounts/github/login/callback/`.

## Settings

| Setting | Value | Why |
| --- | --- | --- |
| `TWO_FACTOR_REQUIRED_FROM` | Unset by default; from the environment variable | The date two-factor authentication becomes mandatory. |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` | Unset by default; from the environment variables | Enable GitHub sign-in. |
| `ACCOUNT_LOGIN_METHODS` | `{"username"}` | Login stays username and password. |
| `ACCOUNT_EMAIL_VERIFICATION` | `"none"` | Email confirmation is ours, not allauth's. |
| `ACCOUNT_SESSION_REMEMBER` | `True` | No "remember me" checkbox; sessions last as long as before. |
| `ACCOUNT_EMAIL_NOTIFICATIONS` | `True` | Email users about security changes. |
| `ACCOUNT_PREVENT_ENUMERATION` | `False` | The signup form already says when an email is taken; GitHub signup does the same. |
| `MFA_TOTP_ISSUER` | `Djangonaut Space`, suffixed with the environment outside production | The label in authenticator apps; keeps staging and production entries apart. |
| `MFA_SUPPORTED_TYPES` | `["totp", "recovery_codes"]` | Authenticator apps only, for now. |
| `SOCIALACCOUNT_AUTO_SIGNUP` | `False` | New GitHub users must go through the signup form. |
| `SOCIALACCOUNT_REAUTHENTICATION_REQUIRED` | `True` | Connecting or removing GitHub needs the password again. |
| `ACCOUNT_RATE_LIMITS` | `False` in tests only | allauth counts attempts in the cache, which outlives a test. |

Rate limiting and the "code already used" check rely on Django's cache. With
the per-process `LocMemCache` configured today, those counters are kept per
worker process, so limits are looser than their nominal values when several
workers run. A shared cache would make them exact.

## Code map

- `accounts/urls.py`: which allauth views are routed.
- `accounts/adapters.py`: allauth adapters.
- `accounts/two_factor.py`: `has_two_factor` and the deadline helpers.
- `accounts/middleware.py`: `RequireTwoFactorMiddleware`.
- `accounts/context_processors.py`: supplies the deadline for the reminder banner in `includes/messages.html`.
- `accounts/receivers.py`: `mirror_email_confirmation_to_allauth`.
- `accounts/forms.py`: `GitHubSignupForm`.
- `accounts/admin.py`: `AuthenticatorAdmin`, for resetting a locked-out user.
- `accounts/views.py`: `AdminLoginRedirectView`, and `ActivateAccountView`'s two-factor check.
- `indymeet/templates/allauth/`, `indymeet/templates/account/` and
  `indymeet/templates/socialaccount/`: templates.
- Tests: `accounts/tests/test_login.py`, `test_two_factor.py`, `test_two_factor_required.py`, `test_authenticator_admin.py`, `test_github_sign_in.py`, `test_email_mirror.py`, and the Playwright test `tests/test_two_factor_flow.py`.
