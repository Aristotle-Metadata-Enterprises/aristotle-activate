# aristotle-activate

Aristotle Activate is a command-line library designed to scan various systems and automatically generate metadata for the Aristotle Metadata Registry. It streamlines the process of discovering and registering metadata from multiple sources, making integration and management more efficient.

# Development

To test:

* cd src
* uv install
* uv run activateme help

This comes with a few sample sqlite files and configurations for testing

* uv run activateme --config ../samples/alchemy/chinook/chinook.sqllite.yaml -S
