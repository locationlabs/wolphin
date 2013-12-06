Wolphin
=======
A Python library that manages ec2 instances.

[![Build Status](https://travis-ci.org/locationlabs/wolphin.png)](https://travis-ci.org/locationlabs/wolphin)

----
Motivation
----------
Many of our projects use virtual machine instances to generate load for capacity and scalability
tests. We want to make it easier to manage such instances using EC2.

Tests that use JMeter get some of this instance management automatically, but we'd like to make it
easier for other kinds of tests.

Problem/Objective
-----------------
Provide a way to manage ec2 instances under a logical grouping of a project. The system should be
able to also deploy something to and execute some stuff on, the 'project' (all or selected instances
within the project).

Related Work
------------
Boto, a python library for ec2 (and many other services) makes it easier to perform tasks on ec2,
reserve instances, terminate instances and so on. jmeter-ec2 scripts give us further insight into
things that can be done when trying to do anything that involves a bunch of ec2 instances under one
logical group (project).

Solution
--------
Create a wrapper to the Boto python library for talking to ec2, to manage ec2 instances under a
logical grouping called a project, while borrowing some concepts from jmeter-ec2, like tagging the
ec2 instances with some metadata that can be used to reflect this logical grouping and hence for
the management of these instances.

**Enter *Wolphin*.**

*trivia: Wolphin is a hybrid of a Whale and a Dolphin. Its a cousin of Boto, a rare Amazon Dolphin.*

Wolphin, as discussed above, is a python library with some function(s) that would allow for
creating wolphin projects and deploying and executing things on these projects. A wolphin project is
a logical entity grouping a number of ec2 instances under one roof. Each wolphin project can be
configured based on various parameters e.g. base image to use (Amazon Machine Image - AMI), the
region in which to spawn instances, the security group to be used, the security key to use and
so on.

Each wolphin project has a name to it and each ec2 instance has a wolphin instance name. This
information is used to tag the ec2 instances and to manage the logical grouping.

**Example:**

A wolphin project named as ``something`` would have instances logically grouped under it having
names of the format: ``something.<number>*`` , say ``something.1``, ``something.2`` or
``something.1_terminated`` and so on.

The tags created on each ec2 instance would be like this:

``ProjectName: wolphin.something``

``Name: wolphin.something.1``

In this way each project *should* have a unique namespaces as far as tagging metadata used to manage
ec2 instances goes.

Wolphin is stateless, i.e. no state about the project is maintained locally, other than the
configuration files made available to wolphin. All operations are done based on this configuration
information and the metadata with which ec2 instances are tagged.

### Wolphin library:

The following operations can be performed using wolphin:

#### create

Create a wolphin project based on a configuration. This involves
spawning ec2 instances based on the configuration parameters of minimum and maximum number of
required instances, including others, such as AMI, access key id, availability zone, etc.
and taking them to the `running` state.
This operation tries to optimize ec2 instance availability. First any available healthy(not
terminated) instances under the same project are considered and then any extra instances needed
to suffice the min-max range are greedily requested from amazon.
Moreover, if there already exist more than the required maximum number of instances for any project,
any extra will be terminated.

#### start

Start all instances or certain instances(s) under a wolphin project. This means taking them to
the `running` state.

#### stop

Stop all instances or certain instances(s) under a wolphin project. This means taking them to the
`stopped` state.

#### reboot

Reboot all instances or certain instances(s) under a wolphin project.

#### terminate

Terminate all instances or certain instances(s) under a wolphin project. This means taking them to
the `terminated` state and tagging them as terminated in some way.

**Note:** instances once terminated cannot be used again.

#### status

Get the status of the instances in a wolphin project. This returns all the info about the
instance(s) such as public and private dns names, public and private ip addresses, state information
, wolphin related metadata such as Project and Name and so on.

#### revert

Revert the instances of a wolphin project to the original AMI specified in the configurations. This
involves terminating the existing instance(s) and spawning new instances having the same logical
wolphin instance name.

**Note:** Properties other than the wolphin ProjectName and instance Name, such as dns name,
ip address(es) may and most probably will change. The revert operation would return the new status
information or the user should use the status operation to get the updated information.

The revert operation can be done in two ways:

1. Batch: relinquish / terminate instances all at once and then spawn the same number of instances.

2. Sequentially: do it one by one, instance by instance.

The pros and cos of one approach vs the other are that since there is an upper limit on the number
of instances running at any given point in time and potentially there might be several wolphin
projects and other sources even, contending to get some instance up in ec2, relinquishing all in a
batch might end up in a situation where the same number of new instances are not provided by amazon.
Sequentially reverting instance by instance reduces this risk somewhat. On the other hand batch
operation would be much faster. A third approach to revert and spawn every instance in parallel may
also be explored but its not in the works for now.

### wolphin_project generator

Wolphin also provides a generator that can be used to iterate over any **RUNNING** ec2 instances associated with
any project. A typical usage scenario would be to use this generator to execute fabric tasks on various
ec2 instances:

    from fabric.api import run

    from wolphin.project import WolphinProject
    from wolphin.config import Configuration
    from wolphin.generator import wolphin_project


    project = WolphinProject.new(Configuration())

    # create instances under the project.
    project.create()

    # run a fabric task on the project (all its ec2 instances).
    for _ in wolphin_project(project):
        run("uname -a")

    # terminate the project(all its instances).
    project.terminate()


### Selector

All operations **with the exception of create** can also be performed on a single or only selected
 instances under a project than the project as a whole. this can be done using a selector, e.g.:

    from wolphin.project import WolphinProject
    from wolphin.config import Configuration
    from wolphin.selector import InstanceNumberBasedSelector


    project = WolphinProject.new(Configuration())

    # create instances under the project.
    project.create()

    # only select instances numbered 1 and 2 for any operations. For instance,
    # if the name of the project were 'project', this selector will only select
    # instances named 'wolphin.project.2' and 'wolphin.project.1'.
    custom_selector = InstanceNumberBasedSelector(instance_numbers=[1, 2])

    project.stop(selector=custom_selector)

 would only stop instances ``wolphin.project.2`` and ``wolphin.project.1``.

 The ``wolphin_project`` generator can also be used in a similar fashion:

    for _ in wolphin_project(project, selector=custom_selector):
        run("uname -a")

 to do ``run("uname -a")`` on instances ``wolphin.project.2`` and ``wolphin.project.1`` only.


The user is free to define his/her own selector.
This can be done by extending the ``wolphin.selector.Selector`` abstract class and overriding its
 ``select`` function. This new class can then be used with a Wolphin project, e.g.:

    class MySelector(Selector):

        def select(self, instances):
            ....
            ....

    project = WolphinProject.new(....)

    project.revert(selector=MySelector())

### Example Script

An example script, demonstrating the use of wolphin is available  examples/examples.py

----
Caveats
-------
1. Creating security groups, setting inbound traffic permissions and any network management are not
a part of wolphin because the use case of having a bunch of test slaves doesn't necessarily require
incoming traffic or communication across nodes. That could change in the future as our test clients
get more mature.
2. Creating access keys and .pem files is not a part of wolphin for security and other reasons.
These steps must be performed outside of wolphin and the relevant details such as locations and
names of resources e.g. .pem file to use, etc., should be provided as a part of the configuration.
3. As of now, creating the base image (AMI) is also outside of the scope for wolphin.
4. The maximum number of total instances available at any point in time, for any account
 and under a particular region (us-west-1, us-east-1 etc.), is governed by amazon.
 The typical limit per account per region is 20. All wolphin projects in the same region
contribute to the upper limit of the instances available at any point. We may need to either get
this number increased or try a different region when configuring the project.
5. Wolphin is a best effort system, i.e. it will try to take care of all messed up states of
instances in a wolphin project but its not very robust against really crazy scenarios e.g. create
a project with 15 instances, in the middle of it break and terminate 2 of them, then run create
again for 5 instances, break again and then run again for 10. Wolphin will try its best but the
results may not be very consistent. It is advised to  play nice with wolphin.

----
