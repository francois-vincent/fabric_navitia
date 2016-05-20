
Integration tests project for https://github.com/CanalTP/fabric_navitia

How to launch (as a fabric_navitia subproject):
- cd tests_integration
- copy navitia packages here
- launch a test set, e.g.
    PYTHONPATH=.. py.test -s test_kraken/test_setup.py [--dev]

How to launch (if a standalone project):
- cd fabric_navitia_testbench
- copy navitia packages here
- launch a test set, e.g.
    PYTHONPATH=path/to/fabric_navitia py.test -s test_kraken/test_setup.py [--dev]

option --dev will skip all tests decorated with @skipifdev.

If you want to rebuild an image, just remove it (docker rmi <image>),
it will be automatically rebuilt when running any test depending on it.


WARNING:
Make sure that file images/keys/unsecure_keys has permissions set to 0600
