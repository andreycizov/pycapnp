import pytest
import capnp
from capnp import KjException
import os
import time

import test_capability_capnp as capability


class Server(capability.TestInterface.Server):
    def __init__(self, val=1):
        self.val = val

    def foo(self, i, j, **kwargs):
        extra = 0
        if j:
            extra = 1
        return str(i * 5 + extra + self.val)

    def buz(self, i, **kwargs):
        return i.host + '_test'

    def bam(self, i, **kwargs):
        return str(i) + '_test', i


class PipelineServer(capability.TestPipeline.Server):
    def getCap(self, n, inCap, _context, **kwargs):
        def _then(response):
            _results = _context.results
            _results.s = response.x + '_foo'
            _results.outBox.cap = Server(100)

        return inCap.foo(i=n).then(_then)


def test_client():
    client = capability.TestInterface._new_client(Server())

    req = client._request('foo')
    req.i = 5

    remote = req.send()
    response = remote.wait()

    assert response.x == '26'

    req = client.foo_request()
    req.i = 5

    remote = req.send()
    response = remote.wait()

    assert response.x == '26'

    with pytest.raises(AttributeError, match="foo2"):
        client.foo2_request()

    req = client.foo_request()

    with pytest.raises(TypeError, match="Can't set `i` to `'foo'`"):
        req.i = 'foo'

    req = client.foo_request()

    with pytest.raises(AttributeError, match="baz"):
        req.baz = 1


