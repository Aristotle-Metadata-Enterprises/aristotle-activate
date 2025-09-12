import os
import yaml
import click
import json

from activate.utils.config import Config
from activate.scanners.base import Scanner
from activate.utils.progress import ProgressReporter


@click.command()
@click.option("--config", type=click.File("rb"), required=True, help="Path to an Activate configuration file")
@click.option("-o", "--output-file", type=click.File("w"), help="Path to a file to save generated metadata")
@click.option("-U", "--upload", is_flag=True, show_default=True, default=False, help="Send generated metadata to a configured server")
@click.option("-S", "--show", is_flag=True, show_default=True, default=False, help="Send generated metadata to terminal (STDOUT)")
@click.option("-T", "--api-token", type=click.STRING, help="Optional API Token. This will override a token set in the configuration file")
@click.option("-D", "--description", type=click.STRING, default="", help="An optional description to add to the payload")
def activate_cli(config, output_file, upload, show, api_token, description):
    configfile = config

    # Change working directory to config file
    # This is mostly necessary for sqllite database files in testing.
    os.chdir(os.path.dirname(config.name))

    config = Config.prepare_from_stream(config)
    data = activate_metadata(config, configfile.name)

    if output_file:
        yaml.dump(data, output_file)
        click.echo(
            f"Activate scan complete. Results stored in {output_file.name}"
        )
    if show:
        import pprint
        click.echo(json.dumps(data, indent=4))
    if upload:
        click.echo(f"Sending results to {config.config['registry']['url']}")
        pipeline, response = config.registry.send_payload(description, data)

        if response.status_code == 201:
            if pipeline:
                click.echo(f'The payload has been sent to pipeline {pipeline}')
            else:
                click.echo('The following item uuids have been activated.')
                click.echo(json.loads(response.content))
        else:
            click.echo(f'Failed to activate items: {json.loads(response.content)}')


def get_scanner(configfilename):
    # This method is mostly useful for preparing a config file in a shell
    config = Config.prepare_from_filename(configfilename)
    scanner = Scanner.from_config(config)
    return scanner


def activate_metadata(config, configfilename):
    click.echo("Scanning schemas")
    with click.progressbar(label="Scanning:", length=100) as bar:
        scanner = Scanner.from_config(config, progress_callback=ClickProgress(bar))
        data = scanner.scan_datasets()

    return data


class ClickProgress(ProgressReporter):
    def __init__(self, bar, verbosity=0):
        super().__init__()
        self.bar = bar
        self.verbosity = verbosity

    def update(self, val: int, label: str = ""):
        self.progress = val
        self.bar.pos = 0
        self.bar.update(val)
        if label:
            self.bar.label = label

    def add(self, val: int):
        import time

        time.sleep(0.01)
        self.update(min(99, self.progress + val))

    def echo(self, message: str, level: int = 0):
        click.echo(message)


if __name__ == "__main__":
    activate_cli()
