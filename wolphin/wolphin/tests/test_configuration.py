import copy

from nose.tools import raises, eq_, ok_

from wolphin.exceptions import InvalidWolphinConfiguration
from wolphin.config import Configuration, parse_property_file
from wolphin.project import WolphinProject


class TestConfiguration(object):
    """Tests for Wolphin Configuration"""

    def _assert_wolphin_error_raised(self, config, exception):
        @raises(exception)
        def _execute(config):
            WolphinProject(config)
        _execute(config)

    def _assert_validation(self, config, validity):
        """Assert that validation is done properly"""

        is_valid, msg = config.validate()
        if ".pem file" not in msg and "could not be found" not in msg:
            # exclude the .pem file exists check.
            print msg
            eq_(validity, is_valid)

    def test_config(self):
        """Tests for validation of a valid config"""

        config = Configuration()
        config.email = "a@a.com"

        # valid config.
        for k in config.__dict__.keys():
            config.__dict__[k] = config.__dict__[k] or "a"

        # test for a valid config.
        yield self._assert_validation, config, True

    def test_config_with_malformed_values(self):

        for array in [[('min_instance_count', 0)],
                     [('min_instance_count', 0), ('max_instance_count', 0)],
                     [('min_instance_count', 1), ('max_instance_count', 0)],
                     [('email', 'a')]]:
            for k, v in array:
                new_config = copy.deepcopy(Configuration())
                new_config.__dict__[k] = v
            yield self._assert_validation, new_config, False
            yield self._assert_wolphin_error_raised, new_config, InvalidWolphinConfiguration

    def test_config_with_none_values(self):

        def _generate_none_value_configs(config):
            """Generate config objects making each attribute's value as None"""

            configs = [config]
            for k, v in config.__dict__.iteritems():
                if v:
                    new_config = copy.deepcopy(config)
                    new_config.__dict__[k] = None
                    configs.append(new_config)
            return configs

        for config in _generate_none_value_configs(Configuration()):
            yield self._assert_validation, config, False
            yield self._assert_wolphin_error_raised, config, InvalidWolphinConfiguration

    def test_parser(self):
        lines = [
            "# zone",                  # comment.
            "zone = 'test_zone'",      # single quotes.
            'region = "test_region"',  # double quotes.
            'tries = 2',               # no quotes.
            ' ',                       # just a blank line.
            ' = ',                     # will be parsed but should not show up in the config.
            '=',                       # the same as above.
            '# something = x'          # commented attribute, must not be in the config.
        ]
        config = Configuration()
        parse_property_file(config, lines)
        eq_('test_zone', config.zone)
        eq_('test_region', config.region)
        eq_(2, int(config.tries))
        config_dict = config.__dict__.keys()
        ok_('something' not in config_dict)
        ok_(' ' not in config_dict)
