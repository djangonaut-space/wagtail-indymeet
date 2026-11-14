# Captain and Navigator Applications

This document covers how captains and navigators (officers) apply, get interviewed and
are notified of results. The Djangonaut flow is in [applications.md](applications.md).

Navigators are selected before Djangonaut applications open. Captains are selected
during team formation. Because the timing is different, each role's results are sent
separately.

## Data model

| Field | Purpose |
|---|---|
| `Survey.role` | `Captain`, `Navigator` or blank. A blank role means a Djangonaut application or a general survey. A session can have at most one survey per role. |
| `UserProfile.passed_captain_interview` | Admin only. Blank = not interviewed, Yes = passed, No = did not pass. |
| `UserProfile.passed_navigator_interview` | Same as above, for navigators. |
| `Session.navigator_results_notifications_sent_at` | When navigator results were last sent. |
| `Session.captain_results_notifications_sent_at` | When captain results were last sent. |

Interview flags live on the profile, not the session, so a volunteer is interviewed
once per role. Someone can be interviewed for both roles.

These fields aren't shown on any user-facing form.

## Flow

1. **Create the role survey.** Copy last session's navigator or captain survey
   (`/django-admin/home/survey/`, "Copy" action). Copies keep their role and are
   detached from the session. Set the copy's session to the upcoming session.
2. **Collect applications.** Volunteers respond to the survey on the site.
3. **Record interviews.** In `/django-admin/accounts/userprofile/`, select the
   interviewed volunteers and use the "Record captain/navigator interview as passed /
   not passed" actions, or edit a profile directly. Filter by the interview columns to
   see who has already been interviewed.
4. **Select officers.** Create a `SessionMembership` with the `Navigator` or `Captain`
   role for each selected volunteer.
5. **Send results.** On the session list (`/django-admin/home/session/`), use
   "Send navigator results" or "Send captain results". The confirmation page lists
   who gets which email.

## Who gets which email

Applicants are users who responded to the session's survey for that role.

| Group | Rule | Template |
|---|---|---|
| Selected | Has a `SessionMembership` for the role | `officer_accepted` |
| Not selected, interviewed | No membership in the session; interview flag for this role is set | `officer_rejected_interviewed` |
| Not selected, not interviewed | No membership in the session; interview flag for this role is blank | `officer_rejected` |

- Only the flag for the role being sent counts. For example, someone interviewed for
  captain who wasn't selected as a navigator gets the not-interviewed navigator email.
- Untick "Send interviewed applicants a separate notification" to send everyone who
  wasn't selected the standard `officer_rejected` email.
- Applicants who hold a *different* role in the session (for example, they applied to
  navigate but were made a captain) get no email.

The officer acceptance email asks people to reply to confirm. The on-site
`accept_membership` flow only handles Djangonaut memberships.

## Duplicate-send guard

Sending a role's results records the time on the session. After that, the confirmation
page shows a warning and requires ticking "Send again anyway" before it queues emails
again. The captain and navigator timestamps are independent of each other and of the
Djangonaut `results_notifications_sent_at`.

## Code

- View: `home/views/session_notifications.py` (`send_officer_results_view`)
- Tasks: `home/tasks/session_notifications.py` (`send_officer_accepted_email`,
  `send_officer_rejected_email`)
- Form: `home/forms.py` (`SendOfficerResultsForm`)
- Templates: `home/templates/admin/send_officer_results.html`,
  `home/templates/email/officer_*`
