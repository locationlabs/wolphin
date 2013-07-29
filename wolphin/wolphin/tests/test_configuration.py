from nose.tools import raises, eq_, ok_

from wolphin.exceptions import InvalidWolphinConfiguration
from wolphin.config import Configuration
from wolphin.project import WolphinProject


class TestConfiguration(object):
    """Tests for Wolphin Configuration"""

    def _assert_wolphin_error_raised(self, config, exception):
        @raises(exception)
        def _execute(config):
            WolphinProject.new(config)
        _execute(config)

    @property
    def _config(self):
        config = Configuration(email='a@a.com')
        for k, v in config.__dict__.iteritems():
            setattr(config, k, v or "test")
        return config

    def test_config_with_malformed_values(self):

        for data in [dict(min_instance_count='0'),
                     dict(min_instance_count='0', max_instance_count='0'),
                     dict(min_instance_count='1', max_instance_count='0'),
                     dict(email='a')]:
            config = self._config
            for k, v in data.iteritems():
                setattr(config, k, v)
            yield self._assert_wolphin_error_raised, config, InvalidWolphinConfiguration

    def test_config_with_none_values(self):

        def _generate_none_value_configs():
            """Generate config objects making each attribute's value as None"""

            configs = [self._config]
            for k, v in configs[0].__dict__.iteritems():
                if v:
                    new_config = self._config
                    setattr(new_config, k, None)
                    configs.append(new_config)
            return configs

        for config in _generate_none_value_configs():
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
        config.parse_config_file(lines)
        eq_('test_zone', config.zone)
        eq_('test_region', config.region)
        eq_(2, int(config.tries))
        config_dict = config.__dict__.keys()
        ok_('something' not in config_dict)
        ok_(' ' not in config_dict)
