import click
import yaml

from activate.lib.config import Config
from activate.lib.scan import Scanner
from activate.lib.loaddb import prepare_engine
from activate.lib.progress import ProgressReporter


@click.command()
@click.option("--config", type=click.File("rb"))
@click.option("-o","--local-metadata-file", type=click.File("w"))
def run(config, local_metadata_file):
    configfile = config
    config = Config.prepare_from_stream(configfile)
    data = activate_metadata(config, configfile.name)

    if local_metadata_file:
        yaml.dump(data, local_metadata_file)
        click.echo(f"Activate scan complete. Results stored in {local_metadata_file.name}")


def get_scanner(configfilename):
    # This method is mostly useful for preparing a config file in a shell
    config = Config.prepare_from_filename(configfilename)
    scanner = Scanner.from_config(config)
    return scanner


def activate_metadata(config, configfilename):
    
    click.echo("Scanning schemas")
    with click.progressbar(label="Scanning:",length=100) as bar:
        scanner = Scanner.from_config(config, progress_callback = ClickProgress(bar))

        data = scanner.scan_datasets()
    
    return data


class ClickProgress(ProgressReporter):
    def __init__(self, bar, verbosity=0):
        super().__init__()
        self.bar = bar
        self.verbosity = verbosity


    def update(self, val: int, label: str=""):
        self.progress = val
        self.bar.pos=0
        self.bar.update(val)
        if label:
            self.bar.label = label

    def add(self, val: int):
        import time
        time.sleep(0.1)
        self.update(min(99,self.progress + val))

    def echo(self, message: str, level: int=0):
        click.echo(message)


if __name__ == '__main__':
    run()