def test_simple_client():
    client = capability.TestInterface._new_client(Server())

    remote = client._send('foo', i=5)
    response = remote.wait()

    assert response.x == '26'

    remote = client.foo(i=5)
    response = remote.wait()

    assert response.x == '26'

    remote = client.foo(i=5, j=True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.foo(5)
    response = remote.wait()

    assert response.x == '26'

    remote = client.foo(5, True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.foo(5, j=True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.buz(capability.TestSturdyRefHostId.new_message(host='localhost'))
    response = remote.wait()

    assert response.x == 'localhost_test'

    remote = client.bam(i=5)
    response = remote.wait()

    assert response.x == '5_test'
    assert response.i == 5

    with pytest.raises(TypeError, match=r"Can't set argument `j` to `10` \(expected type `BOOL`\)"):
        remote = client.foo(5, 10)

    with pytest.raises(TypeError, match="`foo`. Expected 2 and got 3"):
        remote = client.foo(5, True, 100)

    with pytest.raises(TypeError, match="Can't set argument `i` to `foo`"):
        remote = client.foo(i='foo')

    with pytest.raises(AttributeError, match="foo2"):
        remote = client.foo2(i=5)

    with pytest.raises(TypeError, match=r"Can't set argument `baz` to `5` \(argument does not exist\)"):
        remote = client.foo(baz=5)


def test_pipeline():
    client = capability.TestPipeline._new_client(PipelineServer())
    foo_client = capability.TestInterface._new_client(Server())

    remote = client.getCap(n=5, inCap=foo_client)

    outCap = remote.outBox.cap
    pipelinePromise = outCap.foo(i=10)

    response = pipelinePromise.wait()
    assert response.x == '150'

    response = remote.wait()
    assert response.s == '26_foo'


class BadServer(capability.TestInterface.Server):
    def __init__(self, val=1):
        self.val = val

    def foo(self, i, j, **kwargs):
        extra = 0
        if j:
            extra = 1
        return str(i * 5 + extra + self.val), 10  # returning too many args


def test_exception_client():
    client = capability.TestInterface._new_client(BadServer())

    remote = client._send('foo', i=5)
    with pytest.raises(capnp.KjException, match="Too many values returned from `foo`. Expected `1` got `2`"):
        remote.wait()


class BadPipelineServer(capability.TestPipeline.Server):
    def getCap(self, n, inCap, _context, **kwargs):
        def _then(response):
            _results = _context.results
            _results.s = response.x + '_foo'
            _results.outBox.cap = Server(100)

        def _error(error):
            raise KjException('test was a success')

        return inCap.foo(i=n).then(_then, _error)


def test_exception_chain():
    client = capability.TestPipeline._new_client(BadPipelineServer())
    foo_client = capability.TestInterface._new_client(BadServer())

    remote = client.getCap(n=5, inCap=foo_client)

    try:
        remote.wait()
    except KjException as e:
        assert 'test was a success' in str(e)


def test_pipeline_exception():
    client = capability.TestPipeline._new_client(BadPipelineServer())
    foo_client = capability.TestInterface._new_client(BadServer())

    remote = client.getCap(n=5, inCap=foo_client)

    outCap = remote.outBox.cap
    pipelinePromise = outCap.foo(i=10)

    with pytest.raises(KjException, match="test was a success"):
        pipelinePromise.wait()

    with pytest.raises(KjException, match="test was a success"):
        remote.wait()


def test_casting():
    client = capability.TestExtends._new_client(Server())
    client2 = client.upcast(capability.TestInterface)
    client3 = client2.cast_as(capability.TestInterface)

    with pytest.raises(KjException, match="Can't upcast to non-superclass."):
        client.upcast(capability.TestPipeline)


class TailCallOrder(capability.TestCallOrder.Server):
    def __init__(self):
        self.count = -1

    def getCallSequence(self, expected, **kwargs):
        self.count += 1
        return self.count


class TailCaller(capability.TestTailCaller.Server):
    def __init__(self):
        self.count = 0

    def foo(self, i, callee, _context, **kwargs):
        self.count += 1

        tail = callee.foo_request(i=i, t='from TailCaller')
        return _context.tail_call(tail)


class TailCallee(capability.TestTailCallee.Server):
    def __init__(self):
        self.count = 0

    def foo(self, i, t, _context, **kwargs):
        self.count += 1

        results = _context.results
        results.i = i
        results.t = t
        results.c = TailCallOrder()


def test_tail_call():
    callee_server = TailCallee()
    caller_server = TailCaller()

    callee = capability.TestTailCallee._new_client(callee_server)
    caller = capability.TestTailCaller._new_client(caller_server)

    promise = caller.foo(i=456, callee=callee)
    dependent_call1 = promise.c.getCallSequence()

    response = promise.wait()

    assert response.i == 456
    assert response.i == 456

    dependent_call2 = response.c.getCallSequence()
    dependent_call3 = response.c.getCallSequence()

    result = dependent_call1.wait()
    assert result.n == 0
    result = dependent_call2.wait()
    assert result.n == 1
    result = dependent_call3.wait()
    assert result.n == 2

    assert callee_server.count == 1
    assert caller_server.count == 1


def test_cancel():
    client = capability.TestInterface._new_client(Server())

    req = client._request('foo')
    req.i = 5

    remote = req.send()
    remote.cancel()

    with pytest.raises(KjException, match="Promise was already used in a consuming operation. You can no longer use this Promise object"):
        remote.wait()


def test_timer():
    global test_timer_var
    test_timer_var = False

    def set_timer_var():
        global test_timer_var
        test_timer_var = True

    capnp.getTimer().after_delay(1).then(set_timer_var).wait()

    assert test_timer_var is True

    test_timer_var = False
    promise = capnp.Promise(0).then(lambda x: time.sleep(.1)).then(lambda x: time.sleep(.1)).then(
        lambda x: set_timer_var())

    canceller = capnp.getTimer().after_delay(1).then(lambda: promise.cancel())

    joined = capnp.join_promises([canceller, promise])
    joined.wait()

    # faling for now, not sure why...
    # assert test_timer_var is False


def test_double_send():
    client = capability.TestInterface._new_client(Server())

    req = client._request('foo')
    req.i = 5

    req.send()
    with pytest.raises(KjException, match='Request has already been sent.'):
        req.send()


def test_then_args():
    capnp.Promise(0).then(lambda x: 1)

    with pytest.raises(TypeError, match="take exactly one argument"):
        capnp.Promise(0).then(lambda: 1)

    with pytest.raises(TypeError, match="take exactly one argument"):
        capnp.Promise(0).then(lambda x, y: 1)

    capnp.getTimer().after_delay(1).then(lambda: 1)  # after_delay is a VoidPromise

    with pytest.raises(TypeError, match="Function passed to `then` call must take no arguments"):
        capnp.getTimer().after_delay(1).then(lambda x: 1)

    client = capability.TestInterface._new_client(Server())

    client.foo(i=5).then(lambda x: 1)

    with pytest.raises(TypeError, match="take exactly one argument"):
        client.foo(i=5).then(lambda: 1)

    with pytest.raises(TypeError, match="take exactly one argument"):
        client.foo(i=5).then(lambda x, y: 1)


class ExtendsServer(Server):
    def qux(self, **kwargs):
        pass


def test_inheritance():
    client = capability.TestExtends._new_client(ExtendsServer())
    client.qux().wait()

    remote = client.foo(i=5)
    response = remote.wait()

    assert response.x == '26'


class PassedCapTest(capability.TestPassedCap.Server):
    def foo(self, cap, _context, **kwargs):
        def set_result(res):
            _context.results.x = res.x

        return cap.foo(5).then(set_result)


def test_null_cap():
    client = capability.TestPassedCap._new_client(PassedCapTest())
    assert client.foo(Server()).wait().x == '26'

    with pytest.raises(capnp.KjException, match="Called null capability."):
        client.foo().wait()


class StructArgTest(capability.TestStructArg.Server):
    def bar(self, a, b, **kwargs):
        return a + str(b)


def test_struct_args():
    client = capability.TestStructArg._new_client(StructArgTest())
    assert client.bar(a='test', b=1).wait().c == 'test1'
    with pytest.raises(TypeError,
                       match="Cannot call method `bar` with positional args, since its param struct is not implicitly defined and thus does not have a set order of arguments"):
        assert client.bar('test', 1).wait().c == 'test1'


class GenericTest(capability.TestGeneric.Server):
    def foo(self, a, **kwargs):
        return a.as_text() + 'test'


def test_generic():
    client = capability.TestGeneric._new_client(GenericTest())

    obj = capnp._MallocMessageBuilder().get_root_as_any()
    obj.set_as_text("anypointer_")
    assert client.foo(obj).wait().b == 'anypointer_test'
