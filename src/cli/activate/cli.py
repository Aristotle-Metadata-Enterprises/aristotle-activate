import os
import yaml
import click
import json
import time

from activate.utils.config import Config
from activate.utils.exceptions import ActivateConfigError
from activate.scanners.base import Scanner
from activate.utils.progress import ProgressReporter


@click.command()
@click.option("--config", type=click.File("rb"), required=True, help="Path to an Activate configuration file")
@click.option("-o", "--output-file", type=click.File("w"), help="Path to a file to save generated metadata")
@click.option("-U", "--upload", is_flag=True, show_default=True, default=False, help="Send generated metadata to a configured server")
@click.option("-S", "--show", is_flag=True, show_default=True, default=False, help="Send generated metadata to terminal (STDOUT)")
@click.option("-T", "--api-token", type=click.STRING, help="API Token. This can alternatively be set with the ACTIVATE_API_TOKEN environment variable. This will override a token specified in the configuration file")
@click.option("-R", "--registry_url", type=click.STRING, help="Registry for upload. This will override a registry specified in the configuration file")
@click.option("-P", "--pipeline_uuid", type=click.STRING, help="Pipeline UUID to feed into. This will override a pipeline specified in the configuration file")
@click.option("-O", "--ordered", is_flag=True, show_default=True, default=False, help="Split metadata JSON payload by order hints. Only valid for output file (-o) or show (-S)")
@click.option("--metadata-types", type=click.STRING, default=None, help="Only send the specified metadata types. Comma separated list. If not set all types are sent. Only recommended for resending errored loads.")
def activate_cli(config, output_file, upload, show, api_token, registry_url, pipeline_uuid, ordered, metadata_types):
    configfile = config

    # Change working directory to config file
    # This is mostly necessary for sqllite database files in testing.
    os.chdir(os.path.dirname(config.name))

    registry_details = {}
    if registry_url:
        registry_details['url'] = registry_url

    if api_token:
        registry_details['api_token'] = api_token
    elif env_api_token := os.environ.get("ACTIVATE_API_TOKEN", None):
        registry_details['api_token'] = env_api_token
    else:
        raise click.ClickException("1 API token not provided. Set --api-token or ACTIVATE_API_TOKEN environment variable.")
        
    if pipeline_uuid:
        registry_details['pipeline'] = pipeline_uuid

    try:
        config = Config.prepare_from_stream(config, registry_cli=registry_details)
        scanner = activate_metadata(config, configfile.name)
    except ActivateConfigError as e:
        raise click.ClickException(f"Failed to prepare configuration or scan metadata: {e}")

    if ordered:
        data = scanner.metadata_as_ordered_dict()
    else:
        data = scanner.metadata_as_dict()

    if output_file:
        # yaml.dump(data, output_file)
        json.dump(data,  output_file, indent=4)
        click.echo(
            f"Activate scan complete. Results stored in {output_file.name}"
        )
    if show:
        click.echo("Printing to STDOUT")
        click.echo(json.dumps(data, indent=4))
    if upload:
        click.echo(f"Sending results to {config.config['registry']['url']}")
        click.echo(f"Waiting 3 seconds before sending... press Crtl-C to abort...")
        time.sleep(3)
        if metadata_types:
            metadata_types_to_send = metadata_types.split(",")
        else:
            metadata_types_to_send = None
        for status in config.registry.send_as_chunked_payloads(
            scanner,
            metadata_types_to_send=metadata_types_to_send
        ):
            pipeline, response = status
            # continue

            if response.status_code == 201:
                if pipeline:
                    click.echo(f'The payload has been sent to pipeline {pipeline}')
                else:
                    click.echo('The following item uuids have been activated.')
                    click.echo(json.loads(response.content))
            else:
                click.echo(f'Failed to activate items: \n\n {response.content}')


def get_scanner(configfilename):
    # This method is mostly useful for preparing a config file in a shell
    config = Config.prepare_from_filename(configfilename)
    scanner = Scanner.from_config(config)
    return scanner


def activate_metadata(config, configfilename):
    click.echo("Scanning schemas")
    with click.progressbar(label="Scanning:", length=100) as bar:
        scanner = Scanner.from_config(config, progress_callback=ClickProgress(bar))
        metadata = scanner.scan_metadata()

    return scanner


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
