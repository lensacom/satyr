from __future__ import absolute_import, division, print_function

import os

import pytest
from satyr.messages import PythonTask
from satyr.proxies.messages import (CommandInfo, ContainerInfo, Cpus, Disk,
                                    DockerInfo, Mem, TaskID, TaskInfo)
from satyr.scheduler import QueueScheduler, Running
from satyr.utils import RemoteException


@pytest.fixture
def command():
    task = TaskInfo(name='test-task',
                    id=TaskID(value='test-task-id'),
                    resources=[Cpus(0.1), Mem(64)],
                    command=CommandInfo(value='echo 100'))
    return task


@pytest.fixture
def docker_command():
    task = TaskInfo(name='test-docker-task',
                    id=TaskID(value='test-docker-task-id'),
                    resources=[Cpus(0.1), Mem(64)],
                    command=CommandInfo(value='echo 100'),
                    container=ContainerInfo(
                        type='DOCKER',
                        docker=DockerInfo(image='alpine')))
    return task


@pytest.fixture
def docker_python():
    task = PythonTask(id=TaskID(value='test-python-task-id'),
                      fn=sum, args=[range(5)],
                      name='test-python-task-name',
                      resources=[Cpus(0.1), Mem(64), Disk(0)])
    return task


def test_command(mocker, command):
    sched = QueueScheduler()
    mocker.spy(sched, 'on_update')

    with Running(sched, name='test-scheduler'):
        sched.submit(command)
        sched.wait()  # block until all tasks finishes

    calls = sched.on_update.call_args_list
    assert len(calls) == 2

    args, kwargs = calls[0]
    assert args[1].task_id.value == 'test-task-id'
    assert args[1].state == 'TASK_RUNNING'

    args, kwargs = calls[1]
    assert args[1].task_id.value == 'test-task-id'
    assert args[1].state == 'TASK_FINISHED'


@pytest.mark.skipif(not os.environ.get('DOCKER_CONTAINERIZER_ENABLED', False),
                    reason='docker containerizer is disabled in ci setup')
def test_docker_command(mocker, docker_command):
    sched = QueueScheduler()
    mocker.spy(sched, 'on_update')

    with Running(sched, name='test-scheduler'):
        sched.submit(docker_command)
        import time
        time.sleep(5)
        sched.wait()  # block until all tasks finishes

    calls = sched.on_update.call_args_list
    assert len(calls) == 2

    args, kwargs = calls[0]
    assert args[1].task_id.value == 'test-docker-task-id'
    assert args[1].state == 'TASK_RUNNING'

    args, kwargs = calls[1]
    assert args[1].task_id.value == 'test-docker-task-id'
    assert args[1].state == 'TASK_FINISHED'


def test_docker_python(mocker, docker_python):
    sched = QueueScheduler()
    mocker.spy(sched, 'on_update')

    with Running(sched, name='test-scheduler'):
        sched.submit(docker_python)
        sched.wait()  # block until all tasks finishes

    calls = sched.on_update.call_args_list
    assert len(calls) == 2

    args, kwargs = calls[0]
    assert args[1].task_id.value == 'test-python-task-id'
    assert args[1].state == 'TASK_RUNNING'

    args, kwargs = calls[1]
    assert args[1].task_id.value == 'test-python-task-id'
    assert args[1].state == 'TASK_FINISHED'


def test_docker_python_exception():
    sched = QueueScheduler()

    def error():
        raise TypeError('Dummy exception on executor side!')

    task = PythonTask(id=TaskID(value='test-python-task-id'),
                      fn=error, name='test-python-task-name',
                      resources=[Cpus(0.1), Mem(64), Disk(0)])

    with Running(sched, name='test-scheduler'):
        sched.submit(task)
        sched.wait()
        assert task.status.has_failed()
        assert isinstance(task.status.exception, RemoteException)
        assert isinstance(task.status.exception, TypeError)


def test_parallel_execution(mocker, docker_python):
    sched = QueueScheduler()
    mocker.spy(sched, 'on_update')

    with Running(sched, name='test-scheduler'):
        tasks = []
        for i in range(3):
            task = PythonTask(id=TaskID(value='test-python-task-{}'.format(i)),
                              fn=sum, args=[[1, 10, i]],
                              name='test-python-task-name',
                              resources=[Cpus(0.1), Mem(64), Disk(0)])
            sched.submit(task)
            tasks.append(task)
        sched.wait()  # block until all tasks finishes

    assert [t.status.data for t in tasks] == [11, 12, 13]


def test_sequential_execution(mocker, docker_python):
    sched = QueueScheduler()
    mocker.spy(sched, 'on_update')

    with Running(sched, name='test-scheduler'):
        tasks = []
        for i in range(3):
            task = PythonTask(id=TaskID(value='test-python-task-{}'.format(i)),
                              fn=sum, args=[[1, 10, i]],
                              name='test-python-task-name',
                              resources=[Cpus(0.1), Mem(64), Disk(0)])
            sched.submit(task)
            tasks.append(task)
            sched.wait()
            assert task.status.data == 11 + i


def test_docker_python_result(mocker, docker_python):
    sched = QueueScheduler()
    with Running(sched, name='test-scheduler'):
        sched.submit(docker_python)
        sched.wait()  # block until all tasks finishes
        assert docker_python.status.data == 10


@pytest.mark.skip
def test_executor_resize(mocker, docker_python):
    sched = QueueScheduler()

    from time import sleep

    task1 = PythonTask(id=TaskID(value='t1'),
                       fn=sleep, args=[60],
                       name='t1',
                       resources=[Cpus(0.1), Mem(64), Disk(0)])
    task2 = PythonTask(id=TaskID(value='t2'),
                       fn=sleep, args=[60],
                       name='t2',
                       resources=[Cpus(0.2), Mem(128), Disk(0)])

    task1.executor.executor_id.value = 'test'
    task2.executor.executor_id.value = 'test'
    task1.executor.resources = [Cpus(0.01), Mem(32)]
    task2.executor.resources = [Cpus(0.01), Mem(32)]

    import logging
    logging.basicConfig(level=logging.DEBUG)
    #logger = logging.getLogger()
    # logger.setLevel(logging.DEBUG)

    with Running(sched, name='test-scheduler'):

        sched.submit(task1)
        sched.submit(task2)
        sched.wait()  # block until all tasks finishes
        #assert docker_python.status.data == 10
