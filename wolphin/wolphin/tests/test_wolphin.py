from wolphin.project import WolphinProject
from wolphin.tests.mock_boto import connect_to_region

from nose.tools import eq_, ok_
import mock

STATES = {
    'pending': 0,
    'running': 16,
    'shutting-down': 32,
    'stopping': 64,
    'stopped': 80,
    'terminated': 48
}


def mock_config():
    return {
        'PROJECT': 'test_project',
        'EMAIL': 'devnull@locationlabs.com',
        'REGION': 'mock_region',
        'AMI_ID': 'mock_ami',
        'INSTANCE_TYPE': 'mock_type',
        'USER': 'mock_user',
        'INSTANCE_AVAILABILITYZONE': 'mock_zone',
        'INSTANCE_SECURITYGROUP': 'mock_security_group',
        'MIN_INSTANCE_COUNT': 5,
        'MAX_INSTANCE_COUNT': 10,
        'AMAZON_KEYPAIR_NAME': 'mock_keypair_name',
        'AWS_ACCESS_KEY_ID': 'mock_key_id',
        'AWS_SECRET_KEY': 'mock_secret_key',
        'MAX_WAIT_TRIES': 1,
        'MAX_WAIT_DURATION': 1
    }


class TestWolphin(object):
    """Tests for WolphinProject"""

    def setUp(self):
        self.config = mock_config()

        self.project = WolphinProject(config=self.config,
                                      config_validator=mock.Mock(return_value=(True, "")),
                                      connection=connect_to_region(self.config['REGION'],
                                                                   aws_access_key_id=
                                                                   self.config['AWS_ACCESS_KEY_ID'],
                                                                   aws_secret_access_key=
                                                                   self.config['AWS_SECRET_KEY']))

    def _multi_state_setup(self):
        """Sets up an initial project state with instances in valied states"""

        self.project.config['MIN_INSTANCE_COUNT'] = 15
        self.project.config['MAX_INSTANCE_COUNT'] = 15

        self.project.create()
        # working with a mix of states to start with
        instance_ids = self.project.conn.INSTANCES.keys()

        stopping = []
        stopped = []
        shutting_down = []
        terminated = []
        pending = []
        running = []

        for x in range(0, 2):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'stopping'
            self.project.conn.INSTANCES[instance_ids[x]].state_code = STATES['stopping']
            stopping.append(instance_ids[x])
        for x in range(2, 4):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'stopped'
            self.project.conn.INSTANCES[instance_ids[x]].state_code = STATES['stopped']
            stopped.append(instance_ids[x])
        for x in range(4, 6):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'shutting-down'
            self.project.conn.INSTANCES[instance_ids[x]].state_code = STATES['shutting-down']
            shutting_down.append(instance_ids[x])
        for x in range(6, 8):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'terminated'
            self.project.conn.INSTANCES[instance_ids[x]].state_code = STATES['terminated']
            terminated.append(instance_ids[x])
        for x in range(8, 10):
            self.project.conn.INSTANCES[instance_ids[x]].state = 'pending'
            self.project.conn.INSTANCES[instance_ids[x]].state_code = STATES['pending']
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

        instance_count = 0
        for k, v in self.project.conn.INSTANCES.iteritems():
            instance_count += 1 if state == v.state else 0
        eq_(len(base_set) + instance_count_offset, instance_count)
        eq_(self.project.config['MAX_INSTANCE_COUNT'] + instance_count_offset,
            len(self.project.conn.INSTANCES))

    def test_create(self):
        """Test if a project is created successfully"""

        eq_(0, len(self.project.conn.INSTANCES))
        self.project.create()
        ok_(self.config['MIN_INSTANCE_COUNT']
            <= len(self.project.conn.INSTANCES)
            <= self.config['MAX_INSTANCE_COUNT'])
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
                                             self.config['MAX_INSTANCE_COUNT'] - len(base_set))

    def test_start_already_started(self):
        """Test if start works fine with already started instances"""

        self.project.create()
        self.project.start()
        ok_(self.config['MIN_INSTANCE_COUNT']
            <= len(self.project.conn.INSTANCES)
            <= self.config['MAX_INSTANCE_COUNT'])
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
        ok_(self.config['MIN_INSTANCE_COUNT']
            <= len(self.project.conn.INSTANCES)
            <= self.config['MAX_INSTANCE_COUNT'])
        for k, v in self.project.conn.INSTANCES.iteritems():
            eq_('stopped', v.state)

    def _assert_normal_operation_no_instances(self, function, simulate_terminated=False):
        """
        Assert that operation succeeds without side effects
        when there are no instances to work with.
        """

        if simulate_terminated:
            self.project.create()
            self.project.terminate()
        if function == 1:
            self.project.start()
        elif function == 2:
            self.project.stop()
        elif function == 3:
            self.project.terminate()
        elif function == 4:
            self.project.reboot()
        elif function == 5:
            self.project.revert()

        if simulate_terminated:
            ok_(self.config['MIN_INSTANCE_COUNT']
                <= len(self.project.conn.INSTANCES)
                <= self.config['MAX_INSTANCE_COUNT'])
            for k, v in self.project.conn.INSTANCES.iteritems():
                eq_('terminated', v.state)
        else:
            eq_(0, len(self.project.conn.INSTANCES))

    def test_operations_without_creating_project(self):
        """Test operations when there is no instances in existence"""

        simulate_cases = [False, True]

        for simulate in simulate_cases:
            for x in range(5):
                yield (self._assert_normal_operation_no_instances, x, simulate)

    def test_stop(self):
        """Test stop with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.stop()
        self._assert_post_action_multi_state('stopped',
                                             set(stopping) | set(stopped)
                                             | set(pending) | set(running))

    def test_stop_selective(self):
        """Test stopping selected instances"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        instance_ids = [stopping[0], stopped[0], pending[0], running[0]]
        self.project.stop(instance_numbers=self._get_instance_numbers(instance_ids))
        self._assert_post_action_multi_state('stopped', set(instance_ids) | set(stopped))

    def test_terminate(self):
        """Test terminate with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.terminate()
        self._assert_post_action_multi_state('terminated',
                                             set(stopping) | set(stopped)
                                             | set(shutting_down) | set(terminated)
                                             | set(pending) | set(running))

    def test_terminate_selective(self):
        """Test terminating selected instances"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        instance_ids = [stopping[0], stopped[0], pending[0], running[0]]
        self.project.terminate(instance_numbers=self._get_instance_numbers(instance_ids))
        self._assert_post_action_multi_state('terminated', set(instance_ids) | set(terminated))

    def test_reboot(self):
        """Test reboot with multiple already existing instances having varied initial states"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        self.project.reboot()
        self._assert_post_action_multi_state('running',
                                             set(stopping) | set(stopped)
                                             | set(pending) | set(running))

    def test_reboot_selective(self):
        """Test rebooting selected instances"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        instance_ids = [stopping[0], stopped[0], pending[0], running[0]]
        self.project.reboot(instance_numbers=self._get_instance_numbers(instance_ids))
        self._assert_post_action_multi_state('running', set(instance_ids) | set(running))

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

    def test_revert_selective(self):
        """Test reverting selected instances"""

        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()
        instance_ids = [stopping[0], stopped[0], pending[0], running[0]]
        self.project.revert(instance_numbers=self._get_instance_numbers(instance_ids))
        running_count = 0
        terminated_count = 0
        for k, v in self.project.conn.INSTANCES.iteritems():
            if 'running' == v.state:
                running_count += 1
            elif 'terminated' == v.state:
                terminated_count += 1
        eq_(len(instance_ids) + len(running) - 1, running_count)
        non_terminated_ids = set(stopping) | set(stopped) | set(pending) | set(running)
        non_terminated_ids -= set(instance_ids)
        for instance_id in non_terminated_ids:
            ok_('terminated' != self.project.conn.INSTANCES[instance_id].state)
        for instance_id in instance_ids:
            eq_('terminated', self.project.conn.INSTANCES[instance_id].state)

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
                ok_(instance.state not in ['terminated', 'shutting_down'])

    def test_get_healthy_selective_instances(self):
        stopping, stopped, shutting_down, terminated, pending, running = self._multi_state_setup()

        result = self.project.get_healthy_instances(instance_numbers=
                                                    self._get_instance_numbers([
                                                        stopping[0],
                                                        stopped[0],
                                                        pending[0],
                                                        running[0]]))
        ok_(0 < len(result))
        for instance in result:
            ok_(instance.state not in ['terminated', 'shutting_down'])

    def test_get_all_project_instances(self):
        result = self.project.get_all_project_instances()
        instance_ids = self.project.conn.INSTANCES.keys()

        eq_(len(instance_ids), len(result))
        for instance in result:
            ok_(instance.id in instance_ids)

    def test_get_instances(self):
        self.project.create()
        instance_suffix = 1
        result = self.project.get_instances(instance_suffix)
        instance_ids = []
        for k, v in self.project.conn.INSTANCES.iteritems():
            if '1' == v.tags['Name'].split(".")[-1]:
                instance_ids.append(v.id)
        eq_(len(instance_ids), len(result))
        for instance in result:
            ok_(instance.id in instance_ids)

    def _get_instance_numbers(self, instance_ids):
        instance_numbers = []
        for instance_id in instance_ids:
            splits = self.project.conn.INSTANCES[instance_id].tags['Name'].split(".")
            instance_numbers.append(int(splits[-1].split("_")[0]))
        return instance_numbers

    def _assert_wait_for_status(self,
                                instance_count,
                                update_seq,
                                wait_from,
                                wait_till,
                                final_state):
        """Test that  wait_for_status function works as expected"""

        self.project.config['MAX_WAIT_TRIES'] = 4
        self.project.config['MAX_WAIT_DURATION'] = 0
        self.project.config['MIN_INSTANCE_COUNT'] = instance_count
        self.project.config['MAX_INSTANCE_COUNT'] = instance_count
        self.project.create()
        instances = []
        for k, v in self.project.conn.INSTANCES.iteritems():
            v.custom_instance_update_seq = update_seq
            v.state = wait_from
            v.state_code = STATES[wait_from]
            instances.append(v)
        self.project._wait_for_status(instances, STATES[wait_from], STATES[wait_till])
        for instance in instances:
            eq_(final_state, instance.state)
        eq_(len(instances), len(self.project.conn.INSTANCES))

    def test_wait_for_status(self):
        test_cases = [('stopping', ['stopping', 'stopping', 'stopping', 'stopped'], 'stopped'),
                      ('stopping', ['stopping', 'stopped'], 'stopped'),
                      ('stopping', ['stopped', ], 'stopped'),
                      ('stopping', ['stopping', 'stopping', 'stopping', 'stopping', 'stopped'],
                       'stopping')]
        for x in range(1, 3):
            for wait_from, update_seq, final_state in test_cases:
                yield (self._assert_wait_for_status,
                       x,
                       update_seq,
                       wait_from,
                       update_seq[-1],
                       final_state)
