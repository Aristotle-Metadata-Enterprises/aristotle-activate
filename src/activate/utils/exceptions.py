class ActivateConfigError(Exception):
    pass

class MissingSecretArg(Exception):
    def __init__(self, message, arg_name):
        self.arg_name = arg_name
        super().__init__(message)
