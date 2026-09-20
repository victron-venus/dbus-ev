"""Never load device-local credentials or runtime backend choices in unit tests."""

import sys
from types import ModuleType

sys.modules["local_config"] = ModuleType("local_config")
