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
        """Tests for validation of valid and invalid configs"""

        config = Configuration()
        config.email = "a@a.com"

        def _generate_none_value_configs(test_cases, config):
            """Generate config objects making each attribute's value as None"""

            for k, v in config.__dict__.iteritems():
                if v:
                    new_config = copy.deepcopy(config)
                    new_config.__dict__[k] = None
                    test_cases.append(new_config)

        def _generate_invalid_configs_with_malformed_values(test_cases, attribute_arrays):
            """Generates config objects with malformed attribute values"""

            for array in attribute_arrays:
                for k, v in array:
                    new_config = copy.deepcopy(config)
                    new_config.__dict__[k] = v
                    test_cases.append(new_config)

        # used to accumulate invalid configs.
        test_cases = []

        # accumulate configs with some attributes having None values.
        _generate_none_value_configs(test_cases, config)

        # valid config.
        for k in config.__dict__.keys():
            config.__dict__[k] = config.__dict__[k] or "a"

        # test for a valid config.
        yield self._assert_validation, config, True

        malformed_value_array = [[('min_instance_count', 0)],
                                 [('min_instance_count', 0), ('max_instance_count', 0)],
                                 [('min_instance_count', 1), ('max_instance_count', 0)],
                                 [('email', 'a')]]

        # accumulate configs with malformed attribute values.
        _generate_invalid_configs_with_malformed_values(test_cases, malformed_value_array)

        # test for invalid configs.
        for case in test_cases:
            yield self._assert_validation, case, False
            yield self._assert_wolphin_error_raised, case, InvalidWolphinConfiguration

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
