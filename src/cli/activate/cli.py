import click
from activate.lib.config import Config
from activate.lib.loaddb import prepare_engine

@click.command()
@click.option("--config", type=click.File("rb"))
def run(config):
    """ Main script """
    configfile = config

    config = Config.prepare_from_stream(configfile)
    if "sqlite" in config.database_url and "{config_dir}" in config.database_url:
        # This is a nasty hack for relative SQLite URIs
        import os
        path = os.path.dirname(os.path.abspath(configfile.name))
        # import pdb; pdb.set_trace()
        config.config['database_url'] = config.database_url.replace("{config_dir}", path)

    engine = prepare_engine(config)
    print("Aristotle Activate found the following tables:")
    print(list(engine.metadata.tables.keys()))



if __name__ == '__main__':
    run()
