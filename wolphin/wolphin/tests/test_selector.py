from nose.tools import eq_, ok_

from wolphin.tests.mock_boto import Instance
from wolphin.selector import InstanceNumberBasedSelector


class TestInstanceNumberBasedSelector(object):

    def setUp(self):

        self.instances = [Instance("tst", "tst", ["tst"], "tst", "tst") for _ in range(10)]
        tag_number = 1
        for instance in self.instances:
            instance.tags['Name'] = "test.{}".format(tag_number)
            tag_number += 1

    def _assert_instance_number_based_selector_works(self, instance_numbers):

        selector = InstanceNumberBasedSelector(instance_numbers=instance_numbers)
        selected_instances = selector.select(self.instances)
        eq_(len(instance_numbers), len(selected_instances))
        for instance in selected_instances:
            ok_(int(instance.tags['Name'].split(".")[-1].strip()) in instance_numbers)

    def test_number_based_selector(self):
        test_cases = [[1, 4, 7, 8], [1]]
        for test_case in test_cases:
            yield self._assert_instance_number_based_selector_works, test_case

    def test_number_based_selector_for_corner_cases(self):
        """
        Test if the selector returns:
        - No instances if `instance_numbers` is defined but there is no such instance.
        - All instances if `instance_numbers` is not defined.
        """
        eq_(0, len(InstanceNumberBasedSelector(instance_numbers=[1000]).select(self.instances)))
        eq_(10, len(InstanceNumberBasedSelector(instance_numbers=[]).select(self.instances)))
        eq_(10, len(InstanceNumberBasedSelector().select(self.instances)))
