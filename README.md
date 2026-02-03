# aristotle-activate

## Requirement
1. [Python 3.12+](https://www.python.org/downloads/)
2. [uv](https://docs.astral.sh/uv/getting-started/installation/#pypi)

## Development
> [!CAUTION]
> Don't blindly run command without knowing anything about what it does. Perform at your own risk!

To get the developement environement up and ready, execute the following commands:
```bash
# Check if you have multiple Python version on your machine first
ls "/usr/bin/" | grep -i "python"

# `-p` option is mandatory as not all required libraries support Python 3.14 yet
uv run -p "3.12" src/main.py

#
# You'll likely to see a test message here, which confirmed that our previous
# command run successfully
#

# Activate the isolated environment first
source ./.venv/bin/activate

### ONLY DO THIS IF YOU'VE MULTIPLE PYTHON VERSION ON YOUR MACHINE ###
uv run -m ensurepip
uv run -m pip install --upgrade pip

# Otherwise, skip those steps and compile the code to get the CLI binary
# executable file
uv run -m pip install -e .

# Now, we can run the CLI
uv run activateme --help
```

This comes with a few sample sqlite files and configurations for testing. For example:
```bash
# Make sure to activate the isolated environment first
source ./.venv/bin/activate

# Run the sample file
uv run activateme --config "./samples/alchemy/chinook/chinook.sqllite.yaml" -S
```
