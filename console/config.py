import json
import settings


class Option:
    def __init__(self, type=None, min_value=None, max_value=None, choices=None, default=None):
        self.type = type
        self.min_value = min_value
        self.max_value = max_value
        self.default = default
        self.choices = choices

    def validate(self, value):
        if self.type and not isinstance(value, self.type):
            raise ValueError("Invalid option value, %r expected" % self.type)
        if self.min_value is not None and value < self.min_value:
            raise ValueError("Invalid option value, must be >= %r" % self.min_value)
        if self.max_value is not None and value > self.max_value:
            raise ValueError("Invalid option value, must be <= %r" % self.min_value)
        if self.choices is not None and value not in self.choices:
            raise ValueError("Invalid option value, must be one of [%s]" % ", ".join(str(x) for x in self.choices))
        return value


class Config:
    def __init__(self, filename):
        self.filename = filename
        self._data = {}
        self._options = {}
        self._load()

    def add_option(self, name, **kwargs):
        self._options[name] = Option(**kwargs)

    def get(self, name):
        default = self._options[name].default if name in self._options else None
        return self._data.get(name, default)

    def set(self, name, value):
        if name in self._options:
            value = self._options[name].validate(value)
        else:
            raise KeyError("Unknown option")
        self._data[name] = value
        self._dump()

    def _load(self):
        try:
            with open(self.filename, "r") as f:
                self._data = json.loads(f.read())
        except Exception:
            self._data = {}

    def _dump(self):
        with open(self.filename, "w") as f:
            f.write(json.dumps(self._data))


config = Config(settings.CONFIG_FILE)
