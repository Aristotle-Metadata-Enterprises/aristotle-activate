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
    def __init__(self, config: dict, registry_cli):
        self.config = config
        registry_args = config.get('registry', {})
        print(f"{registry_args}")
        print(f"{registry_cli}")
        if registry_cli:
            registry_args.update(registry_cli)
        print(f"{registry_args}")
        self.registry = Registry(**registry_args)
        print(f"{self.registry.pipeline=}")

    @classmethod
    def prepare_from_filename(cls, filename: str):
        with open(filename, "r") as stream:
            return cls.prepare_from_stream(stream)

    @classmethod
    def prepare_from_stream(cls, filelike: typing.IO, registry_cli: dict = {}):
        config = cls(reader(filelike), registry_cli)

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
