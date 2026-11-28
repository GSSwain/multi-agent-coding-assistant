# Secure Key Setup Guide for MACA

This guide documents how to acquire your **Google Gemini** and **Anthropic Claude** API keys and configure them securely across **Linux**, **Windows**, and **macOS** so that the Multi-Agent Coding Assistant (MACA) can access them without storing raw secrets in plain-text configuration files.

---

## 1. Acquiring API Keys

### A. Google Gemini API Key
1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click on the **Get API key** button in the sidebar.
4. Click **Create API key** (select a Google Cloud project or create a new one).
5. Copy your generated key.

### B. Anthropic Claude API Key
1. Visit the [Anthropic Console](https://console.anthropic.com/).
2. Sign in with your account.
3. Navigate to **API Keys**.
4. Click **Create Key**, name it, and copy the generated key.

---

## 2. Linux Setup

### Option A: Secure Storage via `secret-tool` (libsecret / GNOME Keyring) (Recommended)
Storing credentials in your system keyring avoids placing raw API keys in `~/.bashrc` or `~/.zshrc`.

1. Ensure `secret-tool` is installed (for example, `sudo apt install libsecret-tools` on Debian/Ubuntu or `sudo dnf install libsecret` on Fedora).
2. Store your keys in the keyring (you will be prompted to enter each secret safely):
   ```bash
   secret-tool store --label="MACA Gemini API Key" service maca key GEMINI_API_KEY
   secret-tool store --label="MACA Claude API Key" service maca key CLAUDE_API_KEY
   ```
3. Load the secrets automatically in your shell startup file (`~/.bashrc` or `~/.zshrc`):
   ```bash
   cat <<'EOF' >> ~/.bashrc
   export GEMINI_API_KEY="$(secret-tool lookup service maca key GEMINI_API_KEY 2>/dev/null)"
   export CLAUDE_API_KEY="$(secret-tool lookup service maca key CLAUDE_API_KEY 2>/dev/null)"
   EOF
   source ~/.bashrc
   ```
   *(If you use zsh, replace `~/.bashrc` with `~/.zshrc`.)*

### Option B: Standard Environment Variables
For quick testing or headless/CI environments without a desktop keyring:
```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
export CLAUDE_API_KEY="YOUR_CLAUDE_API_KEY"
```

---

## 3. Windows (PowerShell) Setup

### Option A: Temporary Session Environment Variables
Set keys for the current PowerShell session only (cleared when the terminal closes):
```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
$env:CLAUDE_API_KEY="YOUR_CLAUDE_API_KEY"
```

### Option B: Persistent User Environment Variables
Persist keys in your Windows user environment so they are available in all new terminals:
```powershell
# Using .NET Environment API
[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY", "User")
[Environment]::SetEnvironmentVariable("CLAUDE_API_KEY", "YOUR_CLAUDE_API_KEY", "User")

# Or using setx
setx GEMINI_API_KEY "YOUR_GEMINI_API_KEY"
setx CLAUDE_API_KEY "YOUR_CLAUDE_API_KEY"
```
Restart your terminal for persistent user environment changes to take effect.

### Option C: Secure Storage via Windows Credential Manager + PowerShell Profile (Recommended)
Store secrets encrypted in Windows Credential Manager using the `CredentialManager` PowerShell module and load them into your session from `$PROFILE`:

1. Install the `CredentialManager` module for your user account:
   ```powershell
   Install-Module -Name CredentialManager -Scope CurrentUser
   ```
2. Store your API keys (use your username or `maca` as `-UserName`, and your API key as the password when prompted or via `-Password`):
   ```powershell
   New-StoredCredential -Target "GEMINI_API_KEY" -UserName "$env:USERNAME" -Password "YOUR_GEMINI_API_KEY" -Persist LocalMachine
   New-StoredCredential -Target "CLAUDE_API_KEY" -UserName "$env:USERNAME" -Password "YOUR_CLAUDE_API_KEY" -Persist LocalMachine
   ```
3. Load the credentials in your PowerShell profile (`$PROFILE`):
   ```powershell
   if (!(Test-Path -Path $PROFILE)) {
       New-Item -ItemType File -Path $PROFILE -Force | Out-Null
   }
   Add-Content -Path $PROFILE -Value @'
   $geminiCred = Get-StoredCredential -Target "GEMINI_API_KEY"
   if ($geminiCred) { $env:GEMINI_API_KEY = $geminiCred.GetNetworkCredential().Password }
   $claudeCred = Get-StoredCredential -Target "CLAUDE_API_KEY"
   if ($claudeCred) { $env:CLAUDE_API_KEY = $claudeCred.GetNetworkCredential().Password }
   '@
   . $PROFILE
   ```

---

## 4. macOS Keychain Setup

Exposing keys in plain text in files like `~/.zshrc` or `~/.bash_profile` can compromise your credentials. Storing them in the macOS Keychain keeps them encrypted.

### A. Store Gemini API Key
Open your terminal and run the following command (replace `YOUR_GEMINI_API_KEY` with your actual key):
```bash
security add-generic-password -a "$USER" -s "GEMINI_API_KEY" -w "YOUR_GEMINI_API_KEY"
```

### B. Store Claude API Key
Open your terminal and run the following command (replace `YOUR_CLAUDE_API_KEY` with your actual key):
```bash
security add-generic-password -a "$USER" -s "CLAUDE_API_KEY" -w "YOUR_CLAUDE_API_KEY"
```

### C. Add the Keychain Secrets to `~/.zshenv`
To make the secrets available automatically in every new zsh session, add these lines to your shell startup file:

```bash
printf "%s\n" "export GEMINI_API_KEY=\"\$(security find-generic-password -a \"\$USER\" -s \"GEMINI_API_KEY\" -w 2>/dev/null)\"" >> ~/.zshenv
printf "%s\n" "export CLAUDE_API_KEY=\"\$(security find-generic-password -a \"\$USER\" -s \"CLAUDE_API_KEY\" -w 2>/dev/null)\"" >> ~/.zshenv
source ~/.zshenv
```

This uses the Keychain values for `GEMINI_API_KEY` and `CLAUDE_API_KEY` without storing the raw secrets in `.zshrc` or other shell config files.

---

## 5. Verifying Key Storage & Environment

### Linux
Verify keyring lookup and exported environment variables:
```bash
secret-tool lookup service maca key GEMINI_API_KEY
secret-tool lookup service maca key CLAUDE_API_KEY

# Check active shell environment (prints length without exposing the full key)
echo "GEMINI_API_KEY length: ${#GEMINI_API_KEY}"
echo "CLAUDE_API_KEY length: ${#CLAUDE_API_KEY}"
```

### Windows (PowerShell)
Verify Credential Manager entries and active environment variables:
```powershell
# If using CredentialManager
(Get-StoredCredential -Target "GEMINI_API_KEY") -ne $null
(Get-StoredCredential -Target "CLAUDE_API_KEY") -ne $null

# Check active shell environment
"GEMINI_API_KEY length: $($env:GEMINI_API_KEY.Length)"
"CLAUDE_API_KEY length: $($env:CLAUDE_API_KEY.Length)"
```

### macOS
Verify macOS Keychain entries:
```bash
security find-generic-password -a "$USER" -s "GEMINI_API_KEY" -w
security find-generic-password -a "$USER" -s "CLAUDE_API_KEY" -w
```

---

## 6. How MACA Accesses the Keys

Across Linux, Windows, and macOS, MACA reads `GEMINI_API_KEY` and `CLAUDE_API_KEY` directly from the process environment when it starts:
- **Linux**: Export them in `~/.bashrc` or `~/.zshrc` (ideally loaded dynamically via `secret-tool`).
- **Windows**: Set them in your PowerShell session, User environment variables, or load them from Windows Credential Manager via `$PROFILE`.
- **macOS**: Export them from the macOS Keychain in `~/.zshenv` so they are available in every new zsh session.
