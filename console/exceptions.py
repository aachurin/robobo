
class ConsoleException(Exception):
    logger = None

    def __init__(self, msg, logger=None):
        super().__init__(msg)
        self.msg = msg
        if logger is not None:
            self.logger = logger
