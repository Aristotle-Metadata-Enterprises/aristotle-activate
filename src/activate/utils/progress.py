class ProgressReporter:
    def __init__(self):
        self.progress = 0

    def update(self, val: int, label: str = ""):
        raise NotImplemented

    def add(self, val: int):
        raise NotImplemented

    def finish(self):
        self.update(100)

    def echo(self, message: str, level: int = 0):
        raise NotImplemented


class NullProgressReporter(ProgressReporter):
    def update(self, val: int, label: str = ""):
        pass

    def add(self, val: int):
        pass

    def __bool__(self):
        return False

    def echo(self, message: str, level: int = 0):
        pass
