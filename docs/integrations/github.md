# GitHub Integration

## Overview

The platform collects pull request and issue statistics for Djangonaut Space sessions through the GitHub Search API (via [PyGithub](https://github.com/PyGithub/PyGithub)). All collection happens against public repositories, so the API token only needs read access to public data.

Reference: `home/services/github_stats.py`

## Configuration

One environment variable must be set:

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | A GitHub personal access token with read-only access to public repositories |

If `GITHUB_TOKEN` is empty, stats collection raises a `ValueError` rather than running.

## Generating the Token

The collector only calls the search endpoint (`GET /search/issues`) against public repositories, which requires no special permissions — every fine-grained token already includes read-only access to all public repos.

1. Go to **Settings › Developer settings › Personal access tokens › Fine-grained tokens**, or open https://github.com/settings/personal-access-tokens directly.
2. Click **Generate new token**.
3. Give it a descriptive name (e.g. `djangonaut-space-stats`) and an expiration.
4. Under **Repository access**, select **Public Repositories (read-only)**.
5. Click **Generate token** and copy the value immediately — GitHub only shows it once.
6. Create a calendar event that reminds you to renew this token three weeks before it expires.

See GitHub's documentation: [Creating a fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).

## Deployment

Set the variable in Dokku:

```bash
dokku config:set <app> GITHUB_TOKEN=github_pat_...
```

For local development, add it to your `.env` file:

```
GITHUB_TOKEN=github_pat_...
```
