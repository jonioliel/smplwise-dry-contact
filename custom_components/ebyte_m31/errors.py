"""Transport and identification errors."""


class M31Error(Exception):
    """Communication or identification failed."""


class ModbusError(M31Error):
    """The controller returned a Modbus exception response."""

    def __init__(self, function: int, code: int) -> None:
        self.function = function
        self.code = code
        super().__init__(f"Modbus function {function:02x}, exception {code:02x}")


class UnsupportedModel(M31Error):
    """The IO layout cannot be determined."""


class ModelRequired(UnsupportedModel):
    """The controller has no usable model register."""
