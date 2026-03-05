# GitHub App Setup for Tellaro PM

Tellaro PM uses a **GitHub App** for server-to-server operations (listing repos, reading issues, syncing tasks, receiving webhooks). User-attributed actions (creating PRs, commenting as a specific user) are handled by the agent via the user's local `gh` CLI.

## Why a GitHub App?

- **Single installation** on the org — no per-user PATs to manage
- **Fine-grained permissions** — read-only access to repos/issues, write only where needed
- **Higher rate limits** (5,000 requests/hour per installation vs 5,000/hour per user)
- **Webhook delivery** built into the App configuration
- **No user tokens required** for read operations

## Prerequisites

- GitHub organization admin access
- `gh` CLI authenticated (`gh auth status`)
- Backend running locally or deployed

## Step 1: Create the GitHub App

### Option A: Via `gh` CLI (recommended)

```bash
gh api -X POST /orgs/{ORG}/apps \
  --input - <<'EOF'
{
  "name": "Tellaro Project Manager",
  "url": "https://github.com/your-org/tellaro-pm",
  "description": "AI-orchestration-first project management — server integration",
  "default_permissions": {
    "issues": "read",
    "pull_requests": "read",
    "contents": "read",
    "metadata": "read"
  },
  "default_events": ["issues", "pull_request"],
  "public": false
}
EOF
```

### Option B: Via GitHub UI

1. Go to **Organization Settings** > **Developer settings** > **GitHub Apps** > **New GitHub App**
2. Fill in:
   - **Name:** `Tellaro Project Manager`
   - **Homepage URL:** Your Tellaro PM URL
   - **Webhook URL:** `https://your-domain/api/v1/github/webhooks` (or leave blank for now)
   - **Webhook secret:** Generate a random string and save it
3. Set **Permissions**:
   - Repository: Issues → Read, Pull requests → Read, Contents → Read, Metadata → Read
4. Subscribe to **Events**: Issues, Pull request
5. Set **Where can this app be installed?** → Only on this account
6. Click **Create GitHub App**

## Step 2: Generate a Private Key

1. After creating the App, go to the App settings page
2. Scroll to **Private keys** > **Generate a private key**
3. Save the downloaded `.pem` file to a secure location (e.g., `~/.tellaro/github-app.pem`)
4. **Never commit this file to git**

## Step 3: Install the App on Your Organization

1. Go to the App settings page > **Install App** (left sidebar)
2. Click **Install** next to your organization
3. Choose **All repositories** or select specific repos
4. Note the **Installation ID** from the URL after installing:
   `https://github.com/organizations/{ORG}/settings/installations/{INSTALLATION_ID}`

## Step 4: Configure the Backend

Add these to your `backend/.env`:

```env
AUTH_GITHUB_ORG=your-org-name
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/github-app.pem
GITHUB_APP_INSTALLATION_ID=78901234
GITHUB_WEBHOOK_SECRET=your-webhook-secret
```

- **GITHUB_APP_ID**: Found on the App's settings page (the "App ID" field)
- **GITHUB_APP_PRIVATE_KEY_PATH**: Absolute path to the `.pem` file
- **GITHUB_APP_INSTALLATION_ID**: From the installation URL in Step 3
- **GITHUB_WEBHOOK_SECRET**: The secret you configured for webhooks

## Step 5: Verify

Restart the backend and check the status endpoint:

```bash
curl -H "Authorization: Bearer YOUR_JWT" \
  http://localhost:8000/api/v1/github/status
```

Expected response:
```json
{
  "github_app_configured": true,
  "github_app_id": "123456",
  "github_org": "your-org-name",
  "github_app_connected": true
}
```

## How It Works

### Authentication Flow

1. Backend loads the App's private key from disk
2. Generates a short-lived JWT (RS256, 10-minute expiry) signed with the private key
3. Exchanges the JWT for an installation access token via GitHub API
4. Uses the installation token for all API calls (token cached, refreshed when < 5 min remain)

### What Uses the App Token

| Operation | Auth Method |
|---|---|
| List org repos | GitHub App |
| Read issues | GitHub App |
| Sync issues → tasks | GitHub App |
| Receive webhooks | Webhook signature verification |
| Create PRs as user | Agent via user's `gh` CLI |
| Comment as user | Agent via user's `gh` CLI |

### Fallback

If the GitHub App is not configured, the backend falls back to per-user tokens:
1. `X-GitHub-Token` header (PAT passed by caller)
2. `github_access_token` stored on the user document (from OAuth)

## Troubleshooting

**"GitHub App is not configured"**
- Verify all three settings are set: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `GITHUB_APP_INSTALLATION_ID`

**"Private key not found"**
- Check the path in `GITHUB_APP_PRIVATE_KEY_PATH` is absolute and the file exists

**"Bad credentials" from GitHub**
- The App ID may be wrong. Check it matches the "App ID" on the settings page (not the Client ID)
- The private key may have been regenerated. Download a fresh one

**"Resource not accessible by integration"**
- The App doesn't have the required permissions. Edit the App's permissions in GitHub Settings
- The App may not be installed on the repository's org

**Rate limit errors**
- GitHub App installation tokens get 5,000 requests/hour. Check `X-RateLimit-Remaining` headers
