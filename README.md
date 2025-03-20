### Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.


#### Initial Setup

was done with these settings

```bash
uv init --name "Template"--no-description --author-from git --bare --app
uv add python-dotenv loguru requests argparse
uv venv
```

when you have uv installed you do not need to run these commands again