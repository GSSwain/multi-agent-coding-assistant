# Secure Key Setup Guide for MACA

This guide documents how to acquire your **Google Gemini** and **Anthropic Claude** API keys and store them securely using the **macOS Keychain** so that the Multi-Agent Coding Assistant (MACA) can access them without exposing the secrets in plain text.

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

## 2. Secure Configuration via macOS Keychain

Exposing keys in plain text in files like `~/.zshrc` or `~/.bash_profile` can compromise your credentials. Storing them in the macOS Keychain is highly secure.

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

---

## 3. Add the Keychain Secrets to ~/.zshenv

To make the secrets available automatically in every new zsh session, add these lines to your shell startup file:

```bash
printf "%s\n" "export GEMINI_API_KEY=\"\$(security find-generic-password -a \"\$USER\" -s \"GEMINI_API_KEY\" -w 2>/dev/null)\"" >> ~/.zshenv
printf "%s\n" "export CLAUDE_API_KEY=\"\$(security find-generic-password -a \"\$USER\" -s \"CLAUDE_API_KEY\" -w 2>/dev/null)\"" >> ~/.zshenv
source ~/.zshenv
```

This uses the Keychain values for `GEMINI_API_KEY` and `CLAUDE_API_KEY` without storing the raw secrets in `.zshrc` or other shell config files.

---

## 4. Verifying Keychain Storage

You can verify that the keys were successfully written to your macOS Keychain by retrieving them:

```bash
security find-generic-password -a "$USER" -s "GEMINI_API_KEY" -w
security find-generic-password -a "$USER" -s "CLAUDE_API_KEY" -w
```

---

## 5. How MACA Accesses the Keys

MACA reads `GEMINI_API_KEY` and `CLAUDE_API_KEY` from your shell environment when it starts. The recommended macOS setup is to export those values from your Keychain in `~/.zshenv`, which makes the keys available to the CLI in every new zsh session.
