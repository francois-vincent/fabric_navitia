# Put factorized tests in this repo

import pytest

skipifdev = pytest.mark.skipif(pytest.config.getoption('--dev'), reason='test skipped with --dev option')
