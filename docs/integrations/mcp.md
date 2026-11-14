# MCP (Model Context Protocol) Integration

An MCP server at `/mcp/team-formation/` lets an AI client do everything the "Form Teams" admin page does: list/filter applicants, compare availability, assign teams, waitlist applicants, and run auto-allocation. It never returns applicant emails or survey answer text — see `home/mcp.py` for the full tool list and what each one does.

## Set up in Claude Code (or another developer tool)

Claude Code sends a pasted bearer token, so you need one first:

1. In the Django admin, go to **MCP bearer tokens → Bearer tokens → Add**, pick your user, and save. The token value is shown once at the top of the page — copy it immediately.
2. Add the server in Claude Code, with the name/URL first and `--header` last (it takes a list, so anything after it gets swallowed):

   ```bash
   claude mcp add djangonaut-space https://djangonaut.space/mcp/team-formation/ \
       --transport http \
       --header "Authorization: Bearer mcp_..."
   ```

   Use `http://localhost:8000/mcp/team-formation/` instead for local development.

You only need admin access to create the token — no shell/server access required, in production or otherwise.

## Set up in ChatGPT or Claude.ai (hosted assistants)

These connect via OAuth instead — no token to create. In the assistant's connector/MCP settings, add:

```
https://djangonaut.space/mcp/team-formation/
```

It will send you through a login and "allow access" page on the site itself; approve it and you're connected.

## Using it

You need the `home.form_team` Django permission, and to be a superuser or an organizer of the specific session you're asking about — the same access the "Form Teams" admin page requires.

Just ask in plain language, e.g.:

- "What sessions can I form teams for?"
- "Show me unassigned applicants for the Fall 2026 session, sorted by score."
- "Would applicant X have enough overlap with Team Alpha's navigators?"
- "Assign applicants X and Y to Team Alpha."
- "Run auto-allocation for this session as a preview first."

For anything involving an applicant's actual written answers, the assistant will give you a link into the admin instead of reading them itself — open that link to review the content yourself.
