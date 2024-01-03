import yaml
import typing
from activate.utils.exceptions import ConfigError
from activate.utils.registry import Registry

def reader(stream: typing.IO) -> dict:
    """
    Accepts a file like object, returns a dict
    """
    try:
        return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ConfigError("Unable to read config steam or file")


class Config:
    def __init__(self, config: dict):
        self.config = config
        self.registry = Registry(**config['registry'])

    @classmethod
    def prepare_from_filename(cls, filename: str):
        with open(filename, "r") as stream:
            return cls.prepare_from_stream(stream)

    @classmethod
    def prepare_from_stream(cls, filelike: typing.IO):
        config = cls(reader(filelike))

        if config.config["connector"]["type"] == "database":
            db_url = config.config["connector"]["options"]["database_url"]
            if "sqlite" in db_url and "{config_dir}" in db_url:
                # This is a hack for relative SQLite URIs
                import os

                path = os.path.dirname(os.path.abspath(filelike.name))
                # import pdb; pdb.set_trace()
                config.config["connector"]["options"]["database_url"] = db_url.replace(
                    "{config_dir}", path
                )

        return config
