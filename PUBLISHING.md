# Publishing this repository

The intended public repository is `JimmyWangJimmy/open-equity-research`.

With GitHub CLI authenticated:

```bash
gh repo create JimmyWangJimmy/open-equity-research \
  --public \
  --description "Evidence-first, agent-ready U.S. equity research from public SEC filings" \
  --source . \
  --remote origin \
  --push

git push origin v0.1.0
```

Without GitHub CLI, create an empty public repository named
`open-equity-research`, then run:

```bash
git remote add origin git@github.com:JimmyWangJimmy/open-equity-research.git
git push -u origin main
git push origin v0.1.0
```

Suggested topics:

```text
equity-research sec-edgar xbrl ai-agents fundamental-analysis valuation python
```

Before publishing, confirm that `oer.toml`, `research/`, credentials, licensed
data, and private research are not staged. They are excluded by `.gitignore`.
