from mock import Mock, patch
from nose.tools import eq_, ok_

from wolphin.project import WolphinProject
from wolphin.config import Configuration
from wolphin.tests.mock_boto import MockEC2Connection, STATES


class TestWolphin(object):
    """Tests for WolphinProject"""

    def setUp(self):

        # a config object with defaults and project name override.
        config = Configuration(project="test_project")
        config.max_wait_duration = 0
        config.validate = Mock()
        with patch('wolphin.project.connect_to_region', Mock(return_value=MockEC2Connection())):
            self.project = WolphinProject.new(config)

    def _multi_state_setup(self):
        """Sets up an initial project state with instances in varied states"""

        self.project.config.min_instance_count = 15
        self.project.config.max_instance_count = 15

        self.project.create()
        # working with a mix of states to start with
        instance_ids = self.project.conn.INSTANCES.keys()

        stopping = []
        stopped = []
        shutting_down = []
        terminated = []
        pending = []
        running = []

        for x in range(2):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'stopping'
            stopping.append(instance_ids[x])
        for x in range(2, 4):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'stopped'
            stopped.append(instance_ids[x])
        for x in range(4, 6):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'shutting-down'
            shutting_down.append(instance_ids[x])
        for x in range(6, 8):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'terminated'
            terminated.append(instance_ids[x])
        for x in range(8, 10):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'pending'
            pending.append(instance_ids[x])
        for x in range(10, 15):
            running.append(instance_ids[x])

        return stopping, stopped, shutting_down, terminated, pending, running

    def _assert_post_action_multi_state(self, state, base_set, instance_count_offset=0):
        """
        Asserts various conditions for the state of the system after some wolphin operation was
        performed, with a multi state initial setup
        """

        for instance_id in base_set:
            eq_(state, self.project.conn.INSTANCES[instance_id].state)
            eq_(STATES[state], self.project.conn.INSTANCES[instance_id].state_code)

        instance_count = len(filter(lambda instance: instance.state == state,
                                    self.project.conn.INSTANCES.itervalues()))
        eq_(len(base_set) + instance_count_offset, instance_count)
        eq_(self.project.config.max_instance_count + instance_count_offset,
            len(self.project.conn.INSTANCES))

    def test_create(self):
        """Test if a project is created successfully"""

        eq_(0, len(self.project.conn.INSTANCES))
        self.project.create()
        ok_(self.project.config.min_instance_count
            <= len(self.project.conn.INSTANCES)
            <= self.project.config.max_instance_count)
        for k, v in self.project.conn.INSTANCES.iteritems():
            eq_('running', v.state)

    def test_create_multi_initial_state(self):
        """Testing create with multiple already existing instances having varied initial states"""

        eq_(0, len(self.project.conn.INSTANCES))
        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()

        self.project.create()

        base_set = set(stopping) | set(stopped) | set(pending) | set(running)
        self._assert_post_action_multi_state('running',
                                             base_set,
                                             instance_count_offset=
                                             self.project.config.max_instance_count - len(base_set))

    def test_start_already_started(self):
        """Test if start works fine with already started instances"""

        self.project.create()
        self.project.start()
        ok_(self.project.config.min_instance_count
            <= len(self.project.conn.INSTANCES)
            <= self.project.config.max_instance_count)
        for k, v in self.project.conn.INSTANCES.iteritems():
            eq_('running', v.state)

    def test_start(self):
        """Test start with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.start()
        self._assert_post_action_multi_state('running',
                                             set(stopping) | set(stopped)
                                             | set(pending) | set(running))

    def test_stop_already_stopped(self):
        """Test if stop works fine with already started instances"""

        self.project.create()
        self.project.stop()
        ok_(self.project.config.min_instance_count
            <= len(self.project.conn.INSTANCES)
            <= self.project.config.max_instance_count)
        for k, v in self.project.conn.INSTANCES.iteritems():
            eq_('stopped', v.state)

    def _assert_normal_operation_no_instances(self, function, simulate_terminated=False):
        """
        Assert that operation succeeds without side effects
        when there are no instances to work with.
        """

        functions = [
            self.project.start,
            self.project.stop,
            self.project.terminate,
            self.project.reboot,
            self.project.revert
        ]

        if simulate_terminated:
            self.project.create()
            self.project.terminate()

        functions[function]()

        if simulate_terminated:
            ok_(self.project.config.min_instance_count
                <= len(self.project.conn.INSTANCES)
                <= self.project.config.max_instance_count)
            for k, v in self.project.conn.INSTANCES.iteritems():
                eq_('terminated', v.state)
        else:
            eq_(0, len(self.project.conn.INSTANCES))

    def test_operations_without_creating_project(self):
        """Test operations when there is no instances in existence"""

        simulate_cases = [False, True]

        for simulate in simulate_cases:
            for function in range(5):
                yield (self._assert_normal_operation_no_instances, function, simulate)

    def test_stop(self):
        """Test stop with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.stop()
        self._assert_post_action_multi_state('stopped',
                                             set(stopping) | set(stopped)
                                             | set(pending) | set(running))

    def test_terminate(self):
        """Test terminate with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.terminate()
        self._assert_post_action_multi_state('terminated',
                                             set(stopping) | set(stopped)
                                             | set(shutting_down) | set(terminated)
                                             | set(pending) | set(running))

    def test_reboot(self):
        """Test reboot with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.reboot()
        self._assert_post_action_multi_state('running',
                                             set(stopping) | set(stopped)
                                             | set(pending) | set(running))

    def test_revert(self):
        """Test revert with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        base_set = set(stopping) | set(stopped) | set(pending) | set(running)

        self.project.revert()

        running_count = 0
        terminated_count = 0
        for k, v in self.project.conn.INSTANCES.iteritems():
            if 'running' == v.state:
                running_count += 1
            elif 'terminated' == v.state:
                terminated_count += 1
        eq_(len(base_set), running_count)
        eq_(len(base_set) + len(set(terminated) | set(shutting_down)), terminated_count)
        eq_(len(self.project.conn.INSTANCES), running_count + terminated_count)

    def test_status(self):
        """Test status """

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        result = self.project.status()
        result_instance_id_dict = dict()
        base_set = (set(stopping) | set(stopped) | set(shutting_down) | set(terminated)
                    | set(pending) | set(running))

        eq_(len(base_set), len(result))

        for instance in result:
            result_instance_id_dict[instance.id] = instance.state
        for k, v in result_instance_id_dict.iteritems():
            eq_(self.project.conn.INSTANCES[k].state, v)

    def test_get_healthy_instances(self):
        for x in range(1):
            if x == 0:
                # simulating multi state initial setup
                self._multi_state_setup()
            else:
                self.project.create()
            result = self.project.get_healthy_instances()
            ok_(0 < len(result))
            for instance in result:
                ok_(instance.state not in ['terminated', 'shutting-down'])

    def test_get_all_instances(self):
        result = self.project.get_all_instances()
        instance_ids = self.project.conn.INSTANCES.keys()

        eq_(len(instance_ids), len(result))
        for instance in result:
            ok_(instance.id in instance_ids)

    def _assert_state_based_instance_selection(self, state_code):
        """Assert that state based instance selection works fine"""
        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        for instance_id in (set(stopping) | set(stopped) | set(shutting_down) | set(terminated)
                            | set(pending) | set(running)):
            self.project.conn.INSTANCES[instance_id].update_disabled = True

        targets = {
            10000: [],  # invalid state_code case
            STATES['running']: running,
            STATES['pending']: pending,
            STATES['stopping']: stopping,
            STATES['stopped']: stopped,
            STATES['shutting-down']: shutting_down,
            STATES['terminated']: terminated
        }
        got_instances = self.project.get_instances_in_states([state_code])
        eq_(len(targets[state_code]), len(got_instances))
        for i in got_instances:
            ok_(i.id in targets[state_code])

    def test_get_instances_in_state(self):
        for state_code in [10000,  # invalid state_code case
                           STATES['running'],
                           STATES['pending'],
                           STATES['stopping'],
                           STATES['stopped'],
                           STATES['shutting-down'],
                           STATES['terminated']]:
            yield self._assert_state_based_instance_selection, state_code

    def _get_instance_numbers(self, instance_ids):
        instance_numbers = []
        for instance_id in instance_ids:
            splits = self.project.conn.INSTANCES[instance_id].tags['Name'].split(".")
            instance_numbers.append(int(splits[-1].split("_")[0]))
        return instance_numbers

    def _assert_wait_for_transition(self,
                                    instance_count,
                                    update_seq,
                                    wait_from,
                                    wait_till,
                                    final_state):
        """Test that the _wait_for_transition function works as expected"""

        self.project.config.max_wait_tries = 4
        self.project.config.max_wait_duration = 0
        self.project.config.min_instance_count = instance_count
        self.project.config.max_instance_count = instance_count
        self.project.create()
        instances = []
        for k, v in self.project.conn.INSTANCES.iteritems():
            v.custom_instance_update_seq = update_seq
            v.custom_instance_update_seq_loc = 0
            v.state = wait_from
            instances.append(v)
        self.project._wait_for_transition(instances, STATES[wait_from], STATES[wait_till])
        for instance in instances:
            eq_(final_state, instance.state)
        eq_(len(instances), len(self.project.conn.INSTANCES))

    def test_wait_for_transition(self):
        test_cases = [('stopping', ['stopping', 'stopping', 'stopping', 'stopped'], 'stopped'),
                      ('stopping', ['stopping', 'stopped'], 'stopped'),
                      ('stopping', ['stopped', ], 'stopped'),
                      ('stopping', ['stopping', 'stopping', 'stopping', 'stopping', 'stopped'],
                       'stopping')]
        for x in range(1, 3):
            for wait_from, update_seq, final_state in test_cases:
                yield (self._assert_wait_for_transition,
                       x,
                       update_seq,
                       wait_from,
                       update_seq[-1],
                       final_state)
